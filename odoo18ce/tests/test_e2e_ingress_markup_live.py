"""The pure parts of `e2e_ingress_markup_live.py`, and the traps they exist for.

The driver needs a host and a browser. What can be tested without either is
every judgement it makes, and there are four places where getting one subtly
wrong would produce a record that reads clean:

1. **A picture's verdict is surface-dependent.** Under Ingress a root-relative
   `src` must resolve *under* the prefix; on the Public origin the same `src`
   must resolve at the origin *root*, and a prefix appearing there at all is a
   `sub_filter` that leaked out of the Ingress asset location. One function
   answers both, and it must not answer the Ingress question on the Public
   surface -- which is what a hardcoded `Surface.HA_INGRESS` would do, the way
   `e2e_ingress_hand_checks.Signals.escapes` was written when it only ever ran
   on one surface.
2. **Prefix escape is `adapter.is_prefix_escape`, never a local rewrite.** The
   shape this file refuses to reimplement is the doubled prefix: still *under*
   the prefix, and still an escape. `test_e2e_ingress_hand_checks.py` exists
   because a review caught exactly that, and the same trap is reachable here.
3. **A stored value's verdict is the gateway's own prefix shape.** It comes
   from `e2e_collab_peer_snapshot_live.ingress_prefixes`, whose shape is
   derived from the gateway template and pinned against it, so this module
   cannot grow a second, drifting regex.
4. **No Supervisor token may reach a record.** Every value written out goes
   through the redaction, including the stored field values the whole run is
   about.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import e2e_collab_peer_snapshot_live as peer  # noqa: E402
import e2e_ingress_markup_live as markup  # noqa: E402
import e2e_menu_action_adapter as adapter  # noqa: E402

HA_ORIGIN = "http://192.0.2.10:8123"
PREFIX = "/api/hassio_ingress/Tok3nTok3nTok3nTok3n"
INGRESS_BASE = HA_ORIGIN + PREFIX
PUBLIC_ORIGIN = "https://odoo.example.test"

PICTURE = "/web/image/res.company/1/logo"
INGRESS = adapter.Surface.HA_INGRESS
PUBLIC = adapter.Surface.PUBLIC


def ingress_verdict(resolved, loaded=True):
    return markup.picture_verdict(INGRESS, HA_ORIGIN, PREFIX, resolved, loaded)


def public_verdict(resolved, loaded=True):
    return markup.picture_verdict(PUBLIC, PUBLIC_ORIGIN, None, resolved, loaded)


# --- 1. The picture verdict, on each surface ----------------------------------


def test_the_prefixed_picture_is_what_the_ingress_surface_wants():
    """#237 checks 1 and 2, #240 (a), #239's image lines: the fix working."""
    assert ingress_verdict(INGRESS_BASE + PICTURE) == markup.UNDER_PREFIX


def test_the_home_assistant_root_is_the_escape_the_fix_removed():
    """The 0.4.9 shape of an unfixed readonly field: asked of the HA root."""
    assert ingress_verdict(HA_ORIGIN + PICTURE) == markup.ESCAPED


def test_the_doubled_prefix_is_an_escape_and_not_a_pass():
    """Still under the prefix, so "did it leave the prefix" answers no.

    The one shape a local rewrite of the judgement loses. It is reachable here
    because every rule in this family prefixes a value that may already carry
    one.
    """
    doubled = INGRESS_BASE + PREFIX + PICTURE
    assert doubled.startswith(INGRESS_BASE)
    assert ingress_verdict(doubled) == markup.ESCAPED


def test_the_origin_root_is_what_the_public_surface_wants():
    """#237 check 3: the half that says a `sub_filter` did not leak."""
    assert public_verdict(PUBLIC_ORIGIN + PICTURE) == markup.AT_ORIGIN_ROOT


def test_an_ingress_prefix_on_the_public_origin_is_an_escape():
    """A leaked rule: the Public origin serves no shim and no rewrite.

    This is the assertion that fails if the function judges every surface as
    Ingress -- under that reading the path is simply "not the HA origin" and
    passes.
    """
    leaked = PUBLIC_ORIGIN + PREFIX + PICTURE
    assert public_verdict(leaked) == markup.ESCAPED


def test_the_two_surfaces_disagree_about_the_same_resolved_url():
    """The whole reason the surface is a parameter and not a constant."""
    at_root = HA_ORIGIN + PICTURE
    assert ingress_verdict(at_root) == markup.ESCAPED
    assert markup.picture_verdict(PUBLIC, HA_ORIGIN, None, at_root, True) == markup.AT_ORIGIN_ROOT


def test_the_escape_half_of_the_verdict_is_the_adapter_s():
    """Not a tautology: it fails if the module stops delegating.

    Every url is asked of both, and the verdict's escape branch has to agree
    with the adapter on every one of them.
    """
    cases = [
        (INGRESS, HA_ORIGIN, PREFIX, INGRESS_BASE + PICTURE),
        (INGRESS, HA_ORIGIN, PREFIX, HA_ORIGIN + PICTURE),
        (INGRESS, HA_ORIGIN, PREFIX, INGRESS_BASE + PREFIX + PICTURE),
        (INGRESS, HA_ORIGIN, PREFIX, INGRESS_BASE),
        (PUBLIC, PUBLIC_ORIGIN, None, PUBLIC_ORIGIN + PICTURE),
        (PUBLIC, PUBLIC_ORIGIN, None, PUBLIC_ORIGIN + PREFIX + PICTURE),
    ]
    for surface, origin, prefix, url in cases:
        escaped = adapter.is_prefix_escape(url, surface, origin, prefix)
        verdict = markup.picture_verdict(surface, origin, prefix, url, True)
        assert (verdict == markup.ESCAPED) is escaped, url


def test_a_picture_that_resolved_right_but_never_arrived_is_not_a_pass():
    """`complete && naturalWidth > 0` is the half that says the byte arrived.

    A rule can prefix a URL correctly and still name nothing, which is a 404
    and a `http_4xx_5xx` -- but the picture verdict has to say so on its own,
    because the signal counts are for the whole page.
    """
    assert ingress_verdict(INGRESS_BASE + PICTURE, loaded=False) == markup.NOT_LOADED
    assert public_verdict(PUBLIC_ORIGIN + PICTURE, loaded=False) == markup.NOT_LOADED


def test_an_escape_outranks_a_picture_that_did_not_load():
    """Both are true of an unfixed field under Ingress; the escape is the finding."""
    assert ingress_verdict(HA_ORIGIN + PICTURE, loaded=False) == markup.ESCAPED


def test_no_picture_at_all_is_named_rather_than_passed():
    """An empty screen must not read as a clean one.

    The shape this catches is a selector that stopped matching: #240's own row
    warns that a full-HTML value renders no editor, and #237's that the
    `cssAssetId` branch renders a different target.
    """
    assert ingress_verdict(None) == markup.ABSENT
    assert markup.screen_verdict([]) == markup.ABSENT


def test_a_third_party_picture_is_not_this_surface_s_question():
    """And it is *named* as such rather than counted as a prefixed picture.

    `is_prefix_escape` answers `False` both for "this is fine" and for "this is
    none of my business", so a verdict built on it alone would report
    `UNDER-PREFIX` -- asserting the prefix was involved when it never was.
    """
    assert ingress_verdict("https://cdn.example.test/logo.png") == markup.NOT_A_PREFIX_QUESTION


# --- The screen's verdict: the worst picture on it ----------------------------


def test_the_screen_takes_the_worst_verdict_of_its_pictures():
    assert markup.screen_verdict([markup.UNDER_PREFIX, markup.UNDER_PREFIX]) == markup.UNDER_PREFIX
    assert markup.screen_verdict([markup.UNDER_PREFIX, markup.NOT_LOADED]) == markup.NOT_LOADED
    assert markup.screen_verdict([markup.NOT_LOADED, markup.ESCAPED]) == markup.ESCAPED
    assert markup.screen_verdict([markup.UNDER_PREFIX, markup.ABSENT]) == markup.ABSENT


def test_every_picture_verdict_has_a_rank():
    """A new verdict cannot be added without deciding how bad it is."""
    for verdict in markup.PICTURE_VERDICTS:
        assert verdict in markup.PICTURE_SEVERITY


def test_a_screen_verdict_is_a_pass_only_on_the_two_expected_values():
    """`PASSING` is what the evidence table reads; the rest are findings."""
    assert markup.PASSING == frozenset({markup.UNDER_PREFIX, markup.AT_ORIGIN_ROOT})
    for verdict in markup.PICTURE_VERDICTS:
        assert markup.is_pass(verdict) is (verdict in markup.PASSING)


def test_the_expected_verdict_for_a_surface_is_the_one_the_run_compares_against():
    """Each surface has exactly one passing verdict, and they are not the same."""
    assert markup.expected_verdict(INGRESS) == markup.UNDER_PREFIX
    assert markup.expected_verdict(PUBLIC) == markup.AT_ORIGIN_ROOT


# --- 3. The stored value -----------------------------------------------------


def test_a_root_relative_stored_value_is_clean():
    """#237 check 4, #240 (b), #238's two fields: nothing stored a prefix."""
    stored = '<p>x</p><img src="%s">' % PICTURE
    assert markup.stored_verdict(stored) == (markup.CLEAN, 0)


def test_a_stored_prefix_is_the_finding_the_read_back_exists_for():
    stored = '<img src="%s%s">' % (PREFIX, PICTURE)
    assert markup.stored_verdict(stored) == (markup.PREFIX_STORED, 1)


def test_two_different_stored_prefixes_are_both_counted():
    other = "/api/hassio_ingress/0therT0kenMoreThan16"
    stored = '<img src="%s/a"><img src="%s/b">' % (PREFIX, other)
    assert markup.stored_verdict(stored) == (markup.PREFIX_STORED, 2)


def test_an_empty_html_field_is_clean_rather_than_an_error():
    """An html field with no value comes back `False` from the ORM, not `""`."""
    for empty in (None, "", False):
        assert markup.stored_verdict(empty) == (markup.CLEAN, 0)


def test_the_stored_shape_is_the_peer_snapshot_s_and_not_a_second_regex():
    """Not a tautology: it fails if this module grows its own pattern.

    The shape is the gateway's `$safe_ingress_path` map, and
    `test_e2e_collab_peer_snapshot.py` derives it from the template and refuses
    a difference. A second copy here would drift away from the add-on without
    anything noticing.
    """
    assert markup.ingress_prefixes is peer.ingress_prefixes
    assert not any(
        isinstance(value, re.Pattern) and "hassio_ingress" in value.pattern
        for value in vars(markup).values()
    )


def test_a_token_too_short_for_the_gateway_is_not_a_prefix():
    """The shape's own bound, reached through the delegation."""
    assert markup.stored_verdict('<img src="/api/hassio_ingress/short/a">') == (markup.CLEAN, 0)


# --- 4. Redaction ------------------------------------------------------------


def test_the_stored_value_in_a_record_carries_no_token():
    """The run reads a field whose whole point is what prefix is in it."""
    stored = '<img src="%s%s">' % (PREFIX, PICTURE)
    record = markup.evidence_record(
        check="readonly-plain", issue=237, run_id="WOOW-MARKUP-20261001T000000Z",
        database="odoo_parity", target="local", surface=INGRESS,
        screen="/odoo/project.task/7", pictures=[], stored={"project.task.description": stored},
    )
    line = markup.json.dumps(record, sort_keys=True)
    assert PREFIX not in line
    assert "Tok3nTok3nTok3nTok3n" not in line
    assert "<ingress:" in line


def test_the_redaction_is_the_peer_snapshot_s():
    """Same reason as the shape: one implementation, already tested."""
    assert markup.redact is peer.redact


def test_a_clean_value_survives_redaction_unchanged():
    stored = '<p>x</p><img src="%s">' % PICTURE
    assert markup.redact(stored, {}) == stored


# --- The record and the registry ---------------------------------------------


def test_the_record_names_its_schema_and_issue():
    record = markup.evidence_record(
        check="readonly-plain", issue=237, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x", pictures=[], stored={},
    )
    assert record["schema"] == markup.EVIDENCE_SCHEMA
    assert record["issue"] == 237
    assert record["check"] == "readonly-plain"
    assert record["surface"] == INGRESS.value


def test_a_record_with_no_reading_is_not_run_rather_than_a_pass():
    record = markup.evidence_record(
        check="readonly-plain", issue=237, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x", pictures=None, stored={},
    )
    assert record["verdict"] == markup.NOT_RUN


def test_the_record_s_verdict_is_the_screen_s():
    record = markup.evidence_record(
        check="readonly-plain", issue=237, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x",
        pictures=[{"verdict": markup.UNDER_PREFIX}, {"verdict": markup.ESCAPED}], stored={},
    )
    assert record["verdict"] == markup.ESCAPED


def test_a_stored_prefix_fails_the_record_even_when_the_screen_rendered():
    """#237 check 4's point: the screen passing says nothing about the write."""
    stored = '<img src="%s%s">' % (PREFIX, PICTURE)
    record = markup.evidence_record(
        check="codeview", issue=240, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x",
        pictures=[{"verdict": markup.UNDER_PREFIX}],
        stored={"res.users.signature": stored},
    )
    assert record["verdict"] == markup.PREFIX_STORED
    assert record["stored_verdict"] == markup.PREFIX_STORED


@pytest.mark.parametrize("check", sorted(markup.CHECKS))
def test_every_check_the_parser_takes_has_a_branch_and_a_row(check):
    """The parser's choices, `run`'s branches and the register cannot drift."""
    assert hasattr(markup, "do_" + check.replace("-", "_"))
    row = markup.CHECKS[check]
    assert row["issue"] in {234, 237, 238, 239, 240}
    assert isinstance(row["writes"], bool)
    assert row["surfaces"]
    for surface in row["surfaces"]:
        assert surface in {"ingress", "public"}


def test_every_register_row_this_module_carries_has_at_least_one_check():
    """#243's register has five rows; #234's is the peer snapshot's own module."""
    covered = {row["issue"] for row in markup.CHECKS.values()}
    assert covered == {237, 238, 239, 240}


def test_the_read_only_checks_are_named_so_they_can_be_run_first():
    """ADR 0012: a run says what it writes, and the cheap read-only checks go
    first so a failure costs nothing on the host."""
    read_only = {name for name, row in markup.CHECKS.items() if not row["writes"]}
    assert read_only
    assert all(not markup.CHECKS[name]["writes"] for name in read_only)
    assert markup.read_only_first(list(markup.CHECKS)) == sorted(
        markup.CHECKS, key=lambda name: (markup.CHECKS[name]["writes"], name))


def test_the_full_html_seed_value_parses_with_a_non_empty_head():
    """`computeContainsComplexHTML()` is what chooses the iframe path, and it
    chooses it for a value whose parse yields a non-empty `<head>`. A seed
    without one would render the plain path and measure check 1 twice."""
    assert "<head>" in markup.FULL_HTML_VALUE
    assert "<style" in markup.FULL_HTML_VALUE
    assert 'src="/' in markup.FULL_HTML_VALUE
    assert PREFIX not in markup.FULL_HTML_VALUE


def test_the_seeded_value_is_root_relative_so_the_read_back_means_something():
    """Check 4 reads the field back expecting root-relative. If the seed were
    written with a prefix the check could not tell a write from the seed."""
    assert markup.stored_verdict(markup.FULL_HTML_VALUE) == (markup.CLEAN, 0)


def test_the_signature_seed_is_a_fragment_and_not_full_html():
    """#240's row: a full-HTML value renders the readonly viewer and no editor,
    so `toggleCodeView` never reaches the assignment the rules patch."""
    assert "<head>" not in markup.SIGNATURE_VALUE
    assert 'src="/' in markup.SIGNATURE_VALUE
    assert markup.stored_verdict(markup.SIGNATURE_VALUE) == (markup.CLEAN, 0)


def test_the_marker_names_its_run():
    assert markup.marker_for("WOOW-MARKUP-20261001T073009Z").endswith("WOOW-MARKUP-20261001T073009Z")
    assert markup.marker_for("A") != markup.marker_for("B")


def test_the_scratch_task_name_says_it_is_this_run_s_and_disposable():
    """The run must be able to find and delete what it made, and a reader of
    the host must be able to tell it from the onboarding to-do #235 reads."""
    name = markup.scratch_task_name("WOOW-MARKUP-20261001T073009Z")
    assert "WOOW-MARKUP-20261001T073009Z" in name
    assert "scratch" in name.lower()


def test_the_report_counts_each_verdict_and_names_the_failures():
    records = [
        {"check": "readonly-plain", "issue": 237, "surface": "ha_ingress", "verdict": markup.UNDER_PREFIX},
        {"check": "readonly-plain", "issue": 237, "surface": "public", "verdict": markup.AT_ORIGIN_ROOT},
        {"check": "codeview", "issue": 240, "surface": "ha_ingress", "verdict": markup.ESCAPED},
    ]
    summary = markup.summarise(records)
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["failures"] == ["codeview/ha_ingress: " + markup.ESCAPED]


def test_the_report_says_which_checks_never_ran():
    """A partial run has to be legible as partial; #243 may be cut short."""
    summary = markup.summarise([
        {"check": "readonly-plain", "issue": 237, "surface": "ha_ingress", "verdict": markup.UNDER_PREFIX},
    ])
    assert "readonly-iframe" in summary["not_run"]
    assert "readonly-plain" not in summary["not_run"]


def test_a_check_s_extra_readings_cannot_overwrite_the_verdict():
    """`extra` is merged flat into the record, so a key collision would let a
    flow silently replace the verdict or the schema with one of its own
    readings. The eight flows use no such key today; the guard is for the ninth.
    """
    with pytest.raises(ValueError, match="verdict"):
        markup.evidence_record(
            check="codeview", issue=240, run_id="R", database="odoo_parity",
            target="local", surface=INGRESS, screen="/x",
            pictures=[{"verdict": markup.ESCAPED}], stored={},
            extra={"verdict": markup.UNDER_PREFIX},
        )


def test_an_extra_reading_with_its_own_name_is_kept():
    record = markup.evidence_record(
        check="codeview", issue=240, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x",
        pictures=[{"verdict": markup.UNDER_PREFIX}], stored={},
        extra={"uid": 2, "debug": "1"},
    )
    assert record["uid"] == 2 and record["debug"] == "1"
    assert record["verdict"] == markup.UNDER_PREFIX


def test_every_flow_s_extra_keys_stay_clear_of_the_record_s_own():
    """A standing check on the names the eight flows actually use."""
    used = {"task_id", "created_task", "deleted_task", "rendered_iframe", "sandbox",
            "mailing_id", "uid", "signature_before", "signature_restored", "debug",
            "code_view_shown", "code_view_bytes", "element", "dialog", "editor",
            "replace_control", "theme", "saved", "unsaved_after_save", "body_arch_before",
            "body_restored", "revisions", "has_description_history", "form"}
    assert not (used & markup.RESERVED_RECORD_KEYS)


# --- The entrypoint, and the ordering bug that made the driver unrunnable ------


def test_the_entrypoint_guard_comes_after_every_handler():
    """The driver was once entirely unrunnable, and no test noticed.

    `if __name__ == "__main__": raise SystemExit(main())` sat above the eight
    `do_*` definitions, so executing the file -- the only way it is ever used --
    reached `handler_for` before those names were bound and every subcommand died
    with `KeyError: 'do_readonly_plain'`. Importing the module binds everything
    first, which is why `hasattr` passed and the bug survived a green suite and a
    `--help` smoke test (both exit before the lookup).
    """
    source = open(markup.__file__, encoding="utf-8").read().split("\n")
    guard = [n for n, line in enumerate(source) if line.startswith('if __name__ ==')]
    handlers = [n for n, line in enumerate(source) if line.startswith("def do_")]
    assert guard, "the module has no __main__ guard"
    assert handlers
    assert guard[0] > max(handlers), (
        "the __main__ guard is above a do_* handler, so running the file cannot "
        "resolve it: move the guard to the end of the module")


def test_resolving_every_handler_is_what_running_the_file_does():
    """`handler_for`, not `hasattr` -- the lookup the driver actually performs."""
    for check in markup.CHECKS:
        assert callable(markup.handler_for(check))


# --- A URL the prefix has no claim on ------------------------------------------


@pytest.mark.parametrize("url", ["data:image/png;base64,iVBORw0KGgo=",
                                 "blob:http://192.0.2.10:8123/a-b-c",
                                 "https://cdn.example.test/x.png"])
def test_a_source_the_prefix_has_no_claim_on_is_named_not_passed(url):
    """`data:` and `blob:` sources are routine in the mail designer and the
    website preview, so this is the common case, not an edge one."""
    assert ingress_verdict(url) == markup.NOT_A_PREFIX_QUESTION
    assert not markup.is_pass(markup.NOT_A_PREFIX_QUESTION)


def test_such_a_source_neither_outvotes_a_real_picture_nor_rescues_a_screen():
    assert markup.screen_verdict(
        [markup.UNDER_PREFIX, markup.NOT_A_PREFIX_QUESTION]) == markup.UNDER_PREFIX
    assert markup.screen_verdict(
        [markup.ESCAPED, markup.NOT_A_PREFIX_QUESTION]) == markup.ESCAPED
    # All of them: the screen measured nothing, which is ABSENT for the same
    # reason an empty screen is.
    assert markup.screen_verdict([markup.NOT_A_PREFIX_QUESTION]) == markup.ABSENT


def test_the_same_origin_test_is_the_adapter_s_netloc():
    """One notion of same-origin, so this cannot disagree with is_prefix_escape."""
    assert markup.is_prefix_question(INGRESS_BASE + PICTURE, INGRESS, HA_ORIGIN)
    assert not markup.is_prefix_question("data:image/png;base64,x", INGRESS, HA_ORIGIN)
    # A default port spelled out is still the same origin, which is the case a
    # string comparison would get wrong.
    assert markup.is_prefix_question("https://odoo.example.test:443" + PICTURE,
                                     PUBLIC, PUBLIC_ORIGIN)


# --- A stored prefix is never erased ------------------------------------------


def test_a_stored_prefix_outranks_an_unreadable_screen():
    """The worst finding this run can make must not be filed as NOT-RUN.

    `summarise` skips `NOT-RUN`, and the check *was* seen so it is not in
    `not_run` either -- so the old order dropped a prefix-reached-a-write out of
    the tally entirely. `do_readonly_iframe` reaches this: it returns no pictures
    when the field renders no iframe, and still reads the field back.
    """
    stored = '<img src="%s%s">' % (PREFIX, PICTURE)
    record = markup.evidence_record(
        check="readonly-iframe", issue=237, run_id="R", database="odoo_parity",
        target="local", surface=INGRESS, screen="/x", pictures=None,
        stored={"project.task.description": stored},
    )
    assert record["verdict"] == markup.PREFIX_STORED
    summary = markup.summarise([record])
    assert summary["failed"] == 1
    assert summary["failures"] == ["readonly-iframe/ha_ingress: " + markup.PREFIX_STORED]


# --- The values this driver writes name their run -----------------------------


def test_both_seeded_values_name_the_run_that_wrote_them():
    """ADR 0012 / live-tier.md: a writing step is marked with its run id. These
    two replace a real user's signature and a real mailing's body, so attributing
    them later matters more than for a scratch record that can be deleted."""
    run_id = "WOOW-MARKUP-20261001T073009Z"
    assert run_id in markup.signature_value(run_id)
    assert run_id in markup.mailing_body_value(run_id)
    # And they are still the shapes the checks need.
    assert "<head>" not in markup.signature_value(run_id)
    assert 'src="/' in markup.signature_value(run_id)
    assert markup.stored_verdict(markup.signature_value(run_id)) == (markup.CLEAN, 0)
    assert markup.stored_verdict(markup.mailing_body_value(run_id)) == (markup.CLEAN, 0)


def test_a_retried_check_is_counted_once_by_its_last_record():
    """A run that re-ran a check after fixing a fixture must not be tallied twice.

    #243's own run retried five of the eight checks -- a selector, a missing
    editable wait, a fixture that was not an attachment -- and every attempt is
    kept in the records, because a past reading is what it recorded. But the
    *verdict* is the last attempt, so the tally has to dedupe by check and
    surface or it reports a fixed check as a failure forever.
    """
    records = [
        {"check": "media-image-todo", "issue": 239, "surface": "ha_ingress", "verdict": markup.ABSENT},
        {"check": "media-image-todo", "issue": 239, "surface": "ha_ingress", "verdict": markup.UNDER_PREFIX},
        {"check": "media-image-todo", "issue": 239, "surface": "public", "verdict": markup.AT_ORIGIN_ROOT},
    ]
    summary = markup.summarise(records)
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["failures"] == []
    assert summary["attempts"] == 3


def test_the_two_surfaces_of_one_check_are_counted_separately():
    records = [
        {"check": "codeview", "issue": 240, "surface": "ha_ingress", "verdict": markup.UNDER_PREFIX},
        {"check": "codeview", "issue": 240, "surface": "public", "verdict": markup.ESCAPED},
    ]
    summary = markup.summarise(records)
    assert summary["passed"] == 1 and summary["failed"] == 1
