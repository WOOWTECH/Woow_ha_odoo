"""Live: the Ingress markup family's four readonly/editor screens (#243).

`#243` is the register of Live-tier checks the Ingress markup family left owed.
Four of its five rows have no adapter subcommand, because none of them is the
shape `e2e_menu_action_adapter.py` judges -- "open this screen on both surfaces
and diff the two records". Each is instead *one interaction* whose result is
read in two places: on the screen (did the picture resolve under the prefix and
arrive) and in the database afterwards (is the stored value still
root-relative). The fifth row, #234's, is `e2e_collab_peer_snapshot_live.py`,
whose pure helpers this module reuses rather than copies.

    readonly-plain      #237 check 1. A readonly html field on the plain path
                        (`t-out="state.value"`): the html field's history
                        dialog, which mounts `HtmlViewer` through a `getConfig()`
                        setting neither `hasFullHtml` nor `cssAssetId`, so it is
                        that path by construction. Reads only.
    readonly-iframe     #237 check 2. The same field on the `hasFullHtml` path,
                        inside `sandbox="allow-same-origin allow-popups
                        allow-popups-to-escape-sandbox"`. Needs a full-HTML
                        value, so it seeds a **scratch** task -- never the
                        onboarding to-do, whose stored `src` #235's checks read.
    codeview            #240. A user signature in Preferences with debug mode
                        on: the code view toggled off re-inserts the record's
                        markup, and the save must still store it root-relative.
    media-image-todo    #239 line 1. The media dialog reopened on an existing
    media-image-website #239 line 2, the more informative one: the same dialog
                        in the website editor, where `data-original-src` arrives
                        prefixed by the *generic HTML location* rather than the
                        shim, which is the branch that `return`s before the
                        first rule.
    media-document-todo #239 line 3, a no-change check: the document tile was
                        never broken, because both operands of its comparison
                        arrive prefixed. Not highlighted here is new
                        information, not a partial fix.
    mailing-readonly    #238 line 3. A *sent* mailing's body: the legacy
                        editor's readonly iframe. Reads only, so it runs first.
    mailing-editable    #238 lines 1 and 2. The mail designer, and the two
                        fields a save writes -- `body_arch` through
                        `getEditingValue`, and `body_html`, which
                        `commitChanges` inlines separately and which is the one
                        that **leaves the installation**. A run that reads back
                        only `body_arch` has measured half the fix.

Three judgements are deliberately **not** reimplemented here, because each has
a shape that would make a wrong record look clean:

- **Prefix escape is `adapter.is_prefix_escape`.** The shape a local version
  loses is the doubled prefix: still *under* the prefix, so "did it leave the
  prefix" answers no. `e2e_ingress_hand_checks.py` carries the same note
  because a review caught exactly that there, and every rule in this family
  prefixes a value that may already carry one.
- **A picture's verdict depends on the surface.** Under Ingress a root-relative
  `src` must resolve under the prefix; on the Public origin it must resolve at
  the origin root, and a prefix appearing there at all is a `sub_filter` that
  leaked out of the Ingress asset location (#237 check 3). The surface is a
  parameter, never a constant.
- **An Ingress prefix in a stored value is `e2e_collab_peer_snapshot_live`'s
  shape**, which is derived from the gateway's own `$safe_ingress_path` map and
  pinned against the template. A second regex here would drift away from the
  add-on with nothing noticing. Its `redact` comes with it, so no Supervisor
  token reaches a record even though what every check reads back is *which*
  prefix is in a value.

The pure parts are tested in `test_e2e_ingress_markup_live.py`. **The browser
steps are not**, the way `e2e_collab_peer_snapshot_live.py` says of its own:
they have never been executed against this host. Run the read-only checks first
(`read_only_first`) so a selector that moved costs nothing.

    ~/venvs/woow/bin/python odoo18ce/tests/e2e_ingress_markup_live.py \
      mailing-readonly --env-file /projects/Woow_ha_odoo/.env --db odoo_parity \
      --surface both --out markup.jsonl --run-id WOOW-MARKUP-<UTC timestamp>

Writing: `readonly-iframe` creates one scratch `project.task` and deletes it on
`--cleanup`; `codeview` writes `res.users.signature`; `mailing-editable` writes
one mailing's `body_arch` and `body_html`. Each marker names its run, so a
later reader can tell whose text it is. Every other check reads only. The
boundary is ADR 0012.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import e2e_menu_action_adapter as adapter  # noqa: E402
from e2e_collab_peer_snapshot_live import ingress_prefixes, redact  # noqa: E402
from e2e_menu_action_adapter import parse_env_file  # noqa: E402
from e2e_parity_shared_layers_live import TIMEOUT, Env, IngressSide, PublicSide  # noqa: E402

Surface = adapter.Surface

# Not `odoo-parity-evidence/v1`. That schema is one record per plan item with a
# column for each of the two surfaces, joined and diffed by `diff`. These checks
# are one interaction per record, judged against an expectation that *differs*
# by surface rather than against the other surface, and each carries a stored
# field value the parity schema has nowhere to put. Registered beside
# `woow.peer-snapshot.v1` in the parity plan's section 12; no run here feeds
# `conservation`.
EVIDENCE_SCHEMA = "woow.ingress-markup/v1"

# --- Verdicts -----------------------------------------------------------------

# One picture on one screen.
UNDER_PREFIX = "UNDER-PREFIX"        # Ingress: resolved under the Ingress prefix
AT_ORIGIN_ROOT = "AT-ORIGIN-ROOT"    # Public: resolved at the origin root
NOT_LOADED = "NOT-LOADED"            # resolved where it should, and never arrived
ESCAPED = "ESCAPED"                  # resolved somewhere this surface must not reach
ABSENT = "ABSENT"                    # no picture on the screen at all

PICTURE_VERDICTS = (UNDER_PREFIX, AT_ORIGIN_ROOT, NOT_LOADED, ESCAPED, ABSENT)

# Worst wins. `ABSENT` outranks `ESCAPED` because an escape is a measurement and
# an empty screen is not one: #240's row warns that a full-HTML value renders no
# editor and #237's that the `cssAssetId` branch renders a different target, and
# in both cases the check would otherwise pass while testing nothing.
PICTURE_SEVERITY = {
    UNDER_PREFIX: 0,
    AT_ORIGIN_ROOT: 0,
    NOT_LOADED: 1,
    ESCAPED: 2,
    ABSENT: 3,
}

PASSING = frozenset({UNDER_PREFIX, AT_ORIGIN_ROOT})

# One stored value.
CLEAN = "CLEAN"
PREFIX_STORED = "PREFIX-STORED"

NOT_RUN = "NOT-RUN"


def is_pass(verdict: str) -> bool:
    return verdict in PASSING


def expected_verdict(surface: Surface) -> str:
    """What a passing picture looks like on `surface`.

    The two surfaces want *different* things of the same root-relative `src`,
    which is why no check here is a two-surface diff: both sides being equal
    would be the failure.
    """
    return UNDER_PREFIX if surface is Surface.HA_INGRESS else AT_ORIGIN_ROOT


def picture_verdict(
    surface: Surface, origin: str, prefix: str | None, resolved: str | None, loaded: bool,
) -> str:
    """What one `<img>` says, on this surface.

    `resolved` is the browser's own `element.src` -- the attribute resolved
    against the page's base URL, which is the question, because a root-relative
    attribute is exactly what resolves against the Home Assistant root when
    nothing rewrote it. `loaded` is `complete && naturalWidth > 0`: a rule can
    prefix a URL correctly and still name nothing.
    """
    if not resolved:
        return ABSENT
    if adapter.is_prefix_escape(resolved, surface, origin, prefix):
        return ESCAPED
    if not loaded:
        return NOT_LOADED
    return expected_verdict(surface)


def screen_verdict(verdicts: Sequence[str]) -> str:
    """The worst picture on the screen, and `ABSENT` when there was none."""
    if not verdicts:
        return ABSENT
    return max(verdicts, key=lambda verdict: PICTURE_SEVERITY[verdict])


def stored_verdict(value: Any) -> tuple[str, int]:
    """Whether a value read back out of the database carries an Ingress prefix.

    An html field with no value comes back `False` from the ORM rather than an
    empty string, so the falsy cases are clean rather than an error.
    """
    if not value:
        return CLEAN, 0
    found = ingress_prefixes(value if isinstance(value, str) else str(value))
    return (PREFIX_STORED, len(found)) if found else (CLEAN, 0)


# --- The register's rows ------------------------------------------------------

CHECKS: dict[str, dict[str, Any]] = {
    "readonly-plain": {
        "issue": 237, "writes": False, "surfaces": ("ingress", "public"),
        "screen": "the html field's history dialog on the To-do form",
        "what": "a readonly html field on the plain path renders its picture through the surface",
    },
    "readonly-iframe": {
        "issue": 237, "writes": True, "surfaces": ("ingress", "public"),
        "screen": "a scratch to-do whose description is a full-HTML value",
        "what": "the same field on the hasFullHtml path, inside the sandboxed iframe",
    },
    "codeview": {
        "issue": 240, "writes": True, "surfaces": ("ingress", "public"),
        "screen": "the user signature in Preferences, with debug mode on",
        "what": "the code view toggled off re-inserts the record's markup under the prefix",
    },
    "media-image-todo": {
        "issue": 239, "writes": False, "surfaces": ("ingress", "public"),
        "screen": "the To-do description's media dialog, reopened on an existing image",
        "what": "the attachment the image came from is preselected",
    },
    "media-image-website": {
        "issue": 239, "writes": False, "surfaces": ("ingress", "public"),
        "screen": "the website editor's Replace Media dialog on an existing image",
        "what": "the same, on the path where data-original-src arrives prefixed",
    },
    "media-document-todo": {
        "issue": 239, "writes": False, "surfaces": ("ingress", "public"),
        "screen": "the To-do description's media dialog, reopened on a document link",
        "what": "a no-change check: both operands arrive prefixed, so it was never broken",
    },
    "mailing-readonly": {
        "issue": 238, "writes": False, "surfaces": ("ingress", "public"),
        "screen": "a sent mailing's body, the legacy editor's readonly iframe",
        "what": "the readonly iframe renders its pictures under the prefix",
    },
    "mailing-editable": {
        "issue": 238, "writes": True, "surfaces": ("ingress", "public"),
        "screen": "Email Marketing's mailing body, the mail designer",
        "what": "the designer loads under the prefix, and stores body_arch AND body_html root-relative",
    },
}


def read_only_first(names: Sequence[str]) -> list[str]:
    """The order a run takes them in: everything that writes nothing, first.

    ADR 0012 allows the writes, and running the cheap read-only checks first
    means a selector that moved is found before anything is stored.
    """
    return sorted(names, key=lambda name: (CHECKS[name]["writes"], name))


# --- The values the run seeds -------------------------------------------------

# `computeContainsComplexHTML()` turns `sandboxedPreview` on for any value whose
# parse yields a non-empty `<head>`, and `displayReadonly` then renders the
# viewer even while the field is editable. There is no view option for it and
# none exists to set, so the value is how the iframe path is reached.
FULL_HTML_VALUE = (
    "<html><head><style>body{margin:0}</style></head>"
    '<body><img src="/project_todo/static/img/todo_access.png"></body></html>'
)

# A *fragment*, deliberately. #240's row: a full-HTML value renders the readonly
# `HtmlViewer` instead of a `Wysiwyg`, so `this.editor` is `undefined` and
# `toggleCodeView` never reaches the assignment the rules patch -- the check
# would pass while testing nothing.
SIGNATURE_VALUE = '<p>x</p><img src="/web/image/res.company/1/logo" alt="logo"/>'

MARKER_PREFIX = "WOOW-MARKUP hand check"


def marker_for(run_id: str) -> str:
    """Text naming the run that typed it, so the host stays readable."""
    return "%s %s" % (MARKER_PREFIX, run_id)


def scratch_task_name(run_id: str) -> str:
    """The scratch to-do's name: this run's, and disposable.

    #243 is explicit that the iframe check must not use the onboarding to-do,
    because #235's checks read that record's stored `src` and this write would
    be read as their result.
    """
    return "WOOW scratch (delete me) %s" % run_id


# --- The record ---------------------------------------------------------------


def evidence_record(
    *,
    check: str,
    issue: int,
    run_id: str,
    database: str | None,
    target: str,
    surface: Surface,
    screen: str,
    pictures: Sequence[Mapping[str, Any]] | None,
    stored: Mapping[str, Any],
    signals: Mapping[str, int] | None = None,
    extra: Mapping[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """One check on one surface. `pictures` of None means it was never read.

    The verdict is the worse of what the screen showed and what the database
    kept, because #237 check 4 is the half that says the screen passing proves
    nothing about the write: a viewer has no save, so a changed value there
    means the prefix reached one.
    """
    stored_results = {}
    worst_stored = CLEAN
    for field, value in (stored or {}).items():
        verdict, count = stored_verdict(value)
        stored_results[field] = {"verdict": verdict, "prefixes": count}
        if verdict == PREFIX_STORED:
            worst_stored = PREFIX_STORED

    if pictures is None:
        verdict = NOT_RUN
    else:
        verdict = screen_verdict([picture["verdict"] for picture in pictures])
        if worst_stored == PREFIX_STORED:
            verdict = PREFIX_STORED

    record: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "run_id": run_id,
        "check": check,
        "issue": issue,
        "database": database,
        "target": target,
        "surface": surface.value,
        "screen": screen,
        "expected": expected_verdict(surface),
        "verdict": verdict,
        "stored_verdict": worst_stored if stored_results else NOT_RUN,
        "pictures": list(pictures) if pictures is not None else None,
        "stored": stored_results,
        # The values themselves, so a reader can see *what* was stored without
        # seeing a token. This is the one place a Supervisor secret could reach
        # the evidence, and the redaction is where it does not.
        "stored_values": redact(dict(stored or {}), {}),
        "signals": dict(signals or {}),
        "notes": notes,
    }
    if extra:
        record.update(redact(dict(extra), {}))
    return record


def summarise(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What `report` prints: the tally, the failures, and what never ran."""
    passed = failed = 0
    failures: list[str] = []
    seen: set[str] = set()
    for record in records:
        seen.add(record["check"])
        verdict = record["verdict"]
        if verdict == NOT_RUN:
            continue
        if is_pass(verdict):
            passed += 1
        else:
            failed += 1
            failures.append("%s/%s: %s" % (record["check"], record["surface"], verdict))
    return {
        "passed": passed,
        "failed": failed,
        "failures": sorted(failures),
        "not_run": sorted(set(CHECKS) - seen),
    }


# --- Selectors ----------------------------------------------------------------
#
# Every selector this driver uses, in one block, read from the pinned package
# (`ODOO_DEB_VERSION` in `odoo18ce/Dockerfile`) rather than guessed. A selector
# that moved is the most likely reason a first run fails, and `ABSENT` is the
# verdict that says so rather than passing quietly.

HTML_FIELD = ".o_field_html"
EDITABLE = HTML_FIELD + " .odoo-editor-editable"
READONLY_CONTENT = ".o_readonly"
VIEWER_IFRAME = HTML_FIELD + " iframe"
SAVE_BUTTON = ".o_form_button_save"
DISCARD_BUTTON = ".o_form_button_cancel"
UNSAVED = ".o_form_status_indicator_buttons:not(.invisible)"
DIALOG = ".o_dialog .modal-content"
PICTURES = "img"


def read_pictures(root, selector: str, side) -> list[dict[str, Any]]:
    """Every `<img>` under `selector`, and what each one says on this surface.

    Three readings per picture, and all three are needed: the attribute is what
    the rewrite produced, the resolved URL is what the browser made of it
    against the page's base (which is the whole question -- a root-relative
    attribute is exactly what resolves against the Home Assistant root when
    nothing rewrote it), and `loaded` is whether the byte arrived.
    """
    images = root.locator(selector)
    try:
        attributes = images.evaluate_all("els => els.map(e => e.getAttribute('src'))")
        resolved = images.evaluate_all("els => els.map(e => e.src)")
        loaded = images.evaluate_all("els => els.map(e => e.complete && e.naturalWidth > 0)")
    except Exception as error:  # noqa: BLE001 -- a frame that navigated away
        return [{"unreadable": type(error).__name__, "verdict": ABSENT}]
    pictures = []
    for index, source in enumerate(resolved):
        pictures.append({
            "attribute": side.env.mask(attributes[index] if index < len(attributes) else None),
            "resolved": side.env.mask(source),
            "loaded": bool(loaded[index]) if index < len(loaded) else False,
            "verdict": picture_verdict(
                side.surface, side.env.ha if side.surface is Surface.HA_INGRESS else side.env.public,
                side.env.prefix if side.surface is Surface.HA_INGRESS else None,
                source, bool(loaded[index]) if index < len(loaded) else False,
            ),
        })
    return pictures


def viewer_frame(side):
    """The readonly viewer's iframe content, or None when it rendered no iframe.

    `HtmlViewer` picks its path at `get showIframe()` (`hasFullHtml ||
    cssAssetId`), so the absence of an iframe here is a reading: it means the
    value did not take the path the check is about.
    """
    handles = side.root.locator(VIEWER_IFRAME).element_handles()
    for handle in handles:
        frame = handle.content_frame()
        if frame is not None:
            return frame
    return None


def open_one(env: Env, browser, surface: Surface, *, viewport=(1920, 1080)):
    """One surface, started. `PublicSide` does not need the Ingress prefix.

    `open_sides` starts Ingress first because the prefix it learns is what the
    `Masker` redacts with. A public-only run has none to redact, and
    `is_prefix_escape` on the Public surface asks only whether the literal
    `/api/hassio_ingress/` appears -- it needs no token to answer.
    """
    side = (IngressSide if surface is Surface.HA_INGRESS else PublicSide)(env, browser, viewport=viewport)
    side.start()
    return side


# --- The database, over the session's own RPC ---------------------------------
#
# Read back through the *same* session that took the interaction, so the value
# judged is the one that session's save produced. `#256` settled that a reading
# a run needs about its own effect is the session's own RPC and not an `ssh`
# into the host.


def read_field(side, model: str, record_id: int, field: str) -> Any:
    [record] = side.rpc(model, "read", [[record_id], [field]])
    return record.get(field)


def write_field(side, model: str, record_id: int, field: str, value: Any) -> None:
    side.rpc(model, "write", [[record_id], {field: value}])


def seed_scratch_task(side, run_id: str) -> int:
    """A to-do of this run's own, holding the full-HTML value.

    A to-do is a `project.task` with no project (`e2e_collab_peer_snapshot_live`
    finds one the same way). It is a **new** record rather than the onboarding
    to-do on purpose: #235's checks read that record's stored `src`, and this
    write would be read as their result.
    """
    return side.rpc("project.task", "create", [{
        "name": scratch_task_name(run_id),
        "description": FULL_HTML_VALUE,
        "project_id": False,
    }])


def delete_scratch_task(side, task_id: int) -> None:
    side.rpc("project.task", "unlink", [[task_id]])


def current_user_id(side) -> int:
    """The logged-in user, found by the login the run signed in with."""
    ids = side.rpc("res.users", "search", [[["login", "=", side.env.login]]], {"limit": 1})
    if not ids:
        raise RuntimeError("no res.users row for the configured login")
    return ids[0]


def sent_mailing_id(side) -> int | None:
    """A mailing whose body renders through the legacy editor's readonly iframe.

    The body field is `readonly="state in ('sending','done')"`, so the readonly
    path needs a mailing in one of those states. None of them is created here --
    sending a mailing is outside what a parity run may do -- so a host with no
    sent mailing records this check as unreachable rather than sending one.
    """
    ids = side.rpc("mailing.mailing", "search",
                   [[["state", "in", ["sending", "done"]]]], {"limit": 1})
    return ids[0] if ids else None


def editable_mailing_id(side) -> int | None:
    ids = side.rpc("mailing.mailing", "search",
                   [[["state", "in", ["draft", "in_queue"]]]], {"limit": 1})
    return ids[0] if ids else None


def onboarding_todo_id(side) -> int | None:
    ids = side.rpc("project.task", "search", [[["project_id", "=", False]]], {"limit": 1})
    return ids[0] if ids else None


def session_database(side) -> str | None:
    """The database this session ended up on, read rather than assumed."""
    try:
        return side.root.evaluate("() => (odoo.info && odoo.info.db) || null")
    except Exception:  # noqa: BLE001 -- no web client on the current page
        return None


# --- Running one check on one surface -----------------------------------------


SURFACES = {"ingress": Surface.HA_INGRESS, "public": Surface.PUBLIC}


def handler_for(check: str):
    """The `do_` function for a check name, by the one naming rule.

    `test_every_check_the_parser_takes_has_a_branch_and_a_row` holds the parser,
    this lookup and `CHECKS` together, so a check cannot be added to the
    register without a branch to run it.
    """
    return globals()["do_" + check.replace("-", "_")]


def run_check(
    check: str,
    surfaces: Sequence[str],
    *,
    db: str,
    out_path: str,
    run_id: str,
    task_id: int | None = None,
    mailing_id: int | None = None,
    cleanup: bool = False,
    headed: bool = False,
) -> int:
    from playwright.sync_api import sync_playwright

    row = CHECKS[check]
    handler = handler_for(check)
    records: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        try:
            for name in surfaces:
                surface = SURFACES[name]
                env = Env(db)
                side = None
                try:
                    side = open_one(env, browser, surface)
                    outcome: dict[str, Any] = {
                        "screen": row["screen"], "pictures": None, "stored": {}, "notes": "",
                    }
                    mark = side.recorder.mark() if side.recorder else None
                    try:
                        outcome.update(handler(
                            side, run_id, task_id=task_id, mailing_id=mailing_id, cleanup=cleanup,
                        ) or {})
                    except Exception as error:  # noqa: BLE001 -- a step that could not run
                        # A step that threw is `NOT-RUN` with its reason, never a
                        # pass and never a silent gap: `pictures` stays None.
                        outcome["notes"] = "%s: %s" % (
                            type(error).__name__, adapter.sanitize_diagnostic(str(error)))
                    signals = side.recorder.since(mark) if (side.recorder and mark) else {}
                    record = evidence_record(
                        check=check, issue=row["issue"], run_id=run_id,
                        database=session_database(side) or db,
                        target=env.target, surface=surface,
                        screen=outcome.get("screen") or row["screen"],
                        pictures=outcome.get("pictures"),
                        stored=outcome.get("stored") or {},
                        signals=signals,
                        extra=outcome.get("extra"),
                        notes=outcome.get("notes", ""),
                    )
                    records.append(record)
                finally:
                    if side is not None:
                        side.close()
        finally:
            browser.close()

    with open(out_path, "a", encoding="utf-8") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    for record in records:
        print("%s/%s %s  (expected %s)" % (
            record["check"], record["surface"], record["verdict"], record["expected"]))
    return 0 if all(is_pass(record["verdict"]) for record in records) else 1


def do_report(records_path: str) -> int:
    with open(records_path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    summary = summarise(records)
    print("%d passed, %d failed" % (summary["passed"], summary["failed"]))
    for failure in summary["failures"]:
        print("  FAIL " + failure)
    if summary["not_run"]:
        print("  not run: " + ", ".join(summary["not_run"]))
    # The register's own escalation hooks, applied to what was read rather than
    # left for a reader to apply. #239 cannot escalate -- nothing it measures is
    # stored -- and #237 check 4 is the one that can, on any check at all.
    stored = [record for record in records if record.get("stored_verdict") == PREFIX_STORED]
    print("stored_prefix_found=%s" % ("yes" if stored else "no"))
    for record in stored:
        print("  PREFIX STORED by %s/%s in %s" % (
            record["check"], record["surface"], ", ".join(sorted(record.get("stored") or {}))))
    return 1 if (summary["failed"] or stored) else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in read_only_first(list(CHECKS)):
        sub = commands.add_parser(name, help=CHECKS[name]["what"])
        sub.add_argument("--env-file", help="read unset credentials from this NAME=value file")
        sub.add_argument("--db", required=True, help="the database the surfaces must serve")
        sub.add_argument("--out", required=True, help="JSONL evidence file; appended to")
        sub.add_argument("--run-id", required=True, help="the marker the records are named with")
        sub.add_argument("--surface", default="both", choices=["ingress", "public", "both"])
        sub.add_argument("--task-id", type=int, help="reuse a to-do instead of finding or creating one")
        sub.add_argument("--mailing-id", type=int, help="reuse a mailing instead of finding one")
        sub.add_argument("--cleanup", action="store_true",
                         help="delete what this check created before it returns")
        sub.add_argument("--headed", action="store_true")
    report = commands.add_parser("report", help="tally one or more runs' records")
    report.add_argument("records")
    args = parser.parse_args(argv)

    if args.command == "report":
        return do_report(args.records)
    if getattr(args, "env_file", None):
        with open(args.env_file, encoding="utf-8") as handle:
            parse_env_file(handle, os.environ)
    surfaces = ["ingress", "public"] if args.surface == "both" else [args.surface]
    surfaces = [name for name in surfaces if name in CHECKS[args.command]["surfaces"]]
    return run_check(
        args.command, surfaces, db=args.db, out_path=args.out, run_id=args.run_id,
        task_id=args.task_id, mailing_id=args.mailing_id, cleanup=args.cleanup, headed=args.headed,
    )


if __name__ == "__main__":
    raise SystemExit(main())


# --- #237: the readonly html field --------------------------------------------


def do_readonly_iframe(side, run_id: str, *, task_id=None, cleanup=False, **_) -> dict[str, Any]:
    """#237 check 2: the `hasFullHtml` path, inside the sandboxed iframe.

    There is no view option for this path and none exists to set.
    `computeContainsComplexHTML()` turns `sandboxedPreview` on for any value
    whose parse yields a non-empty `<head>`, and `displayReadonly` then renders
    the viewer even while the field is editable -- so the *value* is how the
    path is reached, which is why this check seeds one.

    Check 4 rides along: the field is read back afterwards, and a viewer has no
    save, so a value that changed means the prefix reached a write and the "no
    `OUT` half" decision is wrong.
    """
    created = None
    if task_id is None:
        task_id = created = seed_scratch_task(side, run_id)
    side.goto("/odoo/project.task/%d" % task_id)
    side.wait_webclient()
    side.close_chat_windows()
    side.settle(2000)

    frame = viewer_frame(side)
    extra: dict[str, Any] = {
        "task_id": task_id,
        "created_task": created,
        # The viewer is only on the iframe path when it rendered an iframe. Its
        # absence is a reading, not a retry: it says the value did not take the
        # path this check is about.
        "rendered_iframe": frame is not None,
    }
    if frame is None:
        pictures = None
        notes = ("the html field rendered no iframe, so the value did not take the "
                 "hasFullHtml path; nothing about #237 check 2 was measured")
    else:
        handle = side.root.locator(VIEWER_IFRAME).first
        # `t-att-sandbox` evaluates to this exact string on the `hasFullHtml`
        # branch and to `false` on the `cssAssetId`-only one, so the attribute
        # also says which branch rendered.
        extra["sandbox"] = handle.get_attribute("sandbox")
        pictures = read_pictures(frame, PICTURES, side)
        notes = ""

    stored = {"project.task.description": read_field(side, "project.task", task_id, "description")}
    if cleanup and created is not None:
        delete_scratch_task(side, created)
        extra["deleted_task"] = created
    return {"screen": "/odoo/project.task/%d" % task_id, "pictures": pictures,
            "stored": stored, "extra": extra, "notes": notes}


# --- #238: the legacy web_editor ----------------------------------------------


# The mailing body is `body_arch` on the form; Odoo renders a field wrapper
# carrying the field's name, which is how this driver reaches a widget it has no
# class name for.
MAILING_BODY = '.o_field_widget[name="body_arch"]'


def do_mailing_readonly(side, run_id: str, *, mailing_id=None, **_) -> dict[str, Any]:
    """#238 line 3: a *sent* mailing's body, the legacy readonly iframe.

    Rules 3, 4 and 5 are `_setupReadonlyIframe`'s three branches. The body field
    is `readonly="state in ('sending','done')"`, so this needs a mailing in one
    of those states -- and this run does not create one, because sending a
    mailing is outside what a parity run may do. No save, nothing stored, which
    is why it goes first.
    """
    if mailing_id is None:
        mailing_id = sent_mailing_id(side)
    if mailing_id is None:
        return {"pictures": None, "notes":
                "no mailing.mailing in state sending or done on this database, and this "
                "run does not send one: #238's readonly iframe is unreachable here"}
    side.goto("/odoo/mailing.mailing/%d" % mailing_id)
    side.wait_webclient()
    side.close_chat_windows()
    side.settle(2000)

    extra: dict[str, Any] = {"mailing_id": mailing_id}
    handles = side.root.locator(MAILING_BODY + " iframe").element_handles()
    frame = next((handle.content_frame() for handle in handles if handle.content_frame()), None)
    extra["rendered_iframe"] = frame is not None
    if frame is None:
        return {"screen": "/odoo/mailing.mailing/%d" % mailing_id, "pictures": None, "extra": extra,
                "notes": "the mailing body rendered no iframe; the readonly path was not reached"}
    pictures = read_pictures(frame, PICTURES, side)
    # Read only: the two fields are recorded so the evidence says what the body
    # held, not because this check could have changed them.
    stored = {
        "mailing.mailing.body_arch": read_field(side, "mailing.mailing", mailing_id, "body_arch"),
        "mailing.mailing.body_html": read_field(side, "mailing.mailing", mailing_id, "body_html"),
    }
    return {"screen": "/odoo/mailing.mailing/%d" % mailing_id, "pictures": pictures,
            "stored": stored, "extra": extra}
