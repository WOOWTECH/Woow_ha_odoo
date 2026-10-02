#!/usr/bin/env python3
"""Live tier: two sessions edit one to-do, and what the record keeps (#234).

    python odoo18ce/tests/e2e_collab_peer_snapshot_live.py probe \
        --env-file /projects/Woow_ha_odoo/.env --db odoo_parity
    python odoo18ce/tests/e2e_collab_peer_snapshot_live.py run \
        --env-file /projects/Woow_ha_odoo/.env --db odoo_parity \
        --run-id WOOW-PEER-<UTC timestamp> --out peer.jsonl
    python odoo18ce/tests/e2e_collab_peer_snapshot_live.py report peer.jsonl

`probe` takes `--run-id` too and mints one when it is not given
(`WOOW-PEER-PROBE-<UTC timestamp>`, printed with its report): the marker it
types must be unique to the run, for the reason under **What it measures**.

**#243 has run this script**, on 2026-10-02 against Release 0.4.10, and its two
records are in `docs/testing/evidence/2026-10-02-issue-243/peer.jsonl`: `CLEAN`
on both pairs, and the transport delivered on neither, so those verdicts are
about the save path and not about a delivered peer snapshot (#265 owns that).
That run was also every browser step's first execution, and it found two defects
here, both fixed under #263 and both worth knowing before trusting a reading from
this file: `probe` wrote the field it reported it did not, and its marker was a
constant, which made `delivered` unfalsifiable once the field had ever held it.

The pure functions below -- the prefix shape, the labelling, the redaction, the
wait's judgement, the probe's verdict and the report -- are driven by
`test_e2e_collab_peer_snapshot.py` at the Static tier. The browser steps are not,
and the two defects above are what that costs: both were mistakes about what a
*step* does, which no Static tier can see. So the steps are pinned there by
shape instead, and a failure in them should still be read as this script being
wrong before it is read as the host being wrong.

## What it measures

`project.task.description` is an html field with `'collaborative': true`. The
collaboration transport ships *serialised nodes* -- each attribute's value byte
for byte -- and the peer that joins second is handed the first peer's whole
document as a snapshot. Under Ingress that document's URLs carry the sending
page's prefix, which is `/api/hassio_ingress/<the add-on's ingress token>`. The
receiving session's save is what would write it to the record.

So: session A opens the to-do, the run reads A's editable **before anything is
typed** -- the baseline, which is the document both sessions load -- and A then
types a marker **without saving**. Session B joins the same to-do, and the run
waits for A's unsaved marker to appear in B's editable. That arrival is the
transport's own evidence only because the marker carries the run id and was not
in the baseline: a marker some earlier run stored would otherwise be read out of
the *loaded* value on the first poll and reported as an instant delivery, which
is the false positive #263 found on a `delivered` of 0.0 seconds. B then types
its own marker and saves, and the run reads `description` back over ORM and
classifies every Ingress prefix left in it.

Two pairs, because they answer different questions:

- `--pair ingress-ingress` (default): both sessions reach the add-on through
  Home Assistant. Their prefixes are **expected to be equal**: the token in the
  path is the add-on's `ingress_token`, one persisted secret per installed
  add-on, while the per-user session is a separate secret carried in the
  `ingress_session` cookie. The run records the two prefixes rather than
  assuming it, because that equality is the reason #210's strip already covers
  this pair -- and if they ever differ, this is the row that says so.
- `--pair ingress-public`: A is an Ingress session, B is the Public origin.
  B has no Runtime shim and no rewrite (ADR 0003 keeps that surface the control
  group), so a prefix it receives is a prefix it stores. This is the pair that
  can put the add-on's token in the record today, and the Ingress strip's part
  in it is healing the record on the next Ingress save, not preventing the
  write.

## What it writes

`run` writes the to-do's `description` on the database named by `--db`, and
nothing else: no record is created and none is deleted. Both markers carry the
run id, so the record says which run last edited it, and A's form is discarded
once B has saved, so the stored value is exactly what B saved.

`probe` writes nothing -- and **discarding is what makes that true**, not
declining to save. Navigating away from a dirty To-do form persists the
editable's content: two `probe` runs left their marker in the stored description
twice (#263, found by #243's run on 0.4.10). So `probe` clicks the form's own
Discard on both sessions before it leaves, which reloads the record from the
database, and then reads `description` back over ORM and reports
`wrote_nothing`. The claim is measured and carried in the output rather than
asserted here, and a `probe` that did write exits non-zero. `discard_form` holds
the mechanism and why each of its two waits is load-bearing.

**The read-back is the guarantee, and the discard is only the means** -- which is
deliberate, because this measurement cannot remove every way the form writes
itself. Odoo saves a form on `visibilitychange` as well as on unload
(`web/static/src/views/form/form_controller.js:483`), that handler is **not**
gated on the record being dirty, and it calls a full `save()`. A session whose
page is backgrounded while its form is dirty therefore writes with no navigation
at all -- and session A is *necessarily* dirty while session B opens, since A's
unsaved marker is the thing B is waiting for. The two sessions get their own
browser contexts, which is the arrangement least likely to hide either page, but
"least likely" is not a guarantee and this module will not claim one. So the
field is read back on every `probe` and the result reported: a write that happens
anyway is **detected and named** rather than assumed away, and the record then
needs the marker stripped the way #243's run stripped two.

**No token ever reaches the output.** Every value is passed through `redact`,
which replaces each Ingress prefix with the label of the session it belongs to
(`<ingress:A>`, `<ingress:B>`, `<ingress:unknown>`) -- so the evidence says
*whose* prefix was stored without carrying the secret, which is the whole point
of reading the field back.

Environment: the names the parity run uses (`--env-file` fills unset ones) --
HA_BASE_URL, HA_TOKEN, ADDON_SLUG, ODOO_PUBLIC_URL, ODOO_TEST_LOGIN,
ODOO_TEST_PASSWORD, PARITY_TARGET, and `IGNORE_HTTPS_ERRORS=1` for a
self-signed certificate. The whole list is required even for
`--pair ingress-ingress`, which never opens the Public origin: this shares the
parity run's `Env`, and that is the parity run's contract. No artifact directory
is used -- `run` appends its one record to `--out`, and `probe` prints and keeps
nothing.

The record is a `woow.peer-snapshot.v1` and deliberately not an
`odoo-parity-evidence/v1`; the parity plan's section 12 says why, and
`test_e2e_collab_peer_snapshot.py` holds the two together.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence

from e2e_menu_action_adapter import parse_env_file, sanitize_diagnostic
from e2e_parity_shared_layers_live import TIMEOUT, Env, IngressSide, PublicSide

# The shape of an Ingress prefix, which is nginx's `$safe_ingress_path` map and
# not a guess: a request whose `X-Ingress-Path` does not match it is served
# with no prefix at all. `test_e2e_collab_peer_snapshot.py` derives the same
# shape from the gateway template and refuses a difference, so this constant
# cannot drift away from the add-on it is measuring.
INGRESS_PREFIX_SHAPE = re.compile(r"/api/hassio_ingress/[A-Za-z0-9_-]{16,128}(?![A-Za-z0-9_-])")

# Not `odoo-parity-evidence/v1`. That schema is one record per *plan item*, with
# one column for each of the two **surfaces** a control was observed on; this
# measurement has two **sessions** and, in the `ingress-ingress` pair, only one
# surface -- and what it has to carry is each session's prefix and whose was
# stored, which a parity record has nowhere to put. Registered in the parity
# plan's section 12 beside that schema, and no run here feeds `conservation`.
EVIDENCE_SCHEMA = "woow.peer-snapshot.v1"

CLEAN = "CLEAN"
FOREIGN_PREFIX_STORED = "FOREIGN-PREFIX-STORED"
OWN_PREFIX_STORED = "OWN-PREFIX-STORED"
UNKNOWN_PREFIX_STORED = "UNKNOWN-PREFIX-STORED"
NOT_RUN = "NOT-RUN"

PAIRS = ("ingress-ingress", "ingress-public")

# `probe`'s run id when the command line does not give one. It is a *run* id and
# not a constant marker: #263.
PROBE_RUN_PREFIX = "WOOW-PEER-PROBE"

# The html field's editable, the form's save button, its discard button, and the
# indicator that says the form is dirty. The discard button is in the DOM on a
# clean form too, hidden behind `o_form_status_indicator_buttons.invisible`, so
# it is clicked only when it is visible -- #238's run lost a measurement to
# exactly that (clicking the hidden save button).
EDITABLE = ".o_field_html .odoo-editor-editable"
SAVE_BUTTON = ".o_form_button_save"
DISCARD_BUTTON = ".o_form_button_cancel"
UNSAVED = ".o_form_status_indicator_buttons:not(.invisible)"


# --- What a run calls its markers ----------------------------------------------


def marker(run_id: str, label: str) -> str:
    """The marker session `label` types, which **both** commands get from here.

    A marker has to be unique to the run, because the whole argument for reading
    its arrival as a delivery is that nothing has stored it. `probe` used to type
    the constant `WOOW-PEER-PROBE`; once a probe had written that string into the
    field -- which probes did, see the module docstring -- the next probe found it
    in the receiving editable on the first poll and reported `delivered: true` at
    0.0 seconds while nothing had been delivered (#263). One helper, so the two
    commands cannot drift apart on it again.
    """
    return "%s-%s" % (run_id, label)


def mint_run_id(now: datetime, prefix: str = PROBE_RUN_PREFIX) -> str:
    """A run id in the shape `run` takes on the command line, for `probe`.

    `probe` is the step a reader runs by hand first, so it must not need a run id
    typed to be safe. `now` is passed in rather than read here, which is what
    lets the Static tier pin the shape.
    """
    return "%s-%sZ" % (prefix, now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S"))


# --- What a value says, without saying a token ---------------------------------


def ingress_prefixes(value: str) -> list[str]:
    """Every distinct Ingress prefix in `value`, in the order it first occurs."""
    found: list[str] = []
    for match in INGRESS_PREFIX_SHAPE.finditer(value or ""):
        if match.group(0) not in found:
            found.append(match.group(0))
    return found


def redact(value: Any, labels: Mapping[str, str]) -> Any:
    """Replace every Ingress prefix with the label of the session it belongs to.

    A prefix no session claims is `<ingress:unknown>`: it is still a Supervisor
    token, so it is still never printed, and a reader can tell the two cases
    apart -- an unknown prefix in a record is a value this run did not put
    there.
    """
    if isinstance(value, str):
        def name(match: re.Match) -> str:
            return "/api/hassio_ingress/<ingress:%s>" % labels.get(match.group(0), "unknown")

        return INGRESS_PREFIX_SHAPE.sub(name, value)
    if isinstance(value, Mapping):
        return {key: redact(child, labels) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(child, labels) for child in value)
    return value


def stored_prefix_labels(stored: str, labels: Mapping[str, str]) -> list[str]:
    """Which sessions' prefixes are in a value, in order, without judging them.

    Separate from `classify` because a reading and a verdict are not the same
    thing, and one caller has no verdict to give: `probe` saves nothing, so there
    is no saver for a saver-relative verdict to be relative *to*. It reports this
    instead (#263).

    Note what `labels` does on the `ingress-ingress` pair: both sessions are
    served the add-on's one `ingress_token`, so the two prefixes are equal and
    `labels_for` collapses to a single entry -- whichever session it wrote last.
    A label from here is therefore "a session whose prefix this is", not reliably
    *which* one, on the pair where the two are indistinguishable by construction.
    That is exactly why `prefixes_equal` is recorded separately.
    """
    return [labels.get(prefix, "unknown") for prefix in ingress_prefixes(stored)]


def classify(stored: str, labels: Mapping[str, str], saver: str) -> tuple[str, list[str]]:
    """The verdict for one stored value, and the labels of the prefixes in it.

    `saver` is the label of the session that wrote the value. Its own prefix
    surviving means the strip that #210 added did not run; another session's
    means the strip ran and did not recognise what it was given, which is what
    #234 is about; one nobody claims is a token this run cannot account for and
    is read the same way as a foreign one -- a prefix in a record is the harm
    whoever put it there.
    """
    present = stored_prefix_labels(stored, labels)
    if not present:
        return CLEAN, []
    if any(label == "unknown" for label in present):
        return UNKNOWN_PREFIX_STORED, present
    if any(label != saver for label in present):
        return FOREIGN_PREFIX_STORED, present
    return OWN_PREFIX_STORED, present


def evidence_record(
    *,
    run_id: str,
    database: str,
    target: str,
    pair: str,
    task_id: int | None,
    prefixes: Mapping[str, str | None],
    transport: Mapping[str, Any],
    stored: str | None,
    labels: Mapping[str, str],
    saver: str,
    notes: str = "",
) -> dict[str, Any]:
    """One run's record. `verdict` is NOT-RUN until a value was read back."""
    if stored is None:
        verdict, present = NOT_RUN, []
    else:
        verdict, present = classify(stored, labels, saver)
    record = {
        "schema": EVIDENCE_SCHEMA,
        "run_id": run_id,
        "database": database,
        "target": target,
        "issue": 234,
        "pair": pair,
        "field": "project.task.description",
        "task_id": task_id,
        "saver": saver,
        # The prefixes the two sessions were served, redacted to their labels.
        # Equal prefixes are the expected reading of `ingress-ingress`, and the
        # record says so rather than leaving a reader to infer it from one line.
        "prefixes": {
            label: (redact(prefix, labels) if prefix else None)
            for label, prefix in prefixes.items()
        },
        "prefixes_equal": _equal_prefixes(prefixes),
        "transport": dict(transport),
        "stored": redact(stored, labels),
        "stored_prefixes": present,
        "verdict": verdict,
        "notes": notes,
    }
    return record


def _equal_prefixes(prefixes: Mapping[str, str | None]) -> bool | None:
    values = [prefix for prefix in prefixes.values() if prefix]
    if len(values) < 2:
        return None
    return len(set(values)) == 1


def report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What the run found, and what #234's own criteria make of it."""
    verdicts = [record.get("verdict") for record in records]
    escalate = [
        record for record in records
        if record.get("verdict") in (FOREIGN_PREFIX_STORED, UNKNOWN_PREFIX_STORED)
    ]
    return {
        "records": len(records),
        "verdicts": {verdict: verdicts.count(verdict) for verdict in sorted(set(verdicts))},
        "transport_delivered": sorted(
            {bool((record.get("transport") or {}).get("delivered")) for record in records}
        ),
        # #234's acceptance criteria: a stored foreign token makes it a blocker
        # (parity plan section 1.3, token leak). Said by the report rather than
        # left to whoever reads the JSONL.
        "escalate_issue_234_to_blocker": bool(escalate),
        "pairs": sorted({record.get("pair") for record in records}),
    }


# --- What a wait and a probe conclude ------------------------------------------
#
# Pure, and pinned at the Static tier with the rest: these two are where #263's
# two false readings were decided, and neither needs a browser to be wrong.

PRE_EXISTING_DETAIL = (
    "the marker was already in the editable before the other session typed it, so a "
    "match here would be a value something had stored and not a delivery"
)
NEVER_ARRIVED_DETAIL = (
    "the other session's unsaved marker never arrived; the two sessions did not become "
    "collaboration peers"
)


def await_marker(
    read: Callable[[], str],
    marker_text: str,
    *,
    baseline: str | None,
    sleep: Callable[[int], Any],
    seconds: int = 30,
) -> dict[str, Any]:
    """Poll `read` for `marker_text`, refusing a match that was already there.

    `baseline` is the editable as it read **before** the other session typed --
    the loaded document, which is what both sessions start from. A marker already
    in it cannot have been delivered, so this does not wait for one: it says so
    and stops. That is the guard #263 asked for, and the run id in the marker is
    the other half of it -- the guard catches a collision, the run id makes one
    almost impossible.

    `waited_seconds` of 0.0 with `delivered` true is a legitimate reading and not
    a contradiction of any of this: the receiving session joins *after* the sender
    typed, so the snapshot it is handed can carry the marker on the first poll.
    It is still the shape to look at twice, which is why the number is recorded
    rather than reduced to a boolean (parity plan section 12).
    """
    if marker_text in (baseline or ""):
        return {
            "delivered": False,
            "waited_seconds": 0.0,
            "marker_pre_existing": True,
            "detail": PRE_EXISTING_DETAIL,
        }
    for attempt in range(seconds * 2):
        if marker_text in (read() or ""):
            return {
                "delivered": True,
                "waited_seconds": attempt / 2.0,
                "marker_pre_existing": False,
            }
        sleep(500)
    return {
        "delivered": False,
        "waited_seconds": float(seconds),
        "marker_pre_existing": False,
        "detail": NEVER_ARRIVED_DETAIL,
    }


def transport_note(transport: Mapping[str, Any]) -> str:
    """What a record has to say about its own value when nothing was delivered.

    A delivered transport needs no note. An undelivered one does, and *which*
    way it failed changes the sentence: "the marker never arrived" and "the
    marker was already there" are different findings, and the second one says the
    run id collided, which makes the whole record suspect rather than just its
    transport half. So the wait's own detail is carried through instead of one
    fixed sentence -- the old note said "never saw the sender's marker" either
    way, which would have been a false account of the second case.
    """
    if transport.get("delivered"):
        return ""
    detail = transport.get("detail") or "the marker did not arrive"
    return "%s -- so the stored value is not evidence about the peer transport" % detail


def probe_verdict(
    *,
    transport: Mapping[str, Any],
    stored: str,
    run_id: str,
    discarded: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Whether `probe`'s claims held: it delivered, it wrote nothing, and it can say so.

    `wrote_nothing` is read back off the record rather than asserted, because
    asserting it is exactly what went wrong: the docstring, `docs/agents/
    live-tier.md` and the `finally` block all said the field was untouched while
    two runs' markers sat in it (#263). The marker carries the run id, so this
    looks for *this* probe's write and not for a previous one's leftovers.

    **A form left dirty fails the probe even when the read-back is clean**, and
    that is not belt-and-braces. The read-back can only see writes that have
    already happened; a session still holding unsaved content can be written
    afterwards, by the `visibilitychange` save or by the unload, both of which
    outlive this function. On that path a clean read-back means "not yet", not
    "not at all" -- so the one thing the probe must not do is report
    `wrote_nothing` and exit 0 while leaving the write armed.
    """
    wrote_nothing = run_id not in (stored or "")
    left_dirty = sorted(
        label for label, outcome in discarded.items()
        if outcome.get("dirty") and not outcome.get("discarded")
    )
    if not wrote_nothing:
        detail = ("this probe's own run id is in the stored value, so the probe wrote the "
                  "field it reports it did not: the record needs the marker removed, and "
                  "the discard step did not hold")
    elif left_dirty:
        detail = ("the field read back clean, but session(s) %s were left with unsaved "
                  "content: a dirty form is still written on the way out, so this says "
                  "'not yet' and not 'not at all' -- read the field again on the host"
                  % ", ".join(left_dirty))
    else:
        detail = ""
    return {
        "wrote_nothing": wrote_nothing,
        "forms_left_dirty": left_dirty,
        "detail": detail,
        "exit_code": 0 if (transport.get("delivered") and wrote_nothing and not left_dirty)
                     else 1,
    }


# --- The two sessions ----------------------------------------------------------


def _side_env(env: Env) -> Env:
    """A copy of `env`, so each session owns its own prefix and its own masker.

    `IngressSide.start` writes the prefix it was served onto the Env it was
    given, and two sessions sharing one Env would overwrite each other's -- so
    the second session's evidence would be masked with the first one's prefix.
    The secrets list is copied too, not shared: each session's masker is told
    about the other's prefix, and a shared list would make that one list.
    """
    copied = copy.copy(env)
    copied.extra_secrets = list(env.extra_secrets)
    return copied


def open_pair(env: Env, browser, pair: str, *, viewport=(1600, 1000)):
    """Session A first, then session B: the second to join is the receiver."""
    context_args: dict[str, Any] = {
        # The spelling every other script in this directory uses.
        "ignore_https_errors": os.environ.get("IGNORE_HTTPS_ERRORS", "0") == "1",
    }
    first = IngressSide(_side_env(env), browser, viewport=viewport, **context_args)
    if pair == "ingress-public":
        second = PublicSide(_side_env(env), browser, viewport=viewport, **context_args)
    else:
        second = IngressSide(_side_env(env), browser, viewport=viewport, **context_args)
    first.start()
    second.start()
    # Each side's masker must know the other's prefix as a secret of its own,
    # or a diagnostic from one session could print the other's token.
    for side, other in ((first, second), (second, first)):
        if other.env.prefix:
            side.env.extra_secrets.append(other.env.prefix)
    return first, second


def find_todo(side) -> int:
    """The to-do Odoo creates for every user: a personal task with no project.

    `_ensure_onboarding_todo()` copies `project_todo`'s `todo_user_onboarding`
    template into its description, so it is the record that carries the two
    pictures #210 was measured on. The lowest id is that one; a `--task-id`
    overrides this when a host has been edited into a different state.
    """
    ids = side.rpc("project.task", "search", [[["project_id", "=", False]]],
                   {"limit": 1, "order": "id asc"})
    if not ids:
        raise RuntimeError(
            "no personal to-do on this database: open the To-do app once as the test user, "
            "or name one with --task-id"
        )
    return int(ids[0])


def open_todo(side, task_id: int) -> None:
    side.goto("/odoo/project.task/%d" % task_id)
    side.wait_webclient()
    side.root.locator(EDITABLE).first.wait_for(timeout=TIMEOUT)


def type_marker(side, marker_text: str) -> None:
    """Type into the editable, which is what makes a collaboration step."""
    editable = side.root.locator(EDITABLE).first
    editable.click()
    side.page.keyboard.press("Control+End")
    side.page.keyboard.type(" " + marker_text)


def editable_html(side) -> str:
    return side.root.locator(EDITABLE).first.evaluate("node => node.innerHTML")


def wait_for_transport(side, marker_text: str, *, baseline: str | None,
                       seconds: int = 30) -> dict[str, Any]:
    """Wait for the *other* session's unsaved marker to arrive in this one.

    The waiting and the judgement are `await_marker`'s, which the Static tier
    drives; this is only the two browser verbs it needs. `baseline` must be the
    editable as it read before the sending session typed -- see `stage`.
    """
    return await_marker(
        lambda: editable_html(side),
        marker_text,
        baseline=baseline,
        sleep=side.page.wait_for_timeout,
        seconds=seconds,
    )


def save_form(side) -> None:
    button = side.root.locator(SAVE_BUTTON).first
    button.wait_for(timeout=TIMEOUT)
    button.click()
    side.root.locator(SAVE_BUTTON).first.wait_for(state="hidden", timeout=TIMEOUT)
    side.settle()


def discard_form(side) -> dict[str, Any]:
    """Throw this session's unsaved editor content away, and say what happened.

    **This is what makes `probe` write nothing**, and declining to save is not.
    Two `probe` runs left their marker in `project.task.description`, 32
    characters of it, while every docstring involved said the record was
    untouched (#263, found by #243's run). The mechanism, read from the pinned
    package (`ODOO_DEB_VERSION`, 18.0.20260930) rather than guessed:

    - `useSetupAction` registers a `beforeunload` listener for every form
      controller, which always passes the handler
      (`web/static/src/search/action_hook.js:76`,
      `web/static/src/views/form/form_controller.js:289`), and a real document
      navigation -- which `page.goto` is -- fires it;
    - the handler calls `record.urgentSave()`
      (`web/static/src/views/form/form_controller.js:508`), which raises
      `WILL_SAVE_URGENTLY`; the html field answers it by committing the editor's
      content into the record (`html_editor/static/src/fields/html_field.js:77`),
      which is the typed marker that had never been committed;
    - the urgent path then **writes with `navigator.sendBeacon`**
      (`web/static/src/model/relational_model/record.js:1033`), which no request
      interception sees and nothing can cancel.

    So "only a save writes the field", the reason the old `finally` gave for being
    safe, was never true of this form. Discard is the form's own undo -- it resets
    the record's changes and remounts the editor from the stored value -- and
    after it the field reports itself clean, so the same `beforeunload` harvests
    nothing and the save short-circuits with no RPC at all.

    Two details are load-bearing, not defensive:

    - **The wait.** `FormController.discard()` is asynchronous, and Playwright's
      `click()` returns long before it resolves. Navigating in that window leaves
      the field still dirty and the beacon still fires, so this blocks on the
      indicator going clean rather than clicking and moving on.
    - **The visibility check.** The button is in the DOM on a clean form too,
      behind `o_form_status_indicator_buttons.invisible`
      (`.../form_status_indicator/form_status_indicator.xml:6`), and `click()`
      waits for visibility rather than failing fast -- a clean form would spend
      the whole timeout here. On a readonly form the button is absent entirely,
      which is why presence is checked as well as visibility.

    `dirty` is reported because it is a reading in its own right: a `probe` whose
    forms were never dirty exercised nothing.
    """
    # The indicator is the earliest faithful signal there is -- the html field
    # raises `FIELD_IS_DIRTY` on the first keystroke, before `record.dirty` is
    # set (`html_field.js:225`, `form_status_indicator.js:16`).
    dirty = side.root.locator(UNSAVED).count() > 0
    # `>> visible=true` rather than `.first`, which is this repository's idiom for
    # the same button (`e2e_parity_shared_layers_live.py:1805`). `.first` picks the
    # first match in the DOM whatever its state, so one hidden earlier indicator --
    # a dialog's, a sub-form's -- would make `is_visible()` false and silently skip
    # the real button, which is the failure this function exists to prevent.
    button = side.root.locator(DISCARD_BUTTON + " >> visible=true").first
    if not dirty or not button.count():
        return {"dirty": dirty, "discarded": False}
    button.click()
    # The indicator carries `invisible` again once the record is clean, so this
    # selector stops matching; a locator with no element counts as hidden.
    side.root.locator(UNSAVED).first.wait_for(state="hidden", timeout=TIMEOUT)
    side.settle()
    return {"dirty": True, "discarded": True}


def discard_quietly(side) -> dict[str, Any]:
    """`discard_form`, but a failure here never costs the run its report.

    Discarding is cleanup, and the readings it protects are expensive: a Live run
    needed a deploy and a host, and the transport wait alone takes 30 seconds. A
    `wait_for` that times out because the form will not go clean -- an invalid
    record keeps the indicator up, so it never does -- must not throw away the
    measurement that was already taken. So the outcome is recorded and returned,
    and `probe` treats a form it could not discard as a failure *in the report*
    rather than as an exception that prevents one.
    """
    try:
        return discard_form(side)
    except Exception as error:  # noqa: BLE001 -- the reading matters more
        return {"dirty": True, "discarded": False, "error": type(error).__name__}


def read_description(side, task_id: int) -> str:
    [record] = side.rpc("project.task", "read", [[task_id], ["description"]])
    return record.get("description") or ""


def labels_for(first, second) -> dict[str, str]:
    labels: dict[str, str] = {}
    for label, side in (("A", first), ("B", second)):
        if side.env.prefix:
            labels[side.env.prefix] = label
    return labels


# --- Commands -----------------------------------------------------------------


def stage(env: Env, browser, pair: str, task_id: int | None, marker_text: str):
    """Both commands' common half, up to the point where only `run` saves.

    Session A opens the to-do and types `marker_text` **without saving**; session
    B joins the same record; the run waits for that marker to reach B. Everything
    after this differs: `probe` discards both forms and stops, `run` types B's own
    marker, saves and reads the field back. A failure in here leaves the two
    contexts to `browser.close()` in `main`, which is the last thing either
    command does.

    **A's editable is read before A types**, and that reading is what the wait is
    judged against. It is the loaded document, so a marker found in it was stored
    by something and cannot have been delivered -- the distinction #263 asked for.
    It is read from A rather than from B because B has not joined yet at that
    point, and both sessions load the same stored value.
    """
    first, second = open_pair(env, browser, pair)
    labels = labels_for(first, second)
    task_id = task_id or find_todo(first)
    open_todo(first, task_id)
    baseline = editable_html(first)
    type_marker(first, marker_text)
    open_todo(second, task_id)
    transport = wait_for_transport(second, marker_text, baseline=baseline)
    return first, second, labels, task_id, transport


def do_probe(env: Env, browser, pair: str, task_id: int | None, run_id: str) -> int:
    """Open both sessions, report what they were served, and leave the record alone.

    It does not merely decline to save -- it clicks the form's own **Discard** on
    both sessions and then reads `description` back to say so. `wrote_nothing` in
    the output is that reading, and a false one exits non-zero: the whole of #263
    is that this step's claim was never checked.
    """
    probe_marker = marker(run_id, "A")
    first, second, labels, task_id, transport = stage(
        env, browser, pair, task_id, probe_marker)
    try:
        # Read B's editable before discarding: after a discard it holds the stored
        # value, and what a reader needs from it is what the transport delivered.
        second_editable = redact(editable_html(second), labels)[:2000]
        # Both sessions, each independently: A's discard failing must not leave B
        # dirty *and* unreported. `discard_quietly` says why a failure here is a
        # line in the report rather than an exception instead of one.
        discarded = {label: discard_quietly(side)
                     for label, side in (("A", first), ("B", second))}
        stored = read_description(first, task_id)
        verdict = probe_verdict(transport=transport, stored=stored, run_id=run_id,
                                discarded=discarded)
        print(json.dumps({
            "pair": pair,
            "run_id": run_id,
            "task_id": task_id,
            "prefixes": {label: redact(side.env.prefix, labels)
                         for label, side in (("A", first), ("B", second))},
            "prefixes_equal": _equal_prefixes(
                {"A": first.env.prefix, "B": second.env.prefix}
            ),
            "transport": transport,
            "second_session_editable": second_editable,
            "saved": False,
            "discarded": discarded,
            "wrote_nothing": verdict["wrote_nothing"],
            "forms_left_dirty": verdict["forms_left_dirty"],
            # The labels of the prefixes in the field, and deliberately **no**
            # verdict: `classify` is relative to the session that saved, and no
            # session saved here. Asking it anyway read every prefix as
            # `FOREIGN-PREFIX-STORED` on the `ingress-ingress` pair -- the pair
            # where both sessions share one prefix, so `labels` has one entry and
            # any `saver` passed to it mismatches. That is the verdict the parity
            # plan escalates #234 to `blocker` on, for a value `probe` never wrote.
            "stored_prefixes": stored_prefix_labels(stored, labels),
            "notes": verdict["detail"],
        }, indent=2, ensure_ascii=False))
        return verdict["exit_code"]
    finally:
        for side in (first, second):
            side.close()


def do_run(env: Env, browser, pair: str, task_id: int | None, run_id: str, out_path: str) -> int:
    first, second, labels, task_id, transport = stage(
        env, browser, pair, task_id, marker(run_id, "A"))
    try:
        type_marker(second, marker(run_id, "B"))
        save_form(second)
        stored = read_description(second, task_id)
        record = evidence_record(
            run_id=run_id,
            database=env.db,
            target=env.target,
            pair=pair,
            task_id=task_id,
            prefixes={"A": first.env.prefix, "B": second.env.prefix},
            transport=transport,
            stored=stored,
            labels=labels,
            saver="B",
            notes=transport_note(transport),
        )
        with open(out_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        print(json.dumps(record, indent=2, ensure_ascii=False))
        # Only now: A's form is still dirty with A's own marker, and leaving it
        # that way writes it on the way out (#263). What this command is documented
        # to store is what B saved, so A's leftover is discarded -- but *after* the
        # record is on disk and printed. A cleanup step must never be what loses a
        # measurement that needed a deploy and a host to take. B's form is clean;
        # the save is what made it clean.
        discard_quietly(first)
        return 0 if record["verdict"] == CLEAN else 1
    finally:
        for side in (first, second):
            side.close()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("probe", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--env-file")
        sub.add_argument("--db", required=True, help="the database the sessions must serve")
        sub.add_argument("--pair", choices=PAIRS, default=PAIRS[0])
        sub.add_argument("--task-id", type=int, help="the project.task to edit; default: the "
                                                    "test user's own onboarding to-do")
        sub.add_argument("--headed", action="store_true")
        # Both commands take a run id, because both type a marker and a marker
        # has to be unique to the run (#263). Only `run` requires one: `probe` is
        # the step a reader runs first and by hand, so it mints its own.
        sub.add_argument("--run-id", required=(name == "run"),
                         help="the run both markers carry, e.g. WOOW-PEER-<UTC timestamp>"
                              + ("" if name == "run" else
                                 "; default: a minted %s-<UTC timestamp>" % PROBE_RUN_PREFIX))
        if name == "run":
            sub.add_argument("--out", required=True, help="JSONL file; the record is appended")
    report_command = commands.add_parser("report")
    report_command.add_argument("records")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "report":
        with open(args.records, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        result = report(records)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["escalate_issue_234_to_blocker"] else 0

    if args.env_file:
        with open(args.env_file, encoding="utf-8") as handle:
            parse_env_file(handle, os.environ)
    os.environ["ODOO_DB"] = args.db
    env = Env(args.db)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not args.headed,
            # The collaboration transport is WebRTC; the fake device flags are
            # what the parity run already launches with.
            args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
        )
        try:
            if args.command == "probe":
                run_id = args.run_id or mint_run_id(datetime.now(timezone.utc))
                return do_probe(env, browser, args.pair, args.task_id, run_id)
            return do_run(env, browser, args.pair, args.task_id, args.run_id, args.out)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # noqa: BLE001 -- never print an unmasked secret
        message = sanitize_diagnostic(str(error))
        # The prefix shape is a credential wherever it appears, including in a
        # traceback from a session whose Env never loaded.
        message = redact(message, {})
        try:
            message = Env(os.environ.get("ODOO_DB", "")).mask(message)
        except Exception:  # noqa: BLE001 -- a missing variable was the failure
            pass
        print("peer-snapshot run failed: %s" % message, file=sys.stderr)
        sys.exit(2)
