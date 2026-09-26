#!/usr/bin/env python3
"""POS offline on both surfaces (#161, ADR 0011, parity plan U-C27).

    python odoo18ce/tests/e2e_pos_offline_live.py run --env-file .env --db odoo_parity \
        --out checks.jsonl [--run-id WOOW-PARITY-...] [--config "Furniture Shop"]

On each surface -- the Public origin, then the add-on panel in Home Assistant
with Odoo in its Ingress iframe -- the run opens `/pos/ui` of the config's
open session, cuts the network with the browser's offline emulation (never
the host's), sells one product for cash, restores the network and looks for
the order on the server. Then it cuts the network again and reloads
`/pos/ui`. Each surface's results go into two `odoo-parity-evidence/v1`
records, `POS offline sale` and `POS offline reload`, under U-C27.

The config needs an open session (the run does not open one), and every run
leaves one paid order per surface in it. Signals are counted while the
browser is online; what failed while it was offline is expected and goes
into the details.

Environment and surfaces as in e2e_parity_shared_layers_live.py.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Mapping, Sequence

from e2e_menu_action_adapter import RunInfo, new_run_id, parse_env_file
from e2e_parity_shared_layers import Outcome, check_record
from e2e_parity_shared_layers_live import Env, Side, open_sides

TIMEOUT = 60_000
ROUTE = "/pos/ui"
PRODUCT = "Desk Pad"
SYNC_WAIT_S = 90


# --- Pure parts (static tier: test_e2e_pos_offline.py) -------------------------


def sale_outcome(local: Mapping[str, Any], server_rows: Sequence[Mapping[str, Any]], *, session_id: int) -> Outcome:
    """What became of the sale the till made offline, judged from the server."""
    details: dict[str, Any] = {key: local.get(key) for key in
                               ("went_offline", "validated_offline", "offline_notice", "synced_after_s")}
    if not local.get("went_offline"):
        return Outcome(False, "the till was never offline", details=details)
    if not local.get("validated_offline"):
        return Outcome(True, "till could not validate the sale offline", details=details)
    order = next((row for row in server_rows if row.get("uuid") == local.get("uuid")), None)
    if order is None:
        return Outcome(True, "offline sale not on the server after reconnect", details=details)
    details["server_order"] = {key: order.get(key) for key in
                               ("id", "pos_reference", "state", "amount_total", "session_id")}
    if (order.get("session_id") or [None])[0] != session_id:
        return Outcome(True, "offline sale landed in another session", details=details)
    return Outcome(True, "offline sale reached the server after reconnect", details=details)


_NET_ERROR = re.compile(r"net::ERR_[A-Z_]+")


def net_error(message: str) -> str | None:
    match = _NET_ERROR.search(message or "")
    return match.group(0) if match else None


def reload_outcome(error: str | None, *, till_loaded: bool) -> Outcome:
    """Whether `/pos/ui` comes back when it is loaded again with the network cut."""
    if error:
        code = net_error(error) or "error"
        return Outcome(True, "offline reload fails (%s)" % code, details={"error": code})
    return Outcome(True, "offline reload loads the till" if till_loaded else "offline reload shows no till")


def pos_records(run: RunInfo, public_sale: Outcome, ingress_sale: Outcome,
                public_reload: Outcome, ingress_reload: Outcome) -> list[dict[str, Any]]:
    common = {"module": "point_of_sale", "route": ROUTE}
    return [
        check_record(run, "U-C27", screen="POS offline sale", public=public_sale, ingress=ingress_sale,
                     notes="Sold offline with the browser's offline emulation, then reconnected; the order "
                           "is looked up on the server by its uuid.", **common),
        check_record(run, "U-C27", screen="POS offline reload", public=public_reload, ingress=ingress_reload,
                     notes="/pos/ui loaded again with the network cut. Odoo 18 CE's POS has no service worker "
                           "of its own.", **common),
    ]


# --- Live part ---------------------------------------------------------------

# The POS store: `posmodel` in POS 18, or through the OWL env.
_ORDER_UUID = """() => {
  const pos = window.posmodel || (odoo.__WOWL_DEBUG__ && odoo.__WOWL_DEBUG__.root.env.services.pos);
  const order = pos.getOrder ? pos.getOrder() : pos.get_order();
  return order.uuid;
}"""
_OFFLINE_NOTICE = re.compile(r"Connection Lost[^\n]*|offline[^\n]{0,80}", re.I)


def enter_till(side: Side) -> None:
    """Past the opening control and the pos_hr lock screen, to the product grid."""
    root = side.root
    products = root.locator("article.product").first
    deadline = time.time() + TIMEOUT / 1000
    while time.time() < deadline:
        if products.is_visible():
            return
        dialog_open = root.locator(".modal button", has_text="Open Register")
        if dialog_open.count() and dialog_open.first.is_visible():
            dialog_open.first.click()
        elif root.get_by_text("Open Register").count() and root.get_by_text("Open Register").first.is_visible():
            root.get_by_text("Open Register").first.click()
        elif root.get_by_text("Unlock Register").count() and root.get_by_text("Unlock Register").first.is_visible():
            root.get_by_text("Unlock Register").first.click()
        side.page.wait_for_timeout(1000)
    raise RuntimeError("POS never showed its product grid")


def offline_notice(side: Side, wait_s: int = 15) -> str | None:
    for _ in range(wait_s):
        text = side.root.evaluate("() => document.body.innerText")
        match = _OFFLINE_NOTICE.search(text)
        if match:
            return match.group(0).strip()[:120]
        side.page.wait_for_timeout(1000)
    return None


def sell_one(side: Side) -> bool:
    """Product, Payment, Cash, Validate; True when the receipt screen shows."""
    root = side.root
    root.locator("article.product", has_text=PRODUCT).first.click()
    root.locator(".pay-order-button").first.click()
    root.locator(".paymentmethod", has_text="Cash").first.click()
    root.locator(".validation-button.next:not(.disabled)").first.click()
    try:
        root.get_by_text("New Order").first.wait_for(timeout=30_000)
        return True
    except Exception:  # noqa: BLE001 -- the result says it
        return False


def add_signals(*blocks: Mapping[str, int]) -> dict[str, int]:
    total: dict[str, int] = {}
    for block in blocks:
        for name, count in block.items():
            total[name] = total.get(name, 0) + count
    return total


def offline_sale(side: Side, server: Side, session_id: int, config_id: int) -> tuple[Outcome, Outcome]:
    recorder = side.recorder
    side.close_chat_windows()
    start = recorder.mark()
    side.goto("%s?config_id=%d" % (ROUTE, config_id), wait="domcontentloaded")
    enter_till(side)
    side.settle()
    online_before = recorder.since(start)
    online_details = recorder.details(start)

    local: dict[str, Any] = {"went_offline": False, "validated_offline": False}
    offline_mark = recorder.mark()
    side.context.set_offline(True)
    try:
        local["went_offline"] = side.root.evaluate("() => !navigator.onLine")
        local["uuid"] = side.root.evaluate(_ORDER_UUID)
        local["validated_offline"] = sell_one(side)
        local["offline_notice"] = offline_notice(side)
        offline_seen = recorder.details(offline_mark)
    finally:
        side.context.set_offline(False)
    restored = recorder.mark()
    started = time.time()
    rows: list[dict[str, Any]] = []
    while time.time() - started < SYNC_WAIT_S:
        rows = server.rpc("pos.order", "search_read", [[["uuid", "=", local.get("uuid")]]],
                          {"fields": ["uuid", "session_id", "state", "amount_total", "pos_reference"]})
        if rows:
            local["synced_after_s"] = round(time.time() - started)
            break
        side.page.wait_for_timeout(3000)
    side.settle()
    sale = sale_outcome(local, rows, session_id=session_id)
    sale = Outcome(sale.available, sale.result,
                   add_signals(online_before, recorder.since(restored)),
                   {**sale.details, "offline_window": {k: v for k, v in offline_seen.items() if v},
                    "online_signal_sources": {k: v for k, v in online_details.items() if v}})

    side.context.set_offline(True)
    error = None
    till_loaded = False
    try:
        try:
            side.goto("%s?config_id=%d" % (ROUTE, config_id), wait="domcontentloaded")
            side.root.locator("article.product, .modal button").first.wait_for(timeout=15_000)
            till_loaded = True
        except Exception as caught:  # noqa: BLE001 -- the failure is the result
            error = str(caught).splitlines()[0] if net_error(str(caught)) else None
    finally:
        side.context.set_offline(False)
    return sale, reload_outcome(error, till_loaded=till_loaded)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--env-file")
    run.add_argument("--db", required=True, help="the database both surfaces must serve")
    run.add_argument("--out", required=True, help="JSONL file; records are appended")
    run.add_argument("--run-id")
    run.add_argument("--config", default="Furniture Shop", help="the pos.config to sell with")
    run.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    if args.env_file:
        with open(args.env_file, encoding="utf-8") as handle:
            parse_env_file(handle, os.environ)
    os.environ["ODOO_DB"] = args.db
    env = Env(args.db)
    info = RunInfo(args.run_id or new_run_id(), env.target, env.db)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        public = ingress = None
        try:
            public, ingress = open_sides(env, browser)
            config = public.rpc("pos.config", "search_read", [[["name", "=", args.config]]],
                                {"fields": ["current_session_id", "current_session_state"]})
            if not config or not config[0]["current_session_id"]:
                raise RuntimeError("config %r has no open session" % args.config)
            config_id, session_id = config[0]["id"], config[0]["current_session_id"][0]
            print("session %s (%s)" % (config[0]["current_session_id"][1], config[0]["current_session_state"]),
                  file=sys.stderr)
            outcomes = {}
            for side in (public, ingress):
                outcomes[side.name] = offline_sale(side, public, session_id, config_id)
                print("%s: %s / %s" % (side.name, outcomes[side.name][0].result, outcomes[side.name][1].result),
                      file=sys.stderr)
            records = pos_records(info, outcomes["public"][0], outcomes["ingress"][0],
                                  outcomes["public"][1], outcomes["ingress"][1])
            with open(args.out, "a", encoding="utf-8") as out:
                for record in records:
                    out.write(json.dumps(env.mask(record), ensure_ascii=False, sort_keys=True) + "\n")
            for record in records:
                print("%s %s" % (record["verdict"], record["control_identity"]), file=sys.stderr)
            return 0
        finally:
            for side in (public, ingress):
                if side is not None:
                    side.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
