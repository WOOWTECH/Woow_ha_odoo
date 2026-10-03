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
import base64
import inspect
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
    for value in vars(markup).values():
        if isinstance(value, re.Pattern) and "hassio_ingress" in value.pattern:
            assert value is peer.INGRESS_PREFIX_SHAPE, (
                "this module may hold the peer snapshot's own shape and nothing else "
                "that matches an Ingress prefix")
    # And not in a string either (#266). The document-operand probe reads the
    # served method for a *prefixed* literal, and it spelled the shape out in
    # JavaScript -- twice -- until the shape was handed in instead. A copy there
    # is as free to drift as a second `re.Pattern` and is invisible to the loop
    # above, so both probes are checked as text.
    for name in ("_DOCUMENT_OPERAND_PROBE", "_RULE_PROBE"):
        assert "hassio_ingress" not in getattr(markup, name), name
    assert "spec.prefix_shape" in markup._DOCUMENT_OPERAND_PROBE
    assert "prefix_shape" in inspect.getsource(markup.document_operand_reading)
    assert "INGRESS_PREFIX_SHAPE" in inspect.getsource(markup.document_operand_reading)


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
    """A standing check on the names the nine flows actually use."""
    used = {"task_id", "created_task", "deleted_task", "rendered_iframe", "sandbox",
            "mailing_id", "uid", "signature_before", "signature_restored", "debug",
            "code_view_shown", "code_view_bytes", "element", "dialog", "editor",
            "replace_control", "theme", "saved", "unsaved_after_save", "body_arch_before",
            "body_restored", "revisions", "has_description_history", "form",
            # #266's two fixture-building media checks
            "fixture", "fixture_removed", "element_after_select", "operand",
            "replace_control_present", "replace_control_visible",
            "replace_control_found_in", "discarded", "read_back_error",
            # #274's reading: where the mailing came from
            "mailing_source"}
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


# --- 5. The ambient-row figure (#264) -----------------------------------------
#
# Source pins. The counting needs a browser and a host, and what #264 fixed was
# not a wrong value but a missing reading: #243's run drove the website editor,
# whose preview iframes load tracked pages, and its evidence could only state an
# absolute count read on the host afterwards.


def test_each_surface_reads_the_ambient_rows_it_left():
    source = inspect.getsource(markup.run_check)
    assert "adapter.ambient_accounting(" in source
    assert "adapter.SessionAmbientDriver(side, mask=env.mask)" in source
    assert "command=check" in source, "the check name is this driver's command"
    assert "append=True" in source, "the records append per invocation, so the figure does too"


def test_the_figure_is_per_surface_because_the_session_is():
    """Each surface opens its own `Side`, so the count goes over that session's
    own RPC and the record names which surface it was taken on. A delta over a
    database-wide count cannot be split between two surfaces afterwards."""
    source = inspect.getsource(markup.run_check)
    assert source.index("open_one(env, browser, surface)") < source.index("ambient_accounting(")
    assert "surface, out_path, command=check" in source


def test_the_denominator_counts_the_documents_the_editor_fetched_for_itself():
    """`side.goto` is the only navigation call in this file, and it is not the
    only navigation: `media-image-website` clicks Edit, and the editor loads the
    website page into two preview iframes. Those are the page views that write
    the rows being counted."""
    source = inspect.getsource(markup.run_check)
    assert "navigation_basis=adapter.AMBIENT_BASIS_DOCUMENTS" in source


def test_a_surface_that_already_has_a_record_does_not_get_a_second_one():
    """`summarise` reads the *last* record for a check and surface as its
    verdict, so a failure after the record is on disk -- the accounting raises
    when it is a passing run's only failure -- must not append a `NOT-RUN` line
    that overwrites a verdict this run measured."""
    source = inspect.getsource(markup.run_check)
    assert "if surface.value in kept:" in source
    assert source.index("if surface.value in kept:") < source.index('"the surface could not be driven')


def test_the_module_says_where_the_figure_goes_and_which_check_needs_it():
    said = " ".join(markup.__doc__.split())
    assert adapter.ambient_summary_path("markup.jsonl") in said
    assert "media-image-website" in said
    assert "#256" in said and "#264" in said
    assert "counts only" in said.lower()


def test_a_figure_that_could_not_be_written_does_not_cost_the_other_surface_its_run():
    """`ambient_accounting` raises when the figure is a passing run's only failure
    (#256). Raised where it arrives, on the first surface of a `--surface both`
    run, it would leave the second surface never opened, never measured and with
    no record at all -- not even the `NOT-RUN` fallback, so `summarise` could not
    report the gap either. It is held and raised once every surface has run."""
    source = inspect.getsource(markup.run_check)
    assert "unaccounted.append(error)" in source
    assert "raise unaccounted[0]" in source
    assert source.index("unaccounted.append(error)") < source.index("raise unaccounted[0]")
    # And after the loop, not inside it: the raise sits outside the `for`.
    lines = source.splitlines()
    loop = next(len(line) - len(line.lstrip()) for line in lines if line.lstrip().startswith("for name in"))
    raised = next(len(line) - len(line.lstrip()) for line in lines if line.lstrip() == "raise unaccounted[0]")
    assert raised < loop


def test_a_record_counts_as_kept_only_once_it_is_on_disk():
    """The guard above reads `kept` as "this surface's record is on disk", and the
    `--out` write is the one step in `keep` that can fail. Marking it kept first
    would make that claim false in exactly the case it is consulted, and would
    count a line the file never got as something the run recorded."""
    source = inspect.getsource(markup.run_check)
    assert source.index('open(out_path, "a"') < source.index("kept.add(")
    assert source.index('open(out_path, "a"') < source.index("records.append(")


# --- #239's two owed lines, and the fixtures they needed (#266) ---------------
#
# #243's run reached both and measured neither, for the same reason both times:
# nothing on the host could execute the branch. So the fixtures *are* the
# measurement, and what they contain is as load-bearing as any verdict here.


ATTACHMENT = {"id": 7, "name": "woow-document-fixture-woow-x.txt",
              "mimetype": "text/plain", "checksum": "abc123", "image_src": None}

IMAGE_ATTACHMENT = {"id": 8, "name": "woow-image-fixture-woow-x.png",
                    "mimetype": "image/png", "checksum": "def456",
                    "image_src": "/web/image/8-def456/woow-image-fixture-woow-x.png"}

MEDIA_FLOWS = {
    "media-image-todo": (markup.do_media_image_todo,
                         markup._media_image_todo_after_seeding),
    "media-image-website": (markup.do_media_image_website, markup._website_after_seeding),
    "media-document-todo": (markup.do_media_document_todo,
                            markup._media_document_todo_after_seeding),
    "media-document-mailing": (markup.do_media_document_mailing,
                               markup._document_mailing_after_seeding),
}


def test_the_media_flows_this_file_pins_are_every_media_check():
    """So a tenth check cannot be added without being pinned below."""
    assert set(MEDIA_FLOWS) == {name for name in markup.CHECKS if name.startswith("media-")}


@pytest.mark.parametrize("check", sorted(MEDIA_FLOWS))
def test_every_media_check_records_data_original_src(check):
    """#266 asks for the attribute on **both surfaces for every media check**.

    Including the two document ones, where it is structurally absent: an `<a>`
    has no `src` for the image tools to have optimised, so `None` is the reading
    and an omitted key could not be told apart from a record taken before the
    key existed. The verdict of either document line turns on the `href`, not on
    this -- which is exactly why it has to be recorded rather than inferred.
    """
    source = "".join(inspect.getsource(flow) for flow in MEDIA_FLOWS[check])
    assert '"data_original_src"' in source
    assert 'get_attribute("data-original-src")' in source


def test_the_website_fixture_compares_an_attachment_against_itself():
    """The one property the measurement rests on: `data-original-src` holds the
    attachment's own `image_src`, which is the comparison's other operand. A
    fixture whose two sides were different values could never select a tile, and
    would read exactly like a rule that failed."""
    section = markup.website_fixture_section("WOOW-X", IMAGE_ATTACHMENT)
    assert 'src="%s"' % IMAGE_ATTACHMENT["image_src"] in section
    assert 'data-original-src="%s"' % IMAGE_ATTACHMENT["image_src"] in section


def test_the_website_fixture_carries_what_stops_the_attribute_being_overwritten():
    """`loadImageInfo` early-returns only when **both** `data-original-src` and
    `data-mimetype-before-conversion` are present (`image_processing.js:490-496`).

    Without the second one it would re-fetch the image info in the window
    between the click and the dialog and overwrite the first with the
    root-relative value the ORM just returned -- so under Ingress the branch
    would compare two unprefixed values and pass whether or not rule 2 shipped.
    That is a false pass, and this attribute is what prevents it."""
    section = markup.website_fixture_section("WOOW-X", IMAGE_ATTACHMENT)
    assert 'data-mimetype-before-conversion="image/png"' in section
    assert 'data-original-id="8"' in section


def test_the_website_fixture_is_root_relative_and_names_its_run():
    """It is written into stored arch, so a prefix in it would be a prefix in the
    database -- and `live-tier.md` wants every writing step marked with its run."""
    section = markup.website_fixture_section("WOOW-X", IMAGE_ATTACHMENT)
    assert markup.stored_verdict(section) == (markup.CLEAN, 0)
    assert "WOOW-X" in section
    assert 'alt="%s"' % markup.FIXTURE_IMAGE_ALT in section


def test_the_website_check_finds_its_own_image_and_not_the_first_visible_one():
    """#243 picked "the first visible image" in the preview frame and got
    `/web/image/website/1/logo/My%20Website` -- a record-field image with no
    `data-original-src` at all, which is how that run measured nothing. The
    element under test is named now, so another image cannot stand in for it."""
    source = inspect.getsource(markup._website_after_seeding)
    assert 'img[alt="%s"]' in source and "FIXTURE_IMAGE_ALT" in source
    assert 'locator("img")' not in source


def test_the_website_check_reads_the_attribute_again_after_the_click():
    """`ImageTools._initializeImage` **deletes** the whole `data-original-*`
    group when `loadImage(data-original-src)` is rejected
    (`snippets.options.js:7679-7686`), and that runs between the click and the
    dialog. A record carrying only the before-reading could not tell "the
    attribute was dropped" from "the comparison disagreed"."""
    source = inspect.getsource(markup._website_after_seeding)
    assert '"element_after_select"' in source
    assert source.index('extra["element"]') < source.index("image.click()")
    assert source.index("image.click()") < source.index('extra["element_after_select"]')


def test_each_surface_builds_its_own_fixture_page():
    """`U-D3`'s reason: the two surfaces are separate invocations against one
    database, so a shared name would make the second reuse the first's page."""
    names = {markup.fixture_page_name("WOOW-X", surface)
             for surface in (INGRESS, PUBLIC)}
    assert len(names) == 2
    for name in names:
        assert "woow-x" in name
        assert "_" not in name


def test_the_document_fixture_is_the_dialogs_own_spelling():
    """`createElements` builds `` /web/content/${id}?unique=${checksum}&download=true ``,
    sets `title` and `data-mimetype` (`document_selector.js:69-89`), and
    `media_dialog.js:260` adds `o_image`. A different shape would measure a
    document no user has."""
    markup_text = markup.document_link_markup(ATTACHMENT)
    assert 'class="o_image"' in markup_text
    assert 'href="/web/content/7?unique=abc123&amp;download=true"' in markup_text
    assert 'data-mimetype="text/plain"' in markup_text
    assert ATTACHMENT["name"] in markup_text


def test_the_document_fixture_carries_a_query_string_the_comparison_must_strip():
    """Rule 3's left operand is compared against
    `getAttribute('href').replace(/[?].*/, '')`. A fixture with no query string
    leaves that half of the premise unexercised, so the strip is part of what
    this fixture is for."""
    assert "?" in markup.document_link_markup(ATTACHMENT)
    assert "/web/content/7?" in markup.document_link_markup(ATTACHMENT)


def test_the_document_fixture_body_is_root_relative_and_names_its_run():
    body = markup.mailing_document_body_value("WOOW-X", ATTACHMENT)
    assert markup.stored_verdict(body) == (markup.CLEAN, 0)
    assert "WOOW-X" in body
    assert markup.document_link_markup(ATTACHMENT) in body


def test_the_document_check_looks_for_the_control_before_falling_back():
    """#266 asks for the tile *or* the control that was looked for. Both are
    recorded: `#media-replace` is un-hidden for any `.o_image`, but the same
    function hides the whole toolbar for a media whose `data-mimetype` is not an
    image -- which every dialog-inserted document has. So the fallback is
    expected to be the one that works, and a record that did not say which
    control opened the dialog would not answer the question."""
    source = inspect.getsource(markup._document_mailing_after_seeding)
    assert "REPLACE_LEGACY" in source
    assert '"replace_control_present"' in source
    assert '"replace_control_visible"' in source
    assert '"dblclick"' in source
    assert source.index('"replace_control_present"') < source.index('"dblclick"')


def test_the_document_check_reads_the_two_mailing_fields_back_into_stored():
    """Nothing here is meant to be saved, and that sentence is not the guarantee.
    Clicking inside the designer's editable can leave the form dirty, and an Odoo
    form persists a dirty editor on `beforeunload` and on `visibilitychange`
    without the record being dirty (#263 is the same mechanism on the To-do
    form). The read-back is in `stored`, where `stored_verdict` names a prefix
    that reached the database."""
    source = inspect.getsource(markup._document_mailing_leaving)
    assert '"mailing.mailing.body_arch"' in source
    assert '"mailing.mailing.body_html"' in source
    assert "DISCARD_BUTTON" in source
    assert "return {" in source and '"stored": stored' in source


# Anything that undoes part of a fixture. A handler's error path has to name at
# least one of these; which one depends on what that check made.
CLEANUP_NAMES = (
    "remove_media_task", "_remove_media_todo_quietly", "_leave_media_todo",
    "remove_website_fixture_page", "_leave_website_media",
    "_remove_fixture_attachment", "_restore_mailing_body",
    # #274: the document mailing check now removes a mailing it made, and
    # restores one it borrowed -- two outcomes, so two names.
    "_remove_document_mailing_fixture", "_restore_borrowed_mailing_body",
)

SEEDING_FLOWS = {
    "media-image-todo": (markup.do_media_image_todo,
                         markup._media_image_todo_after_seeding,
                         markup._leave_media_todo),
    "media-document-todo": (markup.do_media_document_todo,
                            markup._media_document_todo_after_seeding,
                            markup._leave_media_todo),
    "media-image-website": (markup.do_media_image_website,
                            markup._website_after_seeding,
                            markup._leave_website_media),
    "media-document-mailing": (markup.do_media_document_mailing,
                               markup._document_mailing_after_seeding,
                               markup._document_mailing_leaving),
}


@pytest.mark.parametrize("check", sorted(SEEDING_FLOWS))
def test_a_fixture_building_check_cannot_leave_its_fixture_behind(check):
    """Every exit from a seeding check goes through its one leaving function.

    This is the trap and not a tidiness rule. All four create their fixture
    *before* the first navigation, and `run_check` **discards a handler's return
    value when it raises** -- so a step failing between the seed and the verdict
    leaves a public `ir.attachment`, and a scratch to-do or a `website.page`
    beside it, on the host with nothing in the evidence naming them. Two of the
    four were written exactly that way and a review caught it.
    """
    handler, browser_half, leaving = SEEDING_FLOWS[check]

    # The browser half runs entirely after the seed, so every one of its exits
    # -- and three of the four are give-up paths -- goes through one door.
    returns = [line for line in inspect.getsource(browser_half).splitlines()
               if line.strip().startswith("return ")]
    assert returns, browser_half.__name__
    assert all(leaving.__name__ + "(" in line for line in returns), (
        "%s has a return that does not go through %s"
        % (browser_half.__name__, leaving.__name__))

    # The handler holds the seed and the browser half inside **two** guards, so
    # a `KeyboardInterrupt` or a `SystemExit` removes the fixture too and not
    # only an ordinary failure.
    source = inspect.getsource(handler)
    assert "except Exception" in source and "except BaseException:" in source, handler.__name__
    ordinary, interrupted = source.split("except BaseException:")
    ordinary = ordinary.split("except Exception")[-1]
    for where, body in (("except Exception", ordinary), ("except BaseException", interrupted)):
        assert any(name in body for name in CLEANUP_NAMES), (
            "%s's %s path removes nothing it created" % (handler.__name__, where))


@pytest.mark.parametrize("seeder", [markup.seed_media_task, markup.seed_website_fixture_page,
                                   markup.seed_document_mailing_fixture])
def test_a_seeder_that_raises_half_way_removes_what_it_already_made(seeder):
    """All three raise *after* a `create`: `seed_media_task` when the image
    attachment has no `image_src`, `seed_website_fixture_page` when
    `website.new_page` returns no url, `seed_document_mailing_fixture` when the
    attachment or the body write fails on a mailing it has already made (#274).
    The row already exists at that point."""
    source = inspect.getsource(seeder)
    assert "except BaseException:" in source
    assert source.index("create_fixture_attachment(") < source.index("except BaseException:")
    assert "raise" in source.split("except BaseException:")[1]


def test_every_exit_from_the_document_check_cleans_up_and_reads_back():
    """One exit point, because a check that gave up early must still discard,
    still read the record back and still remove its fixture -- and there are four
    places it can give up."""
    source = inspect.getsource(markup._document_mailing_after_seeding)
    returns = [line for line in source.splitlines() if line.strip().startswith("return ")]
    assert returns
    assert all("_document_mailing_leaving(" in line for line in returns)


@pytest.mark.parametrize("check", sorted(MEDIA_FLOWS))
def test_every_media_check_declares_itself_as_a_write(check):
    """All four build what they measure (#266), and ADR 0012 wants a check to
    say so: `read_only_first` orders on this flag, so one left marked read-only
    would run before the cheap ones and would misdescribe itself in the
    register."""
    assert markup.CHECKS[check]["writes"] is True


def test_the_todo_fixtures_are_scratch_records_and_not_the_onboarding_one():
    """#243's rule, and the reason the iframe check has the same one: #235's
    checks read the onboarding to-do's stored `src`, so a write there would be
    read as their result."""
    source = inspect.getsource(markup.seed_media_task)
    assert "scratch_task_name(run_id)" in source
    assert "onboarding_todo_id" not in source
    assert '"element_survived"' in source


def test_the_todo_fixtures_read_the_description_back():
    """`project.task.description` is `sanitize_tags=True`, and this driver has
    already been caught by that field once -- #237's check 2 seeded a full-HTML
    value into it and got back the bare `<img>`. The anchor's attributes are all
    whitelisted, so it is expected to survive; the read-back is what replaces
    "expected to"."""
    source = inspect.getsource(markup.seed_media_task)
    assert "read_field(side, \"project.task\"" in source
    assert '"element_survived": wanted in stored' in source


def test_the_image_todo_fixture_carries_no_data_original_src():
    """Rule 2's branch `return`s before the `src` comparison, so an image
    carrying that attribute would measure rule 2 on the screen whose whole point
    is rule 1 -- and the attribute would be root-relative here anyway, because a
    field value arrives over `call_kw` with its quotes escaped and the generic
    HTML location's bare `src="/` cannot claim a position inside `src=\\"/`.
    Rule 2 has a screen of its own for exactly that reason."""
    source = inspect.getsource(markup.seed_media_task)
    assert 'data-original-src="' not in source
    assert "FIXTURE_IMAGE_ALT" in source
    # And the one screen that does carry it is the one that needs it.
    assert 'data-original-src="' in markup.WEBSITE_FIXTURE_SECTION


def test_the_module_says_what_the_two_media_fixtures_create():
    """The docstring's `Writing:` paragraph is where a reader looks before
    running this against the host, so the two new fixtures belong in it."""
    said = " ".join(markup.__doc__.split())
    assert "website.page" in said
    assert "ir.attachment" in said
    assert "--cleanup" in said
    assert "media-document-mailing" in said


def test_the_image_fixture_is_a_real_png():
    """The dialog's domain is `['mimetype', 'in', IMAGE_MIMETYPES]` and
    `image_src` is only computed for a supported image mimetype, so a fixture
    that was not really a PNG would be listed by nothing and compared to
    nothing."""
    raw = base64.b64decode(markup.FIXTURE_PNG_BASE64)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in raw
    assert raw.endswith(b"IEND\xaeB\x60\x82")


def test_the_attachment_fixture_is_public_and_newest_rather_than_searched_for():
    """Two selector properties, both relied on and neither obvious.

    `public=True` is what lists it whatever record the dialog was opened from --
    the website editor's dialog is opened from an `ir.ui.view` and would not list
    the record-scoped attachment #243 used. And `order: 'id desc'` with a limit
    of 30 is why the newest attachment is the first tile: the preselection runs
    inside the first page's own loop, so a tile on page two would never be
    compared and the check would have to type a search."""
    source = inspect.getsource(markup.create_fixture_attachment)
    assert '"public": True' in source
    assert "id desc" in source
    assert '"image_src"' in source and '"checksum"' in source


def test_the_fixture_removal_says_what_went_rather_than_swallowing_it():
    """`website.page.unlink` may take the view with it, so unlinking the view
    afterwards raises on a record that is correctly gone. A silent `except` would
    read as "removed" for a fixture still on the host."""
    source = inspect.getsource(markup.remove_website_fixture_page)
    assert source.count("except Exception") == 2, (
        "the page/view unlink and the attachment unlink are guarded separately, "
        "so one failing does not hide the other's outcome")
    assert "removed[label] = False" in source
    assert 'removed["attachment"] = False' in source
    assert "return removed" in source


def test_both_media_dialogs_are_probed_for_the_rule():
    """Rule 2 is the single pattern the two dialogs spell identically, and the
    two media image checks open *different* ones -- the backend form opens
    `html_editor`'s, the website editor opens the legacy `web_editor` one. A
    probe that only read the current editor's method would report a rule that
    reached a dialog the check never drove. The #243 key names are kept so the
    two runs stay comparable."""
    assert "@html_editor/main/media/media_dialog/image_selector" in markup._RULE_PROBE
    assert "@web_editor/components/media_dialog/image_selector" in markup._RULE_PROBE
    assert '"rule_in_served_method"' in markup._RULE_PROBE
    assert '"legacy_"' in markup._RULE_PROBE


def test_the_document_operand_probe_takes_the_dialog_as_a_parameter():
    """Odoo ships the document comparison twice and the Static tier records both
    as measured-and-left-alone. The legacy reading is the one that belongs beside
    a tile the legacy dialog actually showed."""
    assert markup.CURRENT_DOCUMENT_SELECTOR.startswith("@html_editor/")
    assert markup.LEGACY_DOCUMENT_SELECTOR.startswith("@web_editor/")
    assert "spec.module" in markup._DOCUMENT_OPERAND_PROBE
    assert "spec.dialog" in markup._DOCUMENT_OPERAND_PROBE
    source = inspect.getsource(markup._document_mailing_after_seeding)
    assert "LEGACY_DOCUMENT_SELECTOR" in source


# --- #274: the last media check that did not build what it measures -----------
#
# `media-document-mailing` built its attachment and only *looked up* its
# mailing, so on a database with no draft mailing -- a fresh install, a
# catch-up database, the local add-on's own -- it returned `NOT-RUN` with
# nothing measured. #271's Live run hit exactly that on `catchup164b`, where
# `mass_mailing` had been installed minutes earlier, and had to seed a mailing
# by hand over `odoo shell`: the one thing that stopped that run being
# unattended.
#
# What this section pins is #266's lesson in both directions. A record the run
# **made** is deleted; a record it **borrowed** is restored and never deleted.
# A check that deletes what it did not create is how the next run ends up with
# nothing to measure, and a check that restores what it is about to delete
# reports a borrowed body that nobody borrowed.


class FakeRoot:
    """No unsaved-changes bar, and nothing to discard.

    The browser half has no static tests at all (the module says so); these
    tests are about the writes, and `_document_mailing_leaving` asks the page
    one question before it makes any.
    """

    def locator(self, selector):
        return self

    def count(self):
        return 0


class FakeSide:
    """The driver's RPC seam, with a toy database behind it.

    The seeding and cleanup split is a *sequence of writes*, and an assertion on
    the source would pin its spelling rather than its behaviour -- "`unlink` was
    never reached for a mailing this run did not create" is the property. Every
    step the seeder and the leaving function take goes through `side.rpc`, so
    this is their whole surface.
    """

    def __init__(self, mailings=None, create_state="draft", fail_attachment=False):
        self.mailings = {key: dict(value) for key, value in (mailings or {}).items()}
        self.attachments = {}
        self.models = {"mailing.list": 11}
        self.create_state = create_state
        self.fail_attachment = fail_attachment
        self.calls = []
        self.root = FakeRoot()
        self._next_id = 100

    def rpc(self, model, method, args, kwargs=None):
        kwargs = kwargs or {}
        self.calls.append((model, method, args, kwargs))
        return getattr(self, "_%s_%s" % (model.replace(".", "_"), method))(args, kwargs)

    def did(self, model, method):
        return [call for call in self.calls if call[0] == model and call[1] == method]

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def _mailing_mailing_search(self, args, kwargs):
        states = next(clause[2] for clause in args[0] if clause[0] == "state")
        found = [key for key, record in sorted(self.mailings.items())
                 if record.get("state") in states]
        return found[:kwargs.get("limit", len(found))]

    def _mailing_mailing_create(self, args, kwargs):
        record = {"body_arch": False, "body_html": False}
        record.update(args[0])
        # What the server made, which is not necessarily what was asked for.
        record["state"] = self.create_state
        key = self._new_id()
        self.mailings[key] = record
        return key

    def _mailing_mailing_read(self, args, kwargs):
        return [dict({"id": key}, **{field: self.mailings[key].get(field, False)
                                     for field in args[1]}) for key in args[0]]

    def _mailing_mailing_write(self, args, kwargs):
        for key in args[0]:
            self.mailings[key].update(args[1])
        return True

    def _mailing_mailing_unlink(self, args, kwargs):
        for key in args[0]:
            del self.mailings[key]
        return True

    def _ir_model_search(self, args, kwargs):
        wanted = next(clause[2] for clause in args[0] if clause[0] == "model")
        found = self.models.get(wanted)
        return [found] if found else []

    def _ir_attachment_create(self, args, kwargs):
        if self.fail_attachment:
            raise RuntimeError("the attachment could not be created")
        key = self._new_id()
        self.attachments[key] = dict(args[0])
        return key

    def _ir_attachment_read(self, args, kwargs):
        return [{"id": key, "checksum": "abc123",
                 "mimetype": self.attachments[key].get("mimetype"),
                 "image_src": False} for key in args[0]]

    def _ir_attachment_unlink(self, args, kwargs):
        for key in args[0]:
            del self.attachments[key]
        return True


RUN = "WOOW-MARKUP-20261003T123902Z"
BORROWED = "<div class=\"o_layout\"><p>a real campaign</p></div>"


def seed_document_mailing(side, mailing_id=None):
    return markup.seed_document_mailing_fixture(side, RUN, mailing_id)


def leave(side, fixture, **kwargs):
    return markup._document_mailing_leaving(
        side, fixture, fixture["extra"], "/screen",
        pictures=None, notes="", **kwargs)


def test_a_database_with_no_draft_mailing_gets_one_this_run_made():
    """#274's reading, and the check's own premise: the search that did not find
    a mailing is satisfied by what the seed leaves behind."""
    side = FakeSide()
    assert markup.editable_mailing_id(side) is None
    fixture = seed_document_mailing(side)
    assert fixture["created_mailing"] is not None
    mailing_id = fixture["mailing_id"]
    assert markup.editable_mailing_id(side) == mailing_id
    # Named after the run, the way `live-tier.md` asks of every writing step.
    assert side.mailings[mailing_id]["subject"] == markup.scratch_task_name(RUN)
    assert RUN in side.mailings[mailing_id]["subject"]


def test_the_mailing_this_run_made_is_recorded_beside_the_attachment():
    """`extra["fixture"]` is what a later reader consults to know what is on the
    host, and #271's hand-seeded mailing was in no record at all."""
    side = FakeSide()
    fixture = seed_document_mailing(side)
    recorded = fixture["extra"]["fixture"]
    assert recorded["mailing_id"] == fixture["mailing_id"]
    assert recorded["mailing_subject"] == markup.scratch_task_name(RUN)
    assert recorded["mailing_state"] in markup.EDITABLE_MAILING_STATES
    assert recorded["attachment_id"] == fixture["attachment"]["id"]
    assert fixture["extra"]["mailing_source"] == "created"


def test_a_mailing_this_run_made_is_deleted_and_not_restored():
    side = FakeSide()
    fixture = seed_document_mailing(side)
    outcome = leave(side, fixture, cleanup=True)
    assert outcome["extra"]["fixture_removed"] == {"attachment": True, "mailing": True}
    assert not side.mailings and not side.attachments
    # Restoring a row that is being deleted would report a borrowed body nobody
    # borrowed, which is the reading `body_restored` exists to give.
    assert "body_restored" not in outcome["extra"]


def test_a_borrowed_mailing_is_restored_and_never_deleted():
    """#266's own lesson: a check that deletes what it did not create is how the
    next run ends up with nothing to measure."""
    side = FakeSide(mailings={4: {"state": "draft", "subject": "Real campaign",
                                  "body_arch": BORROWED, "body_html": BORROWED}})
    fixture = seed_document_mailing(side)
    assert fixture["created_mailing"] is None
    assert fixture["mailing_id"] == 4
    assert fixture["extra"]["mailing_source"] == "found"
    # The fixture block is what this run made, and it made no mailing here.
    assert "mailing_id" not in fixture["extra"]["fixture"]
    assert side.mailings[4]["body_arch"] != BORROWED, "the seed overwrote the body"

    outcome = leave(side, fixture, cleanup=True)
    assert side.mailings[4]["body_arch"] == BORROWED
    assert side.mailings[4]["body_html"] == BORROWED
    assert outcome["extra"]["body_restored"] is True
    assert outcome["extra"]["fixture_removed"] == {"attachment": True}
    assert not side.did("mailing.mailing", "unlink")


def test_mailing_id_still_means_reuse_this_one_and_nothing_else():
    """`--mailing-id`'s meaning is unchanged by #274: do not look, do not
    create, do not delete -- and do not second-guess the state the operator
    named, which is why this one is `done`."""
    side = FakeSide(mailings={9: {"state": "done", "subject": "Sent",
                                  "body_arch": BORROWED, "body_html": BORROWED}})
    fixture = seed_document_mailing(side, mailing_id=9)
    assert fixture["mailing_id"] == 9 and fixture["created_mailing"] is None
    assert fixture["extra"]["mailing_source"] == "given"
    assert not side.did("mailing.mailing", "create")
    assert not side.did("mailing.mailing", "search")

    outcome = leave(side, fixture, cleanup=True)
    assert 9 in side.mailings
    assert side.mailings[9]["body_arch"] == BORROWED
    assert outcome["extra"]["fixture_removed"] == {"attachment": True}


def test_a_mailing_that_came_back_uneditable_is_removed_rather_than_measured():
    """The row the seed makes has to satisfy the predicate the search applies:
    the designer's body field is `readonly="state in ('sending','done')"`, so a
    check driven against one of those would measure a readonly screen and read
    like a fixture that did not survive its field."""
    side = FakeSide(create_state="sending")
    with pytest.raises(RuntimeError, match="state"):
        seed_document_mailing(side)
    assert not side.mailings, "the row it made is still on the host"
    assert not side.attachments


def test_a_seed_that_fails_after_making_the_mailing_removes_it():
    """`run_check` discards a handler's return value when it raises, so a row
    left behind here would be on the host with nothing in the evidence naming
    it -- the trap #266's review caught twice."""
    side = FakeSide(fail_attachment=True)
    with pytest.raises(RuntimeError):
        seed_document_mailing(side)
    assert not side.mailings


def test_the_states_the_seed_must_satisfy_are_the_search_s_own():
    """One constant, so the row the seed makes cannot drift away from the row
    the lookup would have accepted."""
    assert markup.EDITABLE_MAILING_STATES == ("draft", "in_queue")
    assert "EDITABLE_MAILING_STATES" in inspect.getsource(markup.editable_mailing_id)
    assert "EDITABLE_MAILING_STATES" in inspect.getsource(markup.create_fixture_mailing)


def test_the_seeded_body_is_what_keeps_the_theme_chooser_off_the_screen():
    """The one thing that could stand between a brand-new mailing and the
    editable, and the reason it does not. The chooser is appended only when
    `value === "" || value === blankEditable`
    (`mass_mailing_html_field.js:520-534`), and the value it reads is the
    `body_arch` the seeder has already written -- so a mailing this run created
    reaches the same screen as one it borrowed. That holds only while the seeded
    body is a non-empty `.o_layout`, which is this half of the premise."""
    body = markup.mailing_document_body_value(RUN, ATTACHMENT)
    assert body.startswith('<div class="o_layout">')
    assert markup.document_link_markup(ATTACHMENT) in body


@pytest.mark.parametrize("check", sorted(MEDIA_FLOWS))
def test_no_media_check_gives_up_because_the_database_had_no_record(check):
    """#266 moved three of the four off records they did not create, #274 the
    fourth. All four now build their screen, so none of them can report "there
    was nothing here to measure" on a database that is merely fresh."""
    source = "".join(inspect.getsource(flow) for flow in MEDIA_FLOWS[check])
    assert "on this database" not in source
