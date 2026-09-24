#!/usr/bin/env python3
"""Install Odoo modules through the Ingress Apps screen, one at a time.

Issue #144's parity run installs 29 modules on a fresh database through the
Ingress surface, never the Public origin or the command line: the install
itself is part of what is tested. For each module in dependency order the
driver opens the module's form in the Apps screen under the Ingress prefix,
presses Activate, and waits until Odoo reports the module installed.

The pure parts are tested in the static tier by test_e2e_ingress_install.py.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping, NamedTuple, Sequence

# `rewrite_apply.report` opens each round with this line and names the
# prefixes it generated on an indented `prefixes:` line.
_ROUND = re.compile(r"Rewrite scan \(apply\): (.+?)\s*$")
_PREFIXES = re.compile(r"^\S*\s+prefixes: (.+?)\s*$")


class ScanRound(NamedTuple):
    status: str
    prefixes: tuple[str, ...]


def scan_rounds(lines: Iterable[str]) -> list[ScanRound]:
    """The Rewrite scan rounds an add-on log excerpt reports, in order."""
    rounds: list[ScanRound] = []
    for line in lines:
        start = _ROUND.search(line)
        if start:
            rounds.append(ScanRound(start.group(1), ()))
            continue
        more = _PREFIXES.search(line)
        if more and rounds:
            rounds[-1] = rounds[-1]._replace(prefixes=tuple(more.group(1).split()))
    return rounds


#: `rewrite_apply.NOTIFICATION_IDS`: every id the Rewrite scan notifies under.
REWRITE_NOTIFICATION_PREFIX = "odoo18ce_generated_rewrites_"


def new_rewrite_notifications(
    before: Iterable[Mapping[str, str]], after: Iterable[Mapping[str, str]],
) -> list[Mapping[str, str]]:
    """Rewrite scan notifications in `after` that `before` did not hold.

    A failure notification keeps its id round after round, so one that was
    created again counts too: its `created_at` changed.
    """
    seen = {(n["notification_id"], n.get("created_at")) for n in before}
    return [
        n for n in after
        if n["notification_id"].startswith(REWRITE_NOTIFICATION_PREFIX)
        and (n["notification_id"], n.get("created_at")) not in seen
    ]


def install_order(targets: Sequence[str], deps: Mapping[str, Iterable[str]]) -> list[str]:
    """The targets ordered so each comes after every target it depends on.

    `deps` holds each module's direct dependencies, targets or not; a
    dependency outside the targets is walked through but left to Odoo to
    install. Ties go alphabetically, so a run is repeatable.
    """
    wanted = set(targets)

    def reachable(module: str) -> set[str]:
        seen: set[str] = set()
        stack = list(deps.get(module, ()))
        while stack:
            name = stack.pop()
            if name not in seen:
                seen.add(name)
                stack.extend(deps.get(name, ()))
        return seen

    before = {module: reachable(module) & wanted for module in wanted}
    order: list[str] = []
    while len(order) < len(wanted):
        ready = sorted(m for m in wanted - set(order) if before[m] <= set(order))
        if not ready:
            raise ValueError("dependency cycle among %s" % sorted(wanted - set(order)))
        order.append(ready[0])
    return order


# --- Live driver ------------------------------------------------------------

INSTALL_TIMEOUT_SECONDS = 1200
#: The Rewrite scan runs a round every five minutes (services.d/rewrite-scan),
#: measured between rounds, so one starts within five minutes plus a round.
SCAN_WAIT_SECONDS = 420
POLL_SECONDS = 15


class IngressApps:
    """The Apps screen under the Ingress prefix, driven like an operator would."""

    def __init__(self, driver) -> None:
        self.driver = driver
        self.page = driver.context.new_page()

    def rpc(self, model: str, method: str, args: list, kwargs: Mapping | None = None):
        response = self.driver.context.request.post(
            self.driver.base + "/web/dataset/call_kw/%s/%s" % (model, method),
            data={"jsonrpc": "2.0", "method": "call", "params": {
                "model": model, "method": method, "args": args, "kwargs": dict(kwargs or {}),
            }},
        )
        body = response.json()
        if response.status != 200 or "error" in body:
            raise RuntimeError("%s.%s failed: %s" % (model, method, body.get("error", {}).get("message")))
        return body["result"]

    def modules(self, names: Sequence[str]) -> dict[str, dict]:
        rows = self.rpc("ir.module.module", "search_read", [[["name", "in", list(names)]]],
                        {"fields": ["name", "state"]})
        return {row["name"]: row for row in rows}

    def dependencies(self) -> dict[str, set[str]]:
        rows = self.rpc("ir.module.module.dependency", "search_read", [[]],
                        {"fields": ["module_id", "name"]})
        deps: dict[str, set[str]] = {}
        ids = {row["module_id"][0] for row in rows}
        names = {row["id"]: row["name"] for row in self.rpc(
            "ir.module.module", "search_read", [[["id", "in", sorted(ids)]]], {"fields": ["name"]})}
        for row in rows:
            deps.setdefault(names[row["module_id"][0]], set()).add(row["name"])
        return deps

    def update_list(self) -> None:
        """Apps > Update Apps List, so modules copied into the addons path show up."""
        self.page.goto(self.driver.base + "/odoo/action-base.action_view_base_module_update",
                       wait_until="load", timeout=120000)
        self.page.locator('button[name="update_module"]').click()
        self.page.locator(".modal").wait_for(state="detached", timeout=300000)

    def install(self, module_id: int) -> None:
        self.page.goto(self.driver.base + "/odoo/action-base.open_module_tree/%d" % module_id,
                       wait_until="load", timeout=120000)
        button = self.page.locator('button[name="button_immediate_install"]')
        button.wait_for(timeout=60000)
        button.click()


def _notifications(driver) -> list[dict]:
    return driver.ingress._call(lambda i: {"id": i, "type": "persistent_notification/get"}) or []


def _log_since(command: str, since: int) -> list[str]:
    import shlex
    import subprocess

    done = subprocess.run(shlex.split(command.format(since=since)), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)
    return (done.stdout + done.stderr).splitlines()


def run_installs(modules: Sequence[str], log_command: str, out, *, update_list: bool) -> int:
    import json
    import os
    import sys
    import time

    from playwright.sync_api import sync_playwright

    from e2e_menu_action_adapter import SurfaceDriver
    from e2e_menu_action_crawler import Surface

    failures = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        driver = SurfaceDriver(Surface.HA_INGRESS, browser,
                               ignore_https_errors=os.environ.get("IGNORE_HTTPS_ERRORS", "0") == "1")
        try:
            driver.log_in()
            apps = IngressApps(driver)
            if update_list:
                apps.update_list()
            known = apps.modules(modules)
            missing = sorted(set(modules) - set(known))
            if missing:
                raise RuntimeError("not in the Apps list: %s" % ", ".join(missing))
            for module in install_order(modules, apps.dependencies()):
                record = {"module": module, "database": os.environ.get("ODOO_DB", "default")}
                state = apps.modules([module])[module]["state"]
                if state == "installed":
                    record.update(result="already installed")
                    out.write(json.dumps(record) + "\n")
                    out.flush()
                    continue
                before = _notifications(driver)
                started = time.time()
                apps.install(known[module]["id"])
                while time.time() - started < INSTALL_TIMEOUT_SECONDS:
                    time.sleep(POLL_SECONDS)
                    driver.ingress.keep_alive()
                    try:
                        state = apps.modules([module])[module]["state"]
                    except Exception:  # noqa: BLE001 -- the registry reloads during an install
                        continue
                    if state == "installed":
                        break
                installed = int(time.time())
                record.update(state=state, install_seconds=installed - int(started))
                rounds: list[ScanRound] = []
                while state == "installed" and time.time() - installed < SCAN_WAIT_SECONDS:
                    time.sleep(POLL_SECONDS)
                    driver.ingress.keep_alive()
                    rounds = scan_rounds(_log_since(log_command, installed))
                    if rounds:
                        break
                added = new_rewrite_notifications(before, _notifications(driver))
                record.update(
                    scan_rounds=[r._asdict() for r in rounds],
                    scan_round_seconds=int(time.time()) - installed if rounds else None,
                    notifications=[{"id": n["notification_id"], "title": n.get("title")} for n in added],
                )
                ok = state == "installed" and bool(rounds)
                failures += not ok
                out.write(json.dumps(driver.masker.value(record), ensure_ascii=False) + "\n")
                out.flush()
                print("%s %s %s" % ("OK  " if ok else "FAIL", module, record.get("state")), file=sys.stderr)
                if state != "installed":
                    break  # a later module may depend on this one
        finally:
            driver.close()
            browser.close()
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import os

    from e2e_menu_action_adapter import parse_env_file

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--modules", required=True, help="comma-separated module names")
    parser.add_argument("--log-command", required=True,
                        help="prints the add-on log since {since} (a Unix time), e.g. "
                             "'ssh root@<test-host> docker logs --since {since} <container>'")
    parser.add_argument("--update-list", action="store_true", help="run Update Apps List first")
    parser.add_argument("--out", required=True, help="JSONL file, one record per module")
    parser.add_argument("--env-file", help="read unset credentials from this NAME=value file")
    args = parser.parse_args(argv)
    if args.env_file:
        with open(args.env_file, encoding="utf-8") as env_file:
            parse_env_file(env_file, os.environ)
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    with open(args.out, "a", encoding="utf-8") as out:
        return run_installs(modules, args.log_command, out, update_list=args.update_list)


if __name__ == "__main__":
    import sys

    sys.exit(main())
