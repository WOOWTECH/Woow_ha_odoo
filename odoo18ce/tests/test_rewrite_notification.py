#!/usr/bin/env python3
"""Static-tier contracts for the Rewrite scan's Home Assistant notification
(issue #78, ADR 0005).

ADR 0005 lets a Generated rewrite go live without a human reading it, and
names the notification and the log line as the review. So the operator
hears about exactly two things: a round that added Generated rewrites
(naming the prefixes), and a round whose generation, validation or reload
failed (naming the step). A round that changed nothing, and any round with
`literal_rewrite_auto` off, sends nothing.

`round_event` and `notification` are pure; `notify` is the adapter to the
Supervisor and is driven here with a fake opener. `main` is the one seam
where a round meets the adapter.
"""
import importlib.machinery
import importlib.util
import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "rootfs/usr/local/lib"
TEMPLATE = ROOT / "rootfs/etc/nginx/nginx.conf.template"
CONFIG = ROOT / "config.yaml"


def load_module(path: Path, name: str):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scan = load_module(LIB_DIR / "rewrite_scan.py", "rewrite_scan")
gate = load_module(LIB_DIR / "literal_rewrite_gate.py", "literal_rewrite_gate")
apply = load_module(LIB_DIR / "rewrite_apply.py", "rewrite_apply")

# Documentation names only; no real database or host here.
DB = "odoo_test"
OTHER_DB = "odoo_other"
URL = "/web/assets/1/8c63e6a/web.assets_web.min.js"
SUM = "7683fa082aaa53fd969289bc141aa78853af2d7c"
TOKEN = "01H8XGJWBWBAQ4TK1Z9MY3MNFW"

FORUM_BUNDLE = 'function post(){window.location.href="/forum/ask";}\n'


def row(database=DB, url=URL, checksum=SUM):
    return scan.BundleRow(
        database=database, url=url, name="web.assets_web.min.js",
        checksum=checksum, store_fname=f"{checksum[:2]}/{checksum}", file_size=1024,
    )


def filestore(tmp_path: Path, *bundles) -> str:
    root = tmp_path / "filestore"
    for one, text in bundles:
        path = Path(scan.bundle_path(one, str(root)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


def ok(database=DB, *rows) -> "scan.DatabaseScan":
    return scan.DatabaseScan(database, scan.STATUS_OK, tuple(rows))


def rendered_conf() -> str:
    config = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, value in {
        "%%WS_PORT%%": "8070",
        "%%PUBLIC_PROTO%%": "https",
        "%%PUBLIC_HOST_MAP%%": '"odoo-test.invalid" 1;',
        "%%DENY_STATUS%%": "444",
        "%%LAN_NETWORKS%%": "192.168.0.0/16 1;",
        "%%INGRESS_CACHE_VERSION%%": "test",
        "%%CANONICAL_URL%%": "https://odoo-test.invalid",
    }.items():
        config = config.replace(placeholder, value)
    return config


class Runner:
    """A stand-in for `subprocess.run`: nginx answers as told."""

    def __init__(self, test_code: int = 0, reload_code: int = 0):
        self.test_code = test_code
        self.reload_code = reload_code

    def __call__(self, command, **kwargs):
        code = self.reload_code if command[1:] == ["-s", "reload"] else self.test_code
        return subprocess.CompletedProcess(command, code, "", "nginx says so\n")


def round_outcome(tmp_path, scan_result, *, include_text="", **keywords):
    include = tmp_path / "nginx-generated-rewrites.conf"
    include.write_text(include_text, encoding="utf-8")
    conf = tmp_path / "nginx.conf"
    conf.write_text(rendered_conf(), encoding="utf-8")
    keywords.setdefault("runner", Runner())
    keywords.setdefault("running", lambda: True)
    keywords.setdefault("state_path", tmp_path / "state.json")
    before = apply.live_prefixes(include)
    outcome = apply.apply_round(
        scan_result, include_path=include, nginx_conf_path=conf,
        version="0" * 64, **keywords,
    )
    return outcome, before


def forum_round(tmp_path, **keywords):
    one = row()
    store = filestore(tmp_path, (one, FORUM_BUNDLE))
    return round_outcome(tmp_path, scan.ScanResult((ok(DB, one),)), filestore=store, **keywords)


# --- which rounds are events --------------------------------------------------

def test_a_round_that_added_a_rule_is_an_added_event(tmp_path: Path) -> None:
    outcome, before = forum_round(tmp_path)
    event = apply.round_event(outcome, before)
    assert event is not None and event.kind == apply.EVENT_ADDED
    assert event.prefixes == ("/forum/",)


def test_only_the_prefixes_the_round_added_are_named(tmp_path: Path) -> None:
    outcome = apply.ApplyResult(
        apply.STATUS_APPLIED, prefixes=("/forum/", "/livechat/"), wrote=True, reloaded=True,
    )
    event = apply.round_event(outcome, ("/forum/",))
    assert event.prefixes == ("/livechat/",)


def test_a_round_that_only_removed_rules_sends_nothing() -> None:
    outcome = apply.ApplyResult(apply.STATUS_APPLIED, prefixes=(), wrote=True, reloaded=True)
    assert apply.round_event(outcome, ("/forum/",)) is None


def test_an_unchanged_round_sends_nothing(tmp_path: Path) -> None:
    outcome, before = forum_round(tmp_path)
    again, before = round_outcome(
        tmp_path, outcome.scan, include_text=outcome.include_text,
        filestore=str(tmp_path / "filestore"), force=True,
    )
    assert again.status == apply.STATUS_UNCHANGED
    assert apply.round_event(again, before) is None


def test_a_round_with_no_pass_due_sends_nothing() -> None:
    outcome = apply.ApplyResult(apply.STATUS_UP_TO_DATE, prefixes=("/forum/",))
    assert apply.round_event(outcome, ()) is None


def test_application_off_sends_nothing(tmp_path: Path) -> None:
    outcome, before = forum_round(tmp_path, auto=False)
    assert outcome.status == apply.STATUS_OFF
    assert outcome.prefixes == ("/forum/",), "the prefixes are what would be rewritten"
    assert apply.round_event(outcome, before, auto=False) is None


def test_application_off_sends_nothing_even_for_a_failed_round() -> None:
    outcome = apply.ApplyResult(apply.STATUS_INCOMPLETE, "the scan is incomplete")
    assert apply.round_event(outcome, (), auto=False) is None


def test_an_incomplete_scan_is_a_failed_generation(tmp_path: Path) -> None:
    outcome, before = round_outcome(
        tmp_path,
        scan.ScanResult((scan.DatabaseScan(OTHER_DB, scan.STATUS_FAILED, error="connection refused"),)),
    )
    event = apply.round_event(outcome, before)
    assert event.kind == apply.EVENT_FAILED
    assert event.step == apply.STEP_GENERATION


def test_a_refused_candidate_is_a_failed_validation(tmp_path: Path) -> None:
    outcome, before = forum_round(tmp_path, runner=Runner(test_code=1))
    assert outcome.status == apply.STATUS_INVALID
    event = apply.round_event(outcome, before)
    assert event.kind == apply.EVENT_FAILED
    assert event.step == apply.STEP_VALIDATION


def test_a_failed_reload_is_a_failed_reload(tmp_path: Path) -> None:
    outcome, before = forum_round(tmp_path, runner=Runner(reload_code=1))
    assert outcome.status == apply.STATUS_APPLIED and not outcome.reloaded
    event = apply.round_event(outcome, before)
    assert event.kind == apply.EVENT_FAILED
    assert event.step == apply.STEP_RELOAD


def test_nginx_not_running_yet_is_not_a_failed_reload(tmp_path: Path) -> None:
    """At start the scan can beat nginx; nginx loads the file when it starts."""
    outcome, before = forum_round(tmp_path, running=lambda: False)
    event = apply.round_event(outcome, before)
    assert event.kind == apply.EVENT_ADDED


# --- what the notification says -----------------------------------------------

def test_an_added_notification_lists_the_prefixes() -> None:
    title, body = apply.notification(apply.RoundEvent(apply.EVENT_ADDED, prefixes=("/forum/", "/livechat/")))
    assert "added" in title.lower()
    assert "/forum/" in body and "/livechat/" in body


def test_a_failed_notification_names_the_step() -> None:
    for step in (apply.STEP_GENERATION, apply.STEP_VALIDATION, apply.STEP_RELOAD):
        title, body = apply.notification(
            apply.RoundEvent(apply.EVENT_FAILED, step=step, detail="nginx says no")
        )
        assert step in title
        assert step in body
        assert "nginx says no" in body


def test_a_notification_never_carries_an_ingress_token() -> None:
    leak = f"/api/hassio_ingress/{TOKEN}/forum/"
    for event in (
        apply.RoundEvent(apply.EVENT_ADDED, prefixes=(leak,)),
        apply.RoundEvent(apply.EVENT_FAILED, step=apply.STEP_VALIDATION, detail=f"at {leak}"),
    ):
        title, body = apply.notification(event)
        assert TOKEN not in title + body
        assert "<redacted>" in body


# --- the adapter --------------------------------------------------------------

class Opener:
    """A stand-in for `urllib.request.urlopen`."""

    def __init__(self, error: Exception | None = None):
        self.requests: list = []
        self.error = error

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        return io.BytesIO(b"[]")


def test_the_adapter_creates_a_persistent_notification_through_the_supervisor() -> None:
    opener = Opener()
    logged: list[str] = []
    sent = apply.notify(("Title", "Body"), token="supervisor-token", opener=opener, log=logged.append)
    assert sent
    (request, timeout), = opener.requests
    assert request.full_url == "http://supervisor/core/api/services/persistent_notification/create"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer supervisor-token"
    payload = json.loads(request.data)
    assert payload["title"] == "Title" and payload["message"] == "Body"
    assert payload["notification_id"]
    assert timeout


def test_a_failure_to_notify_is_logged_and_not_raised() -> None:
    logged: list[str] = []
    opener = Opener(urllib.error.URLError(f"refused at /api/hassio_ingress/{TOKEN}/x"))
    assert not apply.notify(("Title", "Body"), token="t", opener=opener, log=logged.append)
    assert logged and "notification" in logged[0]
    assert TOKEN not in "\n".join(logged)


def test_no_supervisor_token_is_logged_and_nothing_is_sent() -> None:
    logged: list[str] = []
    opener = Opener()
    assert not apply.notify(("Title", "Body"), token="", opener=opener, log=logged.append)
    assert opener.requests == []
    assert logged


def test_the_add_on_may_call_the_home_assistant_api() -> None:
    """`/core/api` through the Supervisor needs `homeassistant_api`."""
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["homeassistant_api"] is True


# --- the seam -----------------------------------------------------------------

def run_main(tmp_path, *arguments, include_text="", failed=False,
             notify_raises=False, sent=None):
    """`main` against a temporary host, with the adapter replaced.

    Returns the exit code, each notification sent as ((title, body), id),
    and the lines the round logged.
    """
    one = row()
    store = filestore(tmp_path, (one, FORUM_BUNDLE))
    include = tmp_path / "nginx-generated-rewrites.conf"
    include.write_text(include_text, encoding="utf-8")
    conf = tmp_path / "nginx.conf"
    conf.write_text(rendered_conf(), encoding="utf-8")
    database = (
        scan.DatabaseScan(DB, scan.STATUS_FAILED, error="connection refused")
        if failed else ok(DB, one)
    )
    sent = [] if sent is None else sent

    def notifier(note, *, notification_id, log):
        if notify_raises:
            raise RuntimeError("the adapter broke")
        sent.append((note, notification_id))
        return True

    original = scan.scan_databases, apply.apply_include
    scan.scan_databases = lambda run_query: scan.ScanResult((database,))

    def no_nginx(text, nginx_conf, **keywords):
        return original[1](text, nginx_conf, **dict(keywords, runner=Runner(), running=lambda: False))

    apply.apply_include = no_nginx
    lines: list[str] = []
    try:
        code = apply.main(
            ["--state", str(tmp_path / "state.json"), "--include", str(include),
             "--nginx-conf", str(conf), "--filestore", store, *arguments],
            out=lines.append, notifier=notifier,
        )
    finally:
        scan.scan_databases, apply.apply_include = original
    return code, sent, lines


def test_main_notifies_a_round_that_added_a_rule(tmp_path: Path) -> None:
    code, sent, _ = run_main(tmp_path)
    assert code == 0
    ((title, body), notification_id), = sent
    assert "/forum/" in body
    assert notification_id == apply.NOTIFICATION_IDS[apply.EVENT_ADDED]


def test_main_notifies_a_failed_round(tmp_path: Path) -> None:
    code, sent, _ = run_main(tmp_path, failed=True)
    assert code == 1
    ((title, body), notification_id), = sent
    assert apply.STEP_GENERATION in title
    assert notification_id == apply.NOTIFICATION_IDS[apply.EVENT_FAILED]


def test_the_two_events_never_replace_each_other() -> None:
    """A failure every five minutes must not overwrite the rules that were added."""
    assert apply.NOTIFICATION_IDS[apply.EVENT_ADDED] != apply.NOTIFICATION_IDS[apply.EVENT_FAILED]


def test_main_notifies_a_generation_that_raised_and_still_fails(tmp_path: Path) -> None:
    sent: list = []
    # argparse keeps the last value, so this points the round at no configuration.
    with pytest.raises(FileNotFoundError):
        run_main(tmp_path, "--nginx-conf", str(tmp_path / "absent.conf"), sent=sent)
    ((title, body), notification_id), = sent
    assert apply.STEP_GENERATION in title
    assert notification_id == apply.NOTIFICATION_IDS[apply.EVENT_FAILED]


def test_main_sends_nothing_for_a_round_that_changed_nothing(tmp_path: Path) -> None:
    _, first, _ = run_main(tmp_path)
    assert first
    written = (tmp_path / "nginx-generated-rewrites.conf").read_text(encoding="utf-8")
    code, sent, _ = run_main(tmp_path, "--force", include_text=written)
    assert code == 0
    assert sent == []


def test_main_sends_nothing_with_application_off(tmp_path: Path) -> None:
    code, sent, _ = run_main(tmp_path, "--no-auto")
    assert code == 0
    assert sent == []
    _, sent, _ = run_main(tmp_path, "--no-auto", failed=True)
    assert sent == []


def test_a_broken_adapter_does_not_change_the_round(tmp_path: Path) -> None:
    code, _, lines = run_main(tmp_path, notify_raises=True)
    assert code == 0
    assert any("notification could not be sent" in line for line in lines)
