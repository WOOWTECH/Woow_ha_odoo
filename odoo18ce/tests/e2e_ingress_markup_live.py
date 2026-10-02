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

**The ambient rows a run leaves are counted by the run** (#256, #264): each
surface counts `website.track` and `website.visitor` over its own session's RPC
after the login and again on the way out, and the delta is appended beside the
records under their own name with `.ambient.json` for its extension
(`markup.jsonl` -> `markup.ambient.json`) -- one line per surface per
invocation, because the records append the same way. Counts only, no URL and no
visitor identity. `media-image-website` is why this driver needs the figure:
it opens the website editor, whose preview iframes load tracked website pages,
so those rows are certainly written -- #243's evidence had to read an absolute
count on the host afterwards and say that no delta could be stated. The
denominator is every document GET the session's browser context made under its
base, which is the only way to count a navigation the editor made for itself.
It is accounting and not a verdict: `diff` never reads it, `read_records`
refuses its schema, and the conservation tally does not move for it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

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
# A `data:` or `blob:` source, or one on a third-party origin. The prefix has no
# claim on it, so neither surface's expectation applies -- and saying
# `UNDER-PREFIX` of it would assert something nobody checked. Routine in the mail
# designer and the website preview, which is why it is named rather than folded
# into a pass.
NOT_A_PREFIX_QUESTION = "NOT-A-PREFIX-QUESTION"

PICTURE_VERDICTS = (UNDER_PREFIX, AT_ORIGIN_ROOT, NOT_LOADED, ESCAPED, ABSENT,
                    NOT_A_PREFIX_QUESTION)

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
    # Ranked, but `screen_verdict` drops it before ranking: it is neither a pass
    # nor a failure, it is a picture that was not this check's subject.
    NOT_A_PREFIX_QUESTION: 0,
}

PASSING = frozenset({UNDER_PREFIX, AT_ORIGIN_ROOT})

# One stored value.
CLEAN = "CLEAN"
PREFIX_STORED = "PREFIX-STORED"

NOT_RUN = "NOT-RUN"

# The names `evidence_record` owns. A flow's own readings are merged flat beside
# them, so a collision would let one quietly replace a verdict with a reading;
# `evidence_record` refuses instead of letting the record lie.
RESERVED_RECORD_KEYS = frozenset({
    "schema", "run_id", "check", "issue", "database", "target", "surface", "screen",
    "expected", "verdict", "stored_verdict", "pictures", "stored", "stored_values",
    "signals", "notes",
})


def is_pass(verdict: str) -> bool:
    return verdict in PASSING


def expected_verdict(surface: Surface) -> str:
    """What a passing picture looks like on `surface`.

    The two surfaces want *different* things of the same root-relative `src`,
    which is why no check here is a two-surface diff: both sides being equal
    would be the failure.
    """
    return UNDER_PREFIX if surface is Surface.HA_INGRESS else AT_ORIGIN_ROOT


def is_prefix_question(url: str, surface: Surface, origin: str) -> bool:
    """Whether the prefix has any claim on `url` at all.

    `adapter.is_prefix_escape` returns `False` both for "this is fine" and for
    "this is none of my business" -- a non-http scheme (`:1160`) and a different
    netloc (`:1164`) -- so on its own it cannot tell a prefixed picture from a
    `data:` URI. The netloc comparison is the adapter's own `_netloc`, not a
    second one written here, so the two functions agree about what same-origin
    means by construction.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https", "ws", "wss"):
        return False
    return adapter._netloc(url) == adapter._netloc(origin)


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
    if not is_prefix_question(resolved, surface, origin):
        return NOT_A_PREFIX_QUESTION
    if not loaded:
        return NOT_LOADED
    return expected_verdict(surface)


def screen_verdict(verdicts: Sequence[str]) -> str:
    """The worst picture the prefix had a claim on, and `ABSENT` when none.

    Pictures that were never a prefix question are dropped rather than ranked: a
    `data:` URI beside a prefixed one must not outvote it, and a screen whose
    pictures were *all* `data:` URIs measured nothing, which is `ABSENT` for the
    same reason an empty screen is.
    """
    judged = [verdict for verdict in verdicts if verdict != NOT_A_PREFIX_QUESTION]
    if not judged:
        return ABSENT
    return max(judged, key=lambda verdict: PICTURE_SEVERITY[verdict])


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
SIGNATURE_VALUE_TEMPLATE = (
    '<p>%s</p><img src="/web/image/res.company/1/logo" alt="logo"/>'
)


def signature_value(run_id: str) -> str:
    """The seeded signature, naming the run that seeded it.

    `docs/agents/live-tier.md` wants every writing step marked with its run id so
    the host stays readable and a later reader can tell whose text is whose. This
    value replaces a real user's signature, so that matters more here than it does
    for a scratch record that can simply be deleted.
    """
    return SIGNATURE_VALUE_TEMPLATE % marker_for(run_id)


# Kept for the Static tier's shape assertions; the run uses `signature_value`.
SIGNATURE_VALUE = SIGNATURE_VALUE_TEMPLATE % "x"

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

    if worst_stored == PREFIX_STORED:
        # Before the `pictures is None` branch, deliberately. A prefix that
        # reached a write is the worst thing this run can find, and a check whose
        # screen could not be read still read the database -- reporting that as
        # `NOT-RUN` would drop it out of the tally entirely, since `summarise`
        # skips `NOT-RUN` and the check was seen so it is not in `not_run` either.
        verdict = PREFIX_STORED
    elif pictures is None:
        verdict = NOT_RUN
    else:
        verdict = screen_verdict([picture["verdict"] for picture in pictures])

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
        collisions = sorted(set(extra) & RESERVED_RECORD_KEYS)
        if collisions:
            raise ValueError("a check's extra readings may not use the record's own "
                             "names: %s" % ", ".join(collisions))
        record.update(redact(dict(extra), {}))
    return record


def summarise(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What `report` prints: the tally, the failures, and what never ran.

    **The last record for a check and surface is its verdict.** A run keeps every
    attempt -- a past reading is what it recorded -- and this run retried five of
    the eight checks after finding a fixture or a selector wrong. Tallying every
    attempt would report a fixed check as a failure for ever.
    """
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in records:
        latest[(record["check"], record["surface"])] = record
    passed = failed = 0
    failures: list[str] = []
    seen: set[str] = set()
    for record in latest.values():
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
        # How many readings were taken to get there, so a retried run is legible
        # as retried rather than looking like a clean first pass.
        "attempts": len(records),
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


def wait_for_editable(side, selector: str = EDITABLE) -> bool:
    """Wait for the html field's editable to mount before reading it.

    `wait_webclient()` returns when the action manager has rendered, which is
    before the editor has mounted and filled the field. Without this wait a
    reading taken straight afterwards found no `<img>` on a record that stores
    one -- a race reported as "the description holds no image", which is the
    same sentence a genuinely empty record produces. `open_todo` in
    `e2e_collab_peer_snapshot_live` waits the same way.
    """
    try:
        side.root.locator(selector).first.wait_for(timeout=TIMEOUT)
        return True
    except Exception:  # noqa: BLE001 -- a form that genuinely has no editable
        return False


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


def seed_scratch_template(side, run_id: str) -> int:
    """A scratch `mail.template` holding the full-HTML value.

    `body_html` is `sanitize_tags=False`, so unlike `project.task.description` it
    keeps the `<head>` that `computeContainsComplexHTML()` needs. `model_id` is
    required, so it is pointed at `res.partner`.
    """
    model_ids = side.rpc("ir.model", "search", [[["model", "=", "res.partner"]]], {"limit": 1})
    return side.rpc("mail.template", "create", [{
        "name": scratch_task_name(run_id),
        "model_id": model_ids[0],
        "subject": marker_for(run_id),
        "body_html": FULL_HTML_VALUE,
    }])


def delete_scratch_task(side, task_id: int) -> None:
    side.rpc("project.task", "unlink", [[task_id]])


def pick_help_action(side) -> int:
    """An `ir.actions.act_window` whose `help` this check may borrow.

    Chosen by lowest id for repeatability, and its prior value is restored. The
    field is #158's, and the view that renders it sets `codeview`.
    """
    ids = side.rpc("ir.actions.act_window", "search", [[]], {"limit": 1, "order": "id asc"})
    if not ids:
        raise RuntimeError("no ir.actions.act_window on this database")
    return ids[0]


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
    # Which surfaces have a record on disk, so the surface-failure fallback below
    # cannot write a second, contradicting line for one of them.
    kept: set[str] = set()
    # An ambient figure that could not be written, held until every surface has
    # run. `ambient_accounting` raises when the figure is a passing run's only
    # failure (#256), and raising it where it arrives would cost the *other*
    # surface its measurement -- a run of `--surface both` would open the public
    # origin never, record nothing for it, and exit by traceback.
    unaccounted: list[Exception] = []

    def keep(record: dict[str, Any], side=None) -> None:
        """Append one record to `--out` the moment it exists.

        Buffering them to the end loses the evidence for writes already made when
        a *later* surface fails -- and this driver writes. `Env.mask` runs over the
        finished record rather than only over the picture URLs: `redact` removes
        the Supervisor token and nothing else, while the values read back here are
        production field values that carry absolute base URLs and `access_token`
        path tokens (`mailing.mailing.body_html` especially).
        """
        masked = side.env.mask(record) if side is not None else record
        with open(out_path, "a", encoding="utf-8") as out:
            out.write(json.dumps(masked, ensure_ascii=False, sort_keys=True) + "\n")
        # After the write, both of them: `kept` is read as "this surface's record
        # is on disk" and `records` as "this is what the run recorded", and a line
        # the file never got is neither.
        records.append(masked)
        kept.add(masked["surface"])
        print("%s/%s %s  (expected %s)" % (
            masked["check"], masked["surface"], masked["verdict"], masked["expected"]))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        try:
            for name in surfaces:
                surface = SURFACES[name]
                env = Env(db)
                side = None
                try:
                    side = open_one(env, browser, surface)
                    # This surface's ambient-row figure, counted by the run itself
                    # (#256, #264) and appended beside the records as
                    # `markup.ambient.json`. The window opens here, after the
                    # login, because the counts go over this session's own RPC --
                    # and it is per surface for the same reason the records are:
                    # each surface has its own session, and a delta over a
                    # database-wide count cannot be split between two of them
                    # afterwards. `media-image-website` is why this driver needs
                    # the figure at all: it opens the website editor, whose
                    # preview iframes load tracked pages.
                    with adapter.ambient_accounting(
                        adapter.SessionAmbientDriver(side, mask=env.mask),
                        adapter.RunInfo(run_id=run_id, target=env.target,
                                        database=session_database(side) or db),
                        surface, out_path, command=check, append=True,
                        navigation_basis=adapter.AMBIENT_BASIS_DOCUMENTS,
                    ):
                        outcome: dict[str, Any] = {
                            "screen": row["screen"], "pictures": None, "stored": {}, "notes": "",
                        }
                        mark = side.recorder.mark() if side.recorder else None
                        try:
                            outcome.update(handler(
                                side, run_id, task_id=task_id, mailing_id=mailing_id,
                                cleanup=cleanup,
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
                        keep(record, side)
                except Exception as error:  # noqa: BLE001 -- the surface itself failed
                    # `open_one`, `side.close()` and `evidence_record`'s own
                    # collision guard all sit outside the handler's `try`. Letting
                    # one escape would have abandoned the whole run with `--out`
                    # never opened, leaving a host this driver had already written
                    # to with no evidence line accounting for it.
                    if surface.value in kept:
                        # This surface's record is on disk, so the failure is in
                        # something after it -- the ambient accounting, which
                        # raises when it is a passing run's only failure (#256). A
                        # second line for the same surface would be read as this
                        # surface's verdict by `summarise`, which takes the last,
                        # so the figure's failure is held and raised after the
                        # loop instead.
                        unaccounted.append(error)
                        continue
                    keep({
                        "schema": EVIDENCE_SCHEMA, "run_id": run_id, "check": check,
                        "issue": row["issue"], "database": db, "target": os.environ.get(
                            "PARITY_TARGET", "local"),
                        "surface": surface.value, "screen": row["screen"],
                        "expected": expected_verdict(surface), "verdict": NOT_RUN,
                        "stored_verdict": NOT_RUN, "pictures": None, "stored": {},
                        "stored_values": {}, "signals": {},
                        "notes": "the surface could not be driven: %s: %s" % (
                            type(error).__name__, adapter.sanitize_diagnostic(str(error))),
                    })
                finally:
                    if side is not None:
                        try:
                            side.close()
                        except Exception:  # noqa: BLE001 -- a context already gone
                            pass
        finally:
            browser.close()

    if unaccounted:
        # Every surface has run and every record it took is on disk; what is left
        # is a figure that could not be written, and #256 exists so that is not
        # swallowed. The first one is raised and the rest are named, because an
        # operator needs the reason and not a count of reasons.
        for later in unaccounted[1:]:
            print("a further ambient figure could not be written: %s"
                  % adapter.sanitize_diagnostic(str(later)), file=sys.stderr)
        raise unaccounted[0]
    if not records:
        print("no record was written: nothing ran")
        return 1
    return 0 if all(is_pass(record["verdict"]) for record in records) else 1


def do_report(records_path: str) -> int:
    with open(records_path, encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    summary = summarise(records)
    print("%d passed, %d failed (from %d recorded attempt(s); the last record for a "
          "check and surface is its verdict)" % (
              summary["passed"], summary["failed"], summary["attempts"]))
    for failure in summary["failures"]:
        print("  FAIL " + failure)
    if summary["not_run"]:
        print("  not run: " + ", ".join(summary["not_run"]))
    # The register's own escalation hooks, applied to what was read rather than
    # left for a reader to apply. #239 cannot escalate -- nothing it measures is
    # stored -- and #237 check 4 is the one that can, on any check at all.
    stored = [record for record in records if record.get("stored_verdict") == PREFIX_STORED]
    # Every attempt is checked for a stored prefix, not just the last: a prefix
    # that reached a write happened even if a later attempt was clean.
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
    if not surfaces:
        # Otherwise the loop never runs, `all(...)` over an empty list is True and
        # a run that measured nothing exits 0 -- the one outcome this whole verdict
        # scheme exists to refuse.
        parser.error("%s does not run on surface %r; it runs on %s" % (
            args.command, args.surface, ", ".join(CHECKS[args.command]["surfaces"])))
    return run_check(
        args.command, surfaces, db=args.db, out_path=args.out, run_id=args.run_id,
        task_id=args.task_id, mailing_id=args.mailing_id, cleanup=args.cleanup, headed=args.headed,
    )



# --- #237: the readonly html field --------------------------------------------


def do_readonly_iframe(side, run_id: str, *, task_id=None, cleanup=False, **_) -> dict[str, Any]:
    """#237 check 2: the `hasFullHtml` path, inside the sandboxed iframe.

    There is no view option for this path and none exists to set.
    `computeContainsComplexHTML()` turns `sandboxedPreview` on for any value
    whose parse yields a non-empty `<head>`, and `displayReadonly` then renders
    the viewer even while the field is editable -- so the *value* is how the path
    is reached, which is why this check seeds one.

    **Not on `project.task.description`, which is the field #237's row names.**
    That field is `sanitize_tags=True`, so the ORM strips `<html>`, `<head>` and
    `<style>` on write: a full-HTML value seeded there comes back as the bare
    `<img>`, `computeContainsComplexHTML()` never sees a `<head>`, and the field
    renders the plain path -- which is check 1's screen, measured twice. Measured
    on this host: the seeded value read back as
    `<img src="/project_todo/static/img/todo_access.png">` and
    `rendered_iframe` was false on both surfaces.

    `mail.template.body_html` is `sanitize_tags=False`, so it keeps a full-HTML
    value, and it renders through `html_mail` -- a subclass of the same
    `HtmlField`. It is the field #240's row warns is "the value most likely to be
    full HTML" for exactly this reason. A scratch template is created and deleted
    rather than an existing one edited.

    Check 4 rides along: the field is read back afterwards, and a viewer has no
    save, so a value that changed means the prefix reached a write and the "no
    `OUT` half" decision is wrong.
    """
    created = None
    if task_id is None:
        task_id = created = seed_scratch_template(side, run_id)
    side.goto("/odoo/mail.template/%d" % task_id)
    side.wait_webclient()
    side.close_chat_windows()
    side.settle(2000)

    frame = viewer_frame(side)
    extra: dict[str, Any] = {
        "record_id": task_id,  # a mail.template id on this check, not a task
        "created_template": created,
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

    stored = {"mail.template.body_html": read_field(side, "mail.template", task_id, "body_html")}
    if cleanup and created is not None:
        side.rpc("mail.template", "unlink", [[created]])
        extra["deleted_template"] = created
    return {"screen": "/odoo/mail.template/%d" % task_id, "pictures": pictures,
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


# --- #240: the code view round trip -------------------------------------------

# `base.action_res_users_my` is `target="new"`, so Preferences is a dialog over
# whatever is on screen (`base/views/res_users_views.xml:506-512`), and its
# footer carries its own save -- `.o_form_button_save` is not on it.
# **Not the user signature, which is the screen #240's row names.** Measured on
# this host: that field renders through `o_field_html_mail` -- the `html_mail`
# subclass -- and its editor comes up **empty**, showing the `o-we-hint`
# placeholder, even with a fragment value present in the record. With an empty
# editable there is no text to select, so the floating toolbar is never raised and
# the `codeview` group never renders. #240's row picked the signature *because*
# `html_mail` was the thing to avoid (a mail body is the value most likely to be
# full HTML); on this build the signature is served by that widget anyway.
#
# `ir.actions.act_window.help` is the other `codeview` view
# (`base/views/ir_actions_views.xml:230`, #158's field). It is a plain `html`
# field on the current editor, `sanitize_tags=True` so it keeps a fragment and
# cannot become a sandboxed preview, and there are 707 records to pick from.
HELP_FIELD = '.o_field_html[name="help"]'
HELP_EDITABLE = HELP_FIELD + " .odoo-editor-editable"
SIGNATURE_FIELD = '.o_field_html[name="signature"]'
SIGNATURE_EDITABLE = SIGNATURE_FIELD + " .odoo-editor-editable"

# Turning the code view **on** for a fragment value is a toolbar item, not the
# button beside the field: `html_field.xml:26` renders `#codeview-btn-group` only
# when `state.showCodeView` is already true or the value is a sandboxed preview,
# and `html_field.js:292-310` registers the toggle as a toolbar command with
# `icon: "fa-code"` whose button carries `name="codeview"`
# (`main/toolbar/toolbar.xml`). So: select text to raise the floating toolbar,
# click it to go on, and click the field's own button to come back off.
CODEVIEW_TOOLBAR_BUTTON = '.o-we-toolbar button[name="codeview"]'
CODEVIEW_OFF_BUTTON = "#codeview-btn-group .o_codeview_btn"
CODEVIEW_TEXTAREA = "textarea.o_codeview"


def do_codeview(side, run_id: str, *, cleanup=False, **_) -> dict[str, Any]:
    """#240: the code view toggled off re-inserts the record's markup.

    The screen is the user signature in **Preferences** with debug mode on, and
    the field is a *fragment* on purpose: `computeContainsComplexHTML()` turns
    `sandboxedPreview` on for a value whose parse yields a non-empty `<head>`,
    the field then renders the readonly `HtmlViewer` instead of a `Wysiwyg`, and
    `this.editor` is `undefined` -- so `toggleCodeView` never reaches the
    assignment at `html_field.js:236` that the rules patch. A full-HTML value
    here would pass while testing nothing.

    Two halves, both recorded: the picture loads under the prefix after the
    toggle, and `res.users.signature` is still root-relative after the save.
    """
    uid = pick_help_action(side)
    before = read_field(side, "ir.actions.act_window", uid, "help")
    extra: dict[str, Any] = {"action_id": uid, "help_before": redact(before or "", {})}
    # Seeded over RPC rather than typed, so the value under test is exactly the
    # one the Static tier measured and the check does not also depend on the
    # code view's own typing working.
    write_field(side, "ir.actions.act_window", uid, "help", signature_value(run_id))
    try:
        return _codeview_after_seeding(side, run_id, uid, before, extra, cleanup=cleanup)
    except Exception as error:
        # The partial readings are the whole value of a failed attempt -- was debug
        # on, did the toolbar appear, was there a selection -- and `run_check`
        # discards a handler's return value when it raises. So restore, then
        # return them as a NOT-RUN outcome rather than re-raising and losing them.
        try:
            write_field(side, "ir.actions.act_window", uid, "help", before or False)
            extra["help_restored"] = True
        except Exception:  # noqa: BLE001 -- the session itself may be gone
            extra["help_restored"] = False
        return {"screen": "/odoo/ir.actions.act_window/%d (help, debug)" % uid, "pictures": None,
                "stored": {}, "extra": extra,
                "notes": "%s: %s" % (type(error).__name__,
                                     adapter.sanitize_diagnostic(str(error))[:300])}
    except BaseException:
        # The interrupt path: Ctrl+C, a kill, a timeout that raises outside
        # `Exception`. A real user's signature was replaced by this check before any
        # browser step, so it is put back here too and the interrupt then continues.
        # `--cleanup` does not cover this; it is only reached on the success path.
        try:
            write_field(side, "ir.actions.act_window", uid, "help", before or False)
        except Exception:  # noqa: BLE001 -- the session itself may be gone
            pass
        raise


def _codeview_after_seeding(side, run_id, uid, before, extra, *, cleanup=False) -> dict[str, Any]:
    """The browser half of `do_codeview`, split out so the seed has a restore."""
    # Debug mode first: `codeview` is `Boolean(odoo.debug && options.codeview)`
    # (`html_field.js:375`), so without it the toolbar item is never registered
    # and there is nothing to toggle.
    side.goto("/odoo?debug=1")
    side.wait_webclient()
    extra["debug"] = side.root.evaluate("() => (window.odoo && odoo.debug) || ''")
    # `?debug=1` goes on **this** navigation, not only on the `/odoo` one before
    # it. Measured on this host: after `/odoo?debug=1` the next page reported
    # `odoo.debug === ""`, so the flag did not survive the navigation, the
    # `codeview` command was never registered (`html_field.js:375` needs
    # `odoo.debug && options.codeview`), and the floating toolbar came up with
    # seven groups and no code view -- which reads exactly like a missing button.
    side.goto("/odoo/ir.actions.act_window/%d?debug=1" % uid)
    side.wait_webclient()
    side.settle(1500)

    editable = side.root.locator(HELP_EDITABLE).first
    editable.wait_for(timeout=TIMEOUT)
    # The toolbar is a selection toolbar; it is not in the DOM until there is one.
    editable.click()
    # A *text* selection, made with the keyboard. A programmatic `Range` fires
    # `selectionchange`, but the floating toolbar is raised from the editor's own
    # pointer and key handling, so a JS-only selection left it absent for the full
    # 60 s wait. `Home` then `Shift+End` selects the first line's text and nothing
    # else -- deliberately not the whole editable, because the toolbar hides a
    # group whose `namespace` does not match the selection's
    # (`toolbar_plugin.js:393`) and the `codeview` group declares none, so an
    # image in the selection would put it in the `image` namespace and hide the
    # one button this check needs.
    # A **triple-click on the paragraph**, which is the real pointer sequence a
    # user makes to select a line. `editable.click()` followed by `Home` /
    # `Shift+End` left the selection collapsed (`{collapsed: true, text: ""}`
    # measured on this host), so the toolbar was never raised and the wait below
    # timed out with nothing to show for it.
    paragraph = side.root.locator(HELP_EDITABLE + " p").first
    extra["paragraph_count"] = paragraph.count()
    extra["editable_visible"] = editable.is_visible()
    extra["dom"] = side.root.evaluate(
        """(sel) => {
            const wrappers = [...document.querySelectorAll(".o_field_html")].map(
                e => (e.getAttribute("name") || "?") + ":" + e.className.slice(0, 50));
            const ed = document.querySelector(sel);
            return {
                html_fields: wrappers,
                editable_html: ed ? ed.innerHTML.slice(0, 180) : null,
                editable_class: ed ? ed.className.slice(0, 80) : null,
                iframes_in_field: document.querySelectorAll(
                    '.o_field_html[name="help"] iframe').length,
            };
        }""", HELP_EDITABLE)
    target = paragraph if paragraph.count() else editable
    target.click(click_count=3)
    # Measured immediately: a settle first let whatever stole focus collapse the
    # selection before it was read, which made the reading say "no selection"
    # when the question was "did the click land".
    extra["after_click"] = side.root.evaluate(
        """() => {
            const s = window.getSelection();
            const a = document.activeElement;
            return {
                collapsed: s.isCollapsed,
                text: (s.toString() || "").slice(0, 40),
                active: a ? (a.tagName + "." + (a.className || "").slice(0, 60)) : null,
                toolbars: document.querySelectorAll(".o-we-toolbar").length,
                codeview_buttons: document.querySelectorAll(
                    '.o-we-toolbar button[name="codeview"]').length,
                any_codeview: document.querySelectorAll(
                    '[name="codeview"], .o_codeview_btn, #codeview-btn-group').length,
                // `odoo.debug` **on this page**. It was read once on the
                // `?debug=1` navigation, but the form is a separate document and
                // `var odoo = {debug: ...}` is baked in at render time, so the
                // question is whether the session carried it here.
                debug_here: (window.odoo && odoo.debug) || "",
                toolbar_buttons: [...document.querySelectorAll(".o-we-toolbar button")]
                    .map(b => b.getAttribute("name") || b.title || "?").slice(0, 30),
                toolbar_groups: [...document.querySelectorAll(".o-we-toolbar .btn-group")]
                    .map(g => g.getAttribute("name") || "?").slice(0, 20),
            };
        }""")
    side.page.wait_for_timeout(1500)
    extra["selection"] = side.root.evaluate(
        "() => { const s = window.getSelection();"
        " return {collapsed: s.isCollapsed, text: (s.toString() || '').slice(0, 40)}; }")
    extra["toolbar_present"] = side.root.locator(".o-we-toolbar").count() > 0
    extra["codeview_button"] = side.root.locator(CODEVIEW_TOOLBAR_BUTTON).count()
    toolbar = side.root.locator(CODEVIEW_TOOLBAR_BUTTON).first
    toolbar.wait_for(timeout=TIMEOUT)
    toolbar.click()
    # The textarea is deliberately not rewritten: it shows the record's own
    # bytes, which is why #240's own prerequisite note says typing a picture
    # there is the easy way to get one in.
    side.root.locator(CODEVIEW_TEXTAREA).first.wait_for(timeout=TIMEOUT)
    extra["code_view_shown"] = True
    extra["code_view_bytes"] = redact(
        side.root.locator(CODEVIEW_TEXTAREA).first.input_value(), {})

    off = side.root.locator(CODEVIEW_OFF_BUTTON).first
    off.wait_for(timeout=TIMEOUT)
    off.click()
    side.settle(1500)
    # This is the reading #240 is about: the markup `toggleCodeView` just
    # re-inserted at `html_field.js:236`, rendered.
    pictures = read_pictures(side.root, HELP_EDITABLE + " img", side)

    save = side.root.locator(SAVE_BUTTON).first
    save.wait_for(timeout=TIMEOUT)
    save.click()
    side.settle(4000)
    extra["unsaved_after_save"] = side.root.locator(UNSAVED).count() > 0
    after = read_field(side, "ir.actions.act_window", uid, "help")
    stored = {"ir.actions.act_window.help": after}

    if cleanup:
        write_field(side, "ir.actions.act_window", uid, "help", before or False)
        extra["help_restored"] = True
    return {"screen": "/odoo/ir.actions.act_window/%d (help, debug)" % uid, "pictures": pictures,
            "stored": stored, "extra": extra}


# --- #237: the plain path, through the history dialog --------------------------

# **The register names "the To-do form" and that form does not have this item.**
# `ProjectTaskFormController` is the only controller that adds it
# (`project_task_form_controller.js:28-38`), and `project_todo`'s own
# `TodoFormController.actionMenuItems` *whitelists* its cog items -- archive,
# unarchive, duplicate, delete and "Convert to Task"
# (`project_todo/static/src/views/todo_form/todo_form_controller.js:20-33`) -- so
# Version History is filtered out there. The screen is therefore the **project
# task** form: `/odoo/project.task/<id>` resolves to `project.view_task_form2`,
# which carries `js_class="project_task_form"` (`project_task_views.xml:322`).
# A to-do is still a `project.task`, so the same record opens on it.
#
# The opener is a *static action menu item* -- the cog,
# `description: _t("Version History")`, icon `fa-history`.
# The cog is `web.ActionMenus`' Actions dropdown (`action_menus.xml:23-28`,
# `data-hotkey="u"`), and its items are `DropdownItem`s classed `o_menu_item`.
COG_BUTTON = '.o_cp_action_menus button[data-hotkey="u"]'
COG_ITEM = ".o_menu_item"
VERSION_HISTORY_LABEL = "Version History"

# `html_editor.HistoryDialog` (`history_dialog.xml`). Its `getConfig()` sets
# neither `hasFullHtml` nor `cssAssetId`, so the `HtmlViewer` it mounts is on the
# plain `t-out="state.value"` path *by construction* -- which is why this is the
# screen for #237 check 1 rather than a field that happens to be readonly.
HISTORY_DIALOG = ".html-history-dialog"
HISTORY_CONTENT = HISTORY_DIALOG + " .history-container"
HISTORY_NO_CONTENT = "No history"
HISTORY_REVISIONS = HISTORY_DIALOG + " .revision-list a"
# Never "Restore history": that writes. The run closes the dialog.
HISTORY_DISCARD = ".o_dialog footer button.btn-secondary"


def do_readonly_plain(side, run_id: str, *, task_id=None, **_) -> dict[str, Any]:
    """#237 check 1: a readonly html field on the plain path.

    `openHistoryDialog` refuses to open when the record has no
    `html_field_history_metadata.description` -- it posts a notification and
    returns -- so this needs a to-do with one past revision. #235's check 2
    created one when it saved the onboarding to-do under Ingress. A host without
    one records this as unreachable rather than saving the record to make one,
    because that is #210's screen and #235's check.

    Reads only: the dialog is closed with Discard, never Restore history.
    """
    if task_id is None:
        task_id = onboarding_todo_id(side)
    if task_id is None:
        return {"pictures": None, "notes": "no to-do (project.task with no project) on this database"}
    # Read the controller's own precondition before driving anything. It refuses
    # on a falsy `html_field_history_metadata.description`, and the field is
    # `None` until the versioned field has been written at least once
    # (`html_field_history_mixin.py:29-41`), so this says *why* in advance rather
    # than leaving a notification to be inferred from an absent dialog.
    metadata = read_field(side, "project.task", task_id, "html_field_history_metadata")
    extra: dict[str, Any] = {
        "task_id": task_id,
        "has_description_history": bool((metadata or {}).get("description")
                                        if isinstance(metadata, Mapping) else metadata),
        "form": "project.view_task_form2 (js_class project_task_form)",
    }
    if not extra["has_description_history"]:
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "html_field_history_metadata has no 'description' entry, so "
                         "openHistoryDialog refuses: this record's description has never been "
                         "written and the plain path is unreachable on it. Saving it to make a "
                         "revision is #210's screen and #235's check, not this one."}
    side.goto("/odoo/project.task/%d" % task_id)
    side.wait_webclient()
    side.close_chat_windows()
    side.settle(1500)

    side.root.locator(COG_BUTTON).first.click()
    side.settle(600)
    item = side.root.locator(COG_ITEM).filter(has_text=VERSION_HISTORY_LABEL).first
    if not item.count():
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "the cog has no %r item on this form" % VERSION_HISTORY_LABEL}
    item.click()
    side.settle(2500)

    dialog = side.root.locator(HISTORY_DIALOG).first
    if not dialog.count():
        # The controller's own refusal path: a notification instead of a dialog.
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "the history dialog did not open: the to-do has no past revision of "
                         "its description, so the plain path is unreachable on this record"}
    body = dialog.inner_text()
    extra["revisions"] = side.root.locator(HISTORY_REVISIONS).count()
    if HISTORY_NO_CONTENT in body and not extra["revisions"]:
        pictures, notes = None, "the history dialog opened with no revisions"
    else:
        # `.o_readonly` is the plain path's own div; scoping to it rather than to
        # the dialog keeps the revision list's own markup out of the reading.
        pictures = read_pictures(side.root, HISTORY_CONTENT + " " + READONLY_CONTENT + " img", side)
        notes = ""
    discard = side.root.locator(HISTORY_DISCARD).first
    if discard.count():
        discard.click()
        side.settle(800)
    stored = {"project.task.description": read_field(side, "project.task", task_id, "description")}
    return {"screen": "/odoo/project.task/%d (Version History)" % task_id, "pictures": pictures,
            "stored": stored, "extra": extra, "notes": notes}


# --- #239: the media dialog's preselection -------------------------------------

# Both editors' dialogs, current and legacy, use the same content class and the
# same tile markers -- `html_editor/.../media_dialog.js:48` and
# `web_editor/.../media_dialog.js:50` both set `o_select_media_dialog`, and both
# `image_selector.xml` and `document_selector.xml` put `o_we_attachment_selected`
# on `.o_existing_attachment_cell` when the tile is the selected one. That class
# **is** #239: the preselection the three rules restored.
MEDIA_DIALOG = ".o_select_media_dialog"
MEDIA_TILE = MEDIA_DIALOG + " .o_existing_attachment_cell"
MEDIA_TILE_SELECTED = MEDIA_TILE + ".o_we_attachment_selected"
MEDIA_DISCARD = ".o_dialog footer button.btn-secondary"

# Reopening the dialog on an existing image. Two editors, two controls:
# `html_editor`'s is a toolbar item in the `image` namespace
# (`media_plugin.js:44-56`, `text: "Replace"`, so `name="replace_image"`), and the
# legacy editor's is the Replace button of its own toolbar
# (`web_editor/static/src/xml/editor.xml:278`).
REPLACE_CURRENT = '.o-we-toolbar button[name="replace_image"]'
REPLACE_LEGACY = "#media-replace"

# The **website editor**'s Replace is neither of those: it is a snippet option,
# `web_editor/views/snippets.xml:415-419`
# (`<div data-js="ReplaceMedia" ...><we-button data-replace-media="true">Replace`),
# and the `snippet-option-<data-js>` class is how the panel names it
# (`snippets.editor.js:3279-3283`). `#media-replace` is the legacy *toolbar*'s
# button and is kept only as a fallback.
REPLACE_WEBSITE = '.snippet-option-ReplaceMedia we-button[data-replace-media="true"]'

# A document in either editor carries `o_image`
# (`document_selector.js:10`, `mediaSpecificClasses`).
DOCUMENT_LINK = "a.o_image"


def media_dialog_reading(side, *, tab: str | None = None) -> dict[str, Any]:
    """What the open media dialog says about preselection.

    `tiles_selected` is the whole of #239: a tile carrying
    `o_we_attachment_selected` is the attachment the element came from, matched
    by a comparison whose two operands the three rules put on the same footing.
    """
    dialog = side.root.locator(MEDIA_DIALOG).first
    dialog.wait_for(timeout=TIMEOUT)
    if tab:
        candidate = side.root.locator(MEDIA_DIALOG + " .nav-link").filter(has_text=tab).first
        if candidate.count():
            candidate.click()
            side.settle(1500)
    # The tiles arrive from `fetchAttachments`, which is a round trip. Reading
    # straight after the dialog appears gave `tiles: 0` on one surface and
    # `tiles: 3` on the other for the same record -- a load race recorded as a
    # difference between the surfaces. Wait for the first tile, then settle.
    try:
        side.root.locator(MEDIA_TILE).first.wait_for(timeout=15000)
    except Exception:  # noqa: BLE001 -- a dialog that genuinely lists none
        pass
    side.settle(1500)
    tiles = side.root.locator(MEDIA_TILE)
    reading = {
        "tiles": tiles.count(),
        "tiles_selected": side.root.locator(MEDIA_TILE_SELECTED).count(),
        "tab": tab or "Images",
    }
    # What the dialog actually offered. Without this, "preselected none" cannot
    # be told apart from "the element never came from any attachment it listed",
    # and those two readings mean opposite things for #239.
    try:
        reading["tile_sources"] = [side.env.mask(source) for source in tiles.evaluate_all(
            """els => els.slice(0, 8).map(e => {
                const img = e.querySelector("img");
                return (img && (img.getAttribute("src") || img.src)) || e.textContent.trim().slice(0, 60);
            })""")]
    except Exception as error:  # noqa: BLE001
        reading["tile_sources"] = ["unreadable: " + type(error).__name__]
    reading.update(rewrite_reached_the_browser(side))
    return reading


# `@html_editor/main/media/media_dialog/image_selector` is where #239's rules 1
# and 2 live. Asking the page whether the served method carries the helper is the
# re-derivation the Issue's "Watch for" section demands when a check fails: it
# separates "the pattern did not match the deployed bytes" from "the rule ran and
# the comparison still disagreed", which are opposite findings.
_RULE_PROBE = """() => {
    const out = {markup_out_global: typeof window.__WOOW_INGRESS_MARKUP_OUT__};
    try {
        const mod = odoo.loader.modules.get(
            "@html_editor/main/media/media_dialog/image_selector");
        const source = mod.ImageSelector.prototype.isInitialMedia.toString();
        out.rule_in_served_method = source.includes("__WOOW_INGRESS_MARKUP_OUT__");
        out.served_method_length = source.length;
    } catch (error) { out.probe_error = String(error).slice(0, 120); }
    return out;
}"""


# Rule 3's argument is that **both** operands of the document comparison arrive
# prefixed: the element's `href` by the Runtime shim, and the literal
# `` `/web/content/${attachment.id}` `` by one of the generic literal rules the
# asset location has shipped since #166, because it begins `` `/web/ ``. No `OUT`
# was shipped for that read and a Static-tier test refuses one. Since no control
# reopens the dialog on a document in the current editor, reading the served
# method is how the premise is measured on the host instead.
_DOCUMENT_OPERAND_PROBE = """() => {
    const out = {};
    try {
        const mod = odoo.loader.modules.get(
            "@html_editor/main/media/media_dialog/document_selector");
        const source = mod.DocumentSelector.prototype.fetchAttachments.toString();
        out.served_literal_prefixed = /\/api\/hassio_ingress\/[A-Za-z0-9_-]{16,}\/web\/content\//.test(source);
        out.served_has_web_content_literal = source.includes("/web/content/");
        out.served_method_length = source.length;
        out.served_strips_query = source.includes("replace(/[?].*/");
    } catch (error) { out.probe_error = String(error).slice(0, 140); }
    return out;
}"""


def document_operand_reading(side) -> dict[str, Any]:
    try:
        return side.root.evaluate(_DOCUMENT_OPERAND_PROBE)
    except Exception as error:  # noqa: BLE001
        return {"probe_error": type(error).__name__}


def rewrite_reached_the_browser(side) -> dict[str, Any]:
    try:
        return side.root.evaluate(_RULE_PROBE)
    except Exception as error:  # noqa: BLE001
        return {"probe_error": type(error).__name__}


def close_media_dialog(side) -> None:
    discard = side.root.locator(MEDIA_DISCARD).first
    if discard.count():
        discard.click()
        side.settle(800)


def _media_verdict(reading: Mapping[str, Any], side) -> tuple[list[dict[str, Any]], str]:
    """#239 is display state, so its pass is the tile and not a picture.

    The record still carries a picture list, because the evidence table is one
    shape for the whole run: a preselected tile is reported as the surface's own
    expected verdict, and no tile is `ABSENT` -- nothing was measured about the
    attachment the element came from.
    """
    if reading["tiles_selected"]:
        return [{"tile": "selected", "verdict": expected_verdict(side.surface)}], ""
    if not reading["tiles"]:
        return [], "the dialog listed no attachment tiles at all, so the preselection was not measured"
    # Listed tiles and none selected is **not** an escape. `isInitialMedia` only
    # ever matches an attachment the dialog actually listed, so a non-match can
    # equally mean the element never came from one -- a static module asset, a
    # record-field image like a website logo. Measured on this host: the
    # onboarding to-do's picture is `/project_todo/static/img/todo_access.png`,
    # which is no attachment at all, and the website home page's is
    # `/web/image/website/1/logo/...`, a field image; both preselected none on
    # **both** surfaces. So this is `ABSENT` -- nothing about the rules was
    # measured -- and a real regression looks different: the same element
    # selected on the Public origin and not under Ingress. That comparison is
    # between two records and belongs to the evidence, not to one verdict.
    return [{"tile": "none selected", "verdict": ABSENT}], (
        "the dialog listed %d tile(s) and preselected none; on this surface that is only a "
        "finding if the other surface preselected one for the same element" % reading["tiles"])


def do_media_image_todo(side, run_id: str, *, task_id=None, **_) -> dict[str, Any]:
    """#239 line 1: the dialog reopened on an image in the To-do description.

    Nothing is stored either way -- this is the row that cannot escalate in
    severity from what the host shows -- so the dialog is discarded and the form
    is never saved.
    """
    if task_id is None:
        task_id = onboarding_todo_id(side)
    if task_id is None:
        return {"pictures": None, "notes": "no to-do on this database"}
    side.goto("/odoo/project.task/%d" % task_id)
    side.wait_webclient()
    side.close_chat_windows()
    extra: dict[str, Any] = {"task_id": task_id, "editable": wait_for_editable(side)}
    side.settle(2000)

    image = side.root.locator(EDITABLE + " img").first
    if not image.count():
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "the description holds no image, so there is nothing to reopen the dialog on"}
    # The element the dialog is asked about, recorded first: #239's comparison is
    # between this `src` and the attachment's `image_src`, and rule 2's branch is
    # about `data-original-src` on the same element.
    extra["element"] = {
        "src": side.env.mask(image.get_attribute("src")),
        "data_original_src": side.env.mask(image.get_attribute("data-original-src")),
    }
    image.click()
    side.settle(1000)
    replace = side.root.locator(REPLACE_CURRENT).first
    if not replace.count():
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "the image toolbar showed no Replace item"}
    replace.click()
    reading = media_dialog_reading(side)
    extra["dialog"] = reading
    pictures, notes = _media_verdict(reading, side)
    close_media_dialog(side)
    return {"screen": "/odoo/project.task/%d (media dialog, image)" % task_id,
            "pictures": pictures, "stored": {}, "extra": extra, "notes": notes}


def do_media_document_todo(side, run_id: str, *, task_id=None, **_) -> dict[str, Any]:
    """#239 line 3: the document tile, a **no-change** check.

    This one was never broken: its comparison's left operand is
    `` `/web/content/${attachment.id}` ``, one of the generic literal rules the
    asset location has shipped since #166, so it arrives prefixed and is compared
    against a prefixed `href`. No `OUT` was shipped for it and a Static-tier test
    refuses one. So a tile **not** highlighted here is new information -- it says
    the `` `/web/ `` coupling does not hold on the host -- and is reported
    against #239 rather than recorded as a partial fix.
    """
    if task_id is None:
        task_id = onboarding_todo_id(side)
    if task_id is None:
        return {"pictures": None, "notes": "no to-do on this database"}
    side.goto("/odoo/project.task/%d" % task_id)
    side.wait_webclient()
    side.close_chat_windows()
    extra: dict[str, Any] = {"task_id": task_id, "editable": wait_for_editable(side)}
    side.settle(2000)

    document = side.root.locator(EDITABLE + " " + DOCUMENT_LINK).first
    if not document.count():
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "the description holds no document link (a.o_image), so this row is "
                         "unreachable on this record; inserting one would be a different check"}
    extra["element"] = {"href": side.env.mask(document.get_attribute("href"))}
    extra["operand"] = document_operand_reading(side)
    # Deliberately **not** a click. A document is an `<a href>`, and clicking one
    # inside the editable navigates or starts a download -- which detaches the
    # element, so the next step times out "waiting for locator" and the check
    # records a timeout rather than a reading. Selecting the node is what raises
    # the toolbar anyway, and it leaves the page where it was.
    side.root.evaluate(
        """(selector) => {
            const anchor = document.querySelector(selector);
            const range = document.createRange();
            range.selectNode(anchor);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }""",
        EDITABLE + " " + DOCUMENT_LINK,
    )
    side.settle(1200)
    # The current editor's Replace is in the toolbar's `image` **namespace**
    # (`media_plugin.js:50`, `namespace: "image"`), and a document is an
    # `<a class="o_image">` rather than an `<img>` -- so selecting one does not
    # raise that group. Try it anyway, then fall back to a double-click, and
    # record which control opened the dialog so the evidence says how it was
    # reached rather than implying the toolbar did it.
    replace = side.root.locator(REPLACE_CURRENT).first
    if replace.count():
        extra["replace_control"] = REPLACE_CURRENT
        replace.click()
    else:
        # `force` because a document box can be laid out with zero size until the
        # editor's own stylesheet sizes it, and Playwright then refuses the click
        # as not actionable -- which is a fixture property, not a finding.
        extra["replace_control"] = "dblclick"
        document.dblclick(force=True)
    side.settle(1500)
    if not side.root.locator(MEDIA_DIALOG).count():
        return {"screen": "/odoo/project.task/%d" % task_id, "pictures": None, "extra": extra,
                "notes": "no control reopened the media dialog on the document link: the current "
                         "editor's Replace item is namespaced to `image` and a document is an "
                         "a.o_image, so this row may only be reachable through the legacy "
                         "editor's dialog (the website editor or the mail designer)"}
    reading = media_dialog_reading(side, tab="Documents")
    extra["dialog"] = reading
    pictures, notes = _media_verdict(reading, side)
    close_media_dialog(side)
    return {"screen": "/odoo/project.task/%d (media dialog, document)" % task_id,
            "pictures": pictures, "stored": {}, "extra": extra, "notes": notes}


def do_media_image_website(side, run_id: str, **_) -> dict[str, Any]:
    """#239 line 2, the more informative image check: the website editor.

    Rule 2's prefix only appears on this path. `data-original-src` is not
    prefixed by the shim, but the generic HTML location's rule is written for
    `src="/` and `sub_filter` is a plain substring search, so it matches inside
    the longer attribute name -- which means markup delivered as an **HTML
    response** carries a prefixed `data-original-src` while the same attribute on
    a field value does not. That branch `return`s before rule 1, so rule 1 alone
    would not have reached it. This dialog is also the legacy `web_editor` one.

    Nothing is saved: the editor is discarded.
    """
    side.goto("/odoo/action-website.website_preview")
    side.wait_webclient()
    root = side.root
    root.locator(".o_edit_website_container button, .o_edit_website_container a").first.click()
    root.locator(".o-snippets-menu, #oe_snippets, .o_we_website_top_actions").first.wait_for(timeout=TIMEOUT)
    side.settle(2000)
    extra: dict[str, Any] = {"editor": "open"}

    # The page is an iframe inside the editor; its images are the editable ones.
    # The editor holds two preview frames: the page and the hidden fallback it
    # navigates through, and which is first in the DOM is not a contract
    # (`e2e_ingress_hand_checks.preview_frames` carries the same note). Picking
    # one by "has an img" chose the hidden one, whose image is never actionable,
    # so the click timed out instead of reading anything. Pick by **visibility**.
    frames = [handle.content_frame() for handle in root.locator(".o_website_preview iframe").element_handles()]
    image = None
    for candidate in frames:
        if candidate is None:
            continue
        images = candidate.locator("img")
        for index in range(min(images.count(), 12)):
            option = images.nth(index)
            try:
                if option.is_visible():
                    image = option
                    break
            except Exception:  # noqa: BLE001 -- a frame that navigated away
                continue
        if image is not None:
            break
    if image is None:
        _discard_website_editor(side)
        return {"pictures": None, "extra": extra,
                "notes": "no preview frame held a visible image to reopen the dialog on"}
    try:
        image.scroll_into_view_if_needed(timeout=15000)
    except Exception:  # noqa: BLE001 -- already in view
        pass
    extra["element"] = {
        "src": side.env.mask(image.get_attribute("src")),
        "data_original_src": side.env.mask(image.get_attribute("data-original-src")),
    }
    image.click()
    side.settle(1500)
    replace = root.locator(REPLACE_WEBSITE).first
    if not replace.count():
        replace = root.locator(REPLACE_LEGACY).first
        extra["replace_control"] = REPLACE_LEGACY
    else:
        extra["replace_control"] = REPLACE_WEBSITE
    if not replace.count():
        _discard_website_editor(side)
        return {"pictures": None, "extra": extra,
                "notes": "neither the ReplaceMedia snippet option nor #media-replace was present "
                         "for the selected image"}
    replace.click()
    reading = media_dialog_reading(side)
    extra["dialog"] = reading
    pictures, notes = _media_verdict(reading, side)
    close_media_dialog(side)
    _discard_website_editor(side)
    return {"screen": "/odoo/action-website.website_preview (Edit, Replace media)",
            "pictures": pictures, "stored": {}, "extra": extra, "notes": notes}


def _discard_website_editor(side) -> None:
    """Leave the editor without saving, the way `U-D2` does."""
    try:
        side.root.locator(
            "button[data-action='cancel'], .o_we_website_top_actions button"
        ).filter(has_text=re.compile("Discard")).first.click()
        side.settle(1000)
        dialog = side.root.locator(".o_dialog footer button.btn-primary")
        if dialog.count():
            dialog.first.click()
            side.settle(800)
    except Exception:  # noqa: BLE001 -- nothing to discard
        pass


# --- #238: the mail designer, and the two fields a save writes -----------------

# The designer's own iframe, read from `mass_mailing_html_field.js`: its
# `contentDocument` holds `#iframe_target` (:224) and the editable `.note-editable`
# (:176), and the theme chooser is `.o_mail_theme_selector_new` (:259) whose theme
# links carry the theme name as their element id (`xml/mass_mailing.xml:25-27`).
# Editing is blocked until a theme is picked, and `basic` is the plain one
# (:455, :729).
MAILING_IFRAME = MAILING_BODY + " iframe"
MAILING_EDITABLE = ".note-editable"
MAILING_THEME_SELECTOR = ".o_mail_theme_selector_new"
MAILING_THEME_BASIC = "a#basic, #basic"

# A root-relative picture, so there is something for the rules to get wrong.
MAILING_BODY_TEMPLATE = (
    '<div class="o_layout"><p>%s</p>'
    '<img src="/web/image/res.company/1/logo" alt="logo"></div>'
)


def mailing_body_value(run_id: str) -> str:
    """The seeded mailing body, naming the run that seeded it."""
    return MAILING_BODY_TEMPLATE % marker_for(run_id)


MAILING_BODY_VALUE = MAILING_BODY_TEMPLATE % "WOOW parity"


def do_mailing_editable(side, run_id: str, *, mailing_id=None, cleanup=False, **_) -> dict[str, Any]:
    """#238 lines 1 and 2: the designer loads, and the save stores **two** fields.

    `body_arch` goes through `getEditingValue` (rule 7). `body_html` does not:
    `commitChanges` builds it separately by cloning the editable into a `srcdoc`
    iframe and running `toInline` over it (rule 8), and it is the field that
    **leaves the installation** with the mail. A run that reads back only
    `body_arch` has measured half the fix.

    If the designer renders blank under Ingress, the first place to look is *not*
    these rules: the editor iframe is built with `document.write`, so no Runtime
    shim runs inside it, and its `<script src>` tags come from the generic HTML
    location's `"src": "/` rewrite of `/web/bundle` JSON.
    """
    if mailing_id is None:
        mailing_id = editable_mailing_id(side)
    if mailing_id is None:
        return {"pictures": None, "notes":
                "no mailing.mailing in state draft or in_queue on this database"}
    before = side.rpc("mailing.mailing", "read", [[mailing_id], ["body_arch", "body_html"]])[0]
    extra: dict[str, Any] = {
        "mailing_id": mailing_id,
        "body_arch_before": redact(before.get("body_arch") or "", {}),
    }
    # Seeded over RPC so the value under test is exactly the measured one, and so
    # the check does not also depend on the designer's own typing working.
    write_field(side, "mailing.mailing", mailing_id, "body_arch", mailing_body_value(run_id))
    try:
        return _mailing_after_seeding(side, mailing_id, run_id, before, extra, cleanup=cleanup)
    except Exception as error:
        # Restore, then return the partial readings rather than re-raising: a
        # handler that raises has its return value discarded by `run_check`, and
        # the readings are the whole value of a failed attempt.
        try:
            side.rpc("mailing.mailing", "write", [[mailing_id], {
                "body_arch": before.get("body_arch") or False,
                "body_html": before.get("body_html") or False,
            }])
            extra["body_restored"] = True
        except Exception:  # noqa: BLE001 -- the session itself may be gone
            extra["body_restored"] = False
        return {"screen": "/odoo/mailing.mailing/%d (mail designer)" % mailing_id,
                "pictures": None, "stored": {}, "extra": extra,
                "notes": "%s: %s" % (type(error).__name__,
                                     adapter.sanitize_diagnostic(str(error))[:300])}
    except BaseException:
        # Same reason as `do_codeview`: this replaced a real mailing's body, every
        # step after it can raise, and `run_check` discards the outcome on a raise.
        try:
            side.rpc("mailing.mailing", "write", [[mailing_id], {
                "body_arch": before.get("body_arch") or False,
                "body_html": before.get("body_html") or False,
            }])
        except Exception:  # noqa: BLE001 -- the session itself may be gone
            pass
        raise


def _mailing_after_seeding(side, mailing_id, run_id, before, extra, *, cleanup=False) -> dict[str, Any]:
    """The browser half of `do_mailing_editable`, split out for the same reason."""
    side.goto("/odoo/mailing.mailing/%d" % mailing_id)
    side.wait_webclient()
    side.close_chat_windows()
    side.settle(3000)

    handles = side.root.locator(MAILING_IFRAME).element_handles()
    frame = next((handle.content_frame() for handle in handles if handle.content_frame()), None)
    extra["rendered_iframe"] = frame is not None
    if frame is None:
        return {"screen": "/odoo/mailing.mailing/%d" % mailing_id, "pictures": None, "extra": extra,
                "notes": "the mail designer rendered no iframe; look at the generic HTML "
                         "location's \"src\": \"/ rewrite of /web/bundle JSON before these rules"}
    if frame.locator(MAILING_THEME_SELECTOR).count():
        basic = frame.locator(MAILING_THEME_BASIC).first
        if basic.count():
            basic.click()
            side.settle(3000)
            extra["theme"] = "basic"
    editable = frame.locator(MAILING_EDITABLE).first
    if not editable.count():
        return {"screen": "/odoo/mailing.mailing/%d" % mailing_id, "pictures": None, "extra": extra,
                "notes": "the designer's iframe held no %s editable" % MAILING_EDITABLE}
    pictures = read_pictures(frame, MAILING_EDITABLE + " img", side)

    # Type into the designer so the form is **dirty**. The body was seeded over
    # RPC, so the form loads clean and the save button, while present in the DOM,
    # stays hidden behind `o_form_status_indicator_buttons.invisible` -- clicking
    # it then times out as not actionable. Typing is also what #238's row asks
    # for: the two rules are the save seam, and a save of an unchanged record
    # writes nothing for them to act on.
    try:
        editable.click()
        side.page.keyboard.press("Control+End")
        side.page.keyboard.type(" " + marker_for(run_id))
        side.settle(1500)
        extra["typed"] = True
    except Exception as error:  # noqa: BLE001
        extra["typed"] = False
        extra["typing_error"] = type(error).__name__

    save = side.root.locator(SAVE_BUTTON).first
    extra["save_visible"] = save.is_visible() if save.count() else False
    if not extra["save_visible"]:
        # Without the save, #238's whole subject is untouched: `getEditingValue`
        # (rule 7) never runs and `commitChanges` never inlines `body_html` (rule
        # 8). And `body_arch` read back would be the value *this function* seeded
        # over RPC -- root-relative, so `CLEAN` -- which with the pictures already
        # read would score a pass for a check that exercised neither rule. The
        # form is loaded clean precisely because the seed was an RPC write, so this
        # path is likely rather than hypothetical.
        extra["saved"] = False
        return {"screen": "/odoo/mailing.mailing/%d (mail designer)" % mailing_id,
                "pictures": None, "extra": extra,
                "notes": "%s never became visible, so nothing was saved: the two rules this "
                         "check is about are the save seam, and a read-back of the RPC-seeded "
                         "body_arch would have scored a pass without exercising either"
                         % SAVE_BUTTON}
    save.click()
    side.settle(6000)
    extra["saved"] = True
    extra["unsaved_after_save"] = side.root.locator(UNSAVED).count() > 0
    if extra["unsaved_after_save"]:
        extra["save_incomplete"] = True
    after = side.rpc("mailing.mailing", "read", [[mailing_id], ["body_arch", "body_html"]])[0]
    stored = {
        "mailing.mailing.body_arch": after.get("body_arch"),
        "mailing.mailing.body_html": after.get("body_html"),
    }
    if cleanup:
        side.rpc("mailing.mailing", "write", [[mailing_id], {
            "body_arch": before.get("body_arch") or False,
            "body_html": before.get("body_html") or False,
        }])
        extra["body_restored"] = True
    return {"screen": "/odoo/mailing.mailing/%d (mail designer)" % mailing_id,
            "pictures": pictures, "stored": stored, "extra": extra}

if __name__ == "__main__":
    raise SystemExit(main())
