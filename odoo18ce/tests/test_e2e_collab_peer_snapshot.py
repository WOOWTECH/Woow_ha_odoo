#!/usr/bin/env python3
"""Static-tier tests for the pure parts of the peer-snapshot run (#234).

Nothing here opens a browser or a websocket, and nothing reads credentials.
What it does cover is everything the run decides *about* a value: the prefix
shape it looks for, the redaction that keeps a Supervisor token out of the
evidence, the verdict #234's criteria escalate on, and the report that says so.

Since #263 it also covers what the run decides about its own *steps*, because
that is where two false readings came from: `probe` claimed to write nothing
while writing the field on every run, and its marker was a constant, which made
`delivered` unfalsifiable once the field had ever held it. So the marker helper,
the wait's refusal of a pre-existing match and the probe's own verdict are driven
here, the two commands are pinned to the shape that cannot reproduce either
defect, and the three documents that state the behaviour are pinned to the code.

#243 took the measurement, so the browser steps are no longer unrun -- but they
are still not driven from here, and the redaction is still the thing that matters
most: the record the run writes exists to say *whose* prefix reached the field,
and getting that wrong means either an unreadable record or a token in the
repository.
"""
import inspect
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from e2e_collab_peer_snapshot_live import (
    CLEAN,
    EVIDENCE_SCHEMA,
    FOREIGN_PREFIX_STORED,
    INGRESS_PREFIX_SHAPE,
    NOT_RUN,
    OWN_PREFIX_STORED,
    PAIRS,
    PROBE_RUN_PREFIX,
    UNKNOWN_PREFIX_STORED,
    await_marker,
    classify,
    discard_form,
    do_probe,
    do_run,
    evidence_record,
    ingress_prefixes,
    marker,
    mint_run_id,
    probe_verdict,
    redact,
    discard_quietly,
    report,
    stage,
    stored_prefix_labels,
    transport_note,
    wait_for_transport,
)

TEMPLATE = Path(__file__).resolve().parents[1] / "rootfs/etc/nginx/nginx.conf.template"
PARITY_PLAN = Path(__file__).resolve().parents[2] / "docs/testing/INGRESS_VS_PUBLIC_PARITY.md"
LIVE_TIER_DOC = Path(__file__).resolve().parents[2] / "docs/agents/live-tier.md"

# Documentation-only tokens of the length Supervisor's `secrets.token_urlsafe`
# default produces (43 characters of the class the gateway accepts).
TOKEN_A = "Hs3-kQ9fR2tV7wXz_bC4dE6gJ8mN1pS5uY0aL2oZ4qT"
TOKEN_B = "Zq7_mB2xT5yD8hJ1kL4nP6rS9vW0cF3gN5tQ8uX1zA6"
TOKEN_C = "Nf1-tR8wY2bK5mD9pL3sV6xA0cJ7hQ4uZ8eG1nT5oW2"
PREFIX_A = "/api/hassio_ingress/" + TOKEN_A
PREFIX_B = "/api/hassio_ingress/" + TOKEN_B
PREFIX_C = "/api/hassio_ingress/" + TOKEN_C
PICTURE = "/project_todo/static/img/todo_access.png"
LABELS = {PREFIX_A: "A", PREFIX_B: "B"}


class PrefixShapeTests(unittest.TestCase):
    def test_the_shape_is_the_gateways_own(self):
        """Derived from the template, so the run cannot measure a shape the
        add-on does not serve. The gateway's map is the authority (ADR 0004);
        the markup strip of #234 reads it too, and
        `test_ingress_peer_snapshot_prefix.py` holds that pair together."""
        gateway = re.search(
            r'"~\^(/api/hassio_ingress/\[[^\]]+\]\{\d+,\d+\})\$"\s+\$http_x_ingress_path;',
            TEMPLATE.read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(gateway, "the $safe_ingress_path map must state the prefix shape")
        self.assertEqual(
            INGRESS_PREFIX_SHAPE.pattern,
            gateway.group(1) + "(?![A-Za-z0-9_-])",
            "the run must look for the prefix shape the gateway validates, plus the "
            "lookahead that refuses a token longer than it accepts",
        )

    def test_every_distinct_prefix_in_order(self):
        value = '<img src="%s%s"/><img src="%s%s"/><a href="%s/web">x</a>' % (
            PREFIX_B, PICTURE, PREFIX_A, PICTURE, PREFIX_B)
        self.assertEqual(ingress_prefixes(value), [PREFIX_B, PREFIX_A])

    def test_what_is_not_a_prefix(self):
        for value in (
            "",
            '<img src="%s"/>' % PICTURE,
            # Short of the bound, over it, and a character the class refuses.
            "/api/hassio_ingress/" + "x" * 15,
            "/api/hassio_ingress/" + "x" * 129,
            "/api/hassio_ingress/" + "x" * 8 + "." + "x" * 8,
            "/api/hassio_ingres/" + TOKEN_A,
            "<p>served under /api/hassio_ingress/ and nowhere else</p>",
        ):
            self.assertEqual(ingress_prefixes(value), [], value)

    def test_a_token_at_the_bound_is_taken_whole(self):
        """The same rule the strip has: a token over the bound is left alone
        rather than matched to the bound, so a report never shows half a
        token joined to the path after it."""
        self.assertEqual(ingress_prefixes("/api/hassio_ingress/" + "x" * 128),
                         ["/api/hassio_ingress/" + "x" * 128])
        self.assertEqual(ingress_prefixes("/api/hassio_ingress/" + "x" * 129), [])


class RedactionTests(unittest.TestCase):
    def test_a_prefix_becomes_the_label_of_the_session_it_belongs_to(self):
        value = '<img src="%s%s"/>' % (PREFIX_A, PICTURE)
        self.assertEqual(
            redact(value, LABELS),
            '<img src="/api/hassio_ingress/<ingress:A>%s"/>' % PICTURE,
        )

    def test_a_prefix_no_session_claims_is_still_never_printed(self):
        value = '<img src="%s%s"/>' % (PREFIX_C, PICTURE)
        redacted = redact(value, LABELS)
        self.assertNotIn(TOKEN_C, redacted)
        self.assertEqual(redacted,
                         '<img src="/api/hassio_ingress/<ingress:unknown>%s"/>' % PICTURE)

    def test_no_token_survives_anywhere_in_a_record(self):
        record = evidence_record(
            run_id="WOOW-PEER-20261001T000000Z", database="odoo_parity", target="local",
            pair="ingress-ingress", task_id=5,
            prefixes={"A": PREFIX_A, "B": PREFIX_B},
            transport={"delivered": True},
            stored='<img src="%s%s"/><img src="%s%s"/>' % (PREFIX_A, PICTURE, PREFIX_C, PICTURE),
            labels=LABELS, saver="B",
        )
        text = json.dumps(record)
        for token in (TOKEN_A, TOKEN_B, TOKEN_C):
            self.assertNotIn(token, text, "a Supervisor token must never reach the evidence")

    def test_structures_are_walked_and_other_values_untouched(self):
        self.assertEqual(redact({"a": [PREFIX_A], "b": 7, "c": None}, LABELS),
                         {"a": ["/api/hassio_ingress/<ingress:A>"], "b": 7, "c": None})


class VerdictTests(unittest.TestCase):
    def test_a_clean_value(self):
        self.assertEqual(classify('<img src="%s"/>' % PICTURE, LABELS, "B"), (CLEAN, []))

    def test_another_sessions_prefix_is_the_hole_issue_234_is_about(self):
        verdict, present = classify('<img src="%s%s"/>' % (PREFIX_A, PICTURE), LABELS, "B")
        self.assertEqual((verdict, present), (FOREIGN_PREFIX_STORED, ["A"]))

    def test_the_savers_own_prefix_means_the_strip_did_not_run(self):
        verdict, present = classify('<img src="%s%s"/>' % (PREFIX_B, PICTURE), LABELS, "B")
        self.assertEqual((verdict, present), (OWN_PREFIX_STORED, ["B"]))

    def test_a_prefix_nobody_claims_is_read_like_a_foreign_one(self):
        verdict, present = classify('<img src="%s%s"/>' % (PREFIX_C, PICTURE), LABELS, "B")
        self.assertEqual((verdict, present), (UNKNOWN_PREFIX_STORED, ["unknown"]))

    def test_both_prefixes_in_one_value_is_foreign(self):
        """What the receiving peer's editable holds: `setAttribute` hands a
        foreign prefix to the shim's `path()`, which prefixes it again."""
        verdict, present = classify(
            '<img src="%s%s%s"/>' % (PREFIX_B, PREFIX_A, PICTURE), LABELS, "B")
        self.assertEqual(verdict, FOREIGN_PREFIX_STORED)
        self.assertEqual(sorted(present), ["A", "B"])


class RecordTests(unittest.TestCase):
    def kwargs(self, **overrides):
        base = dict(
            run_id="WOOW-PEER-20261001T000000Z", database="odoo_parity", target="local",
            pair="ingress-ingress", task_id=5,
            prefixes={"A": PREFIX_A, "B": PREFIX_A},
            transport={"delivered": True}, stored='<img src="%s"/>' % PICTURE,
            labels={PREFIX_A: "A"}, saver="B",
        )
        base.update(overrides)
        return base

    def test_equal_prefixes_are_recorded_as_the_expected_reading(self):
        """Two Ingress sessions on one add-on share the prefix: the token in
        the path is the add-on's, not the session's. The record says it rather
        than leaving a reader to compare two redacted labels."""
        record = evidence_record(**self.kwargs())
        self.assertIs(record["prefixes_equal"], True)
        self.assertEqual(record["verdict"], CLEAN)

    def test_different_prefixes_are_recorded_too(self):
        record = evidence_record(**self.kwargs(
            prefixes={"A": PREFIX_A, "B": PREFIX_B}, labels=LABELS))
        self.assertIs(record["prefixes_equal"], False)

    def test_a_public_peer_has_no_prefix_of_its_own(self):
        record = evidence_record(**self.kwargs(
            pair="ingress-public", prefixes={"A": PREFIX_A, "B": None}))
        self.assertIsNone(record["prefixes"]["B"])
        self.assertIsNone(record["prefixes_equal"])

    def test_no_value_read_back_is_not_run_and_not_clean(self):
        record = evidence_record(**self.kwargs(stored=None))
        self.assertEqual(record["verdict"], NOT_RUN)
        self.assertIsNone(record["stored"])

    def test_the_record_names_the_field_the_issue_is_about(self):
        record = evidence_record(**self.kwargs())
        self.assertEqual(record["field"], "project.task.description")
        self.assertEqual(record["issue"], 234)
        self.assertIn(record["pair"], PAIRS)

    def test_the_schema_is_the_one_the_parity_plan_registers(self):
        """Section 12 of the plan is where evidence schemas are declared, and
        this one is not `odoo-parity-evidence/v1` for reasons recorded there.
        A record whose schema no document names is a record nobody reading an
        evidence directory can place."""
        record = evidence_record(**self.kwargs())
        self.assertEqual(record["schema"], EVIDENCE_SCHEMA)
        plan = PARITY_PLAN.read_text(encoding="utf-8")
        section = plan[plan.index("## 12. "):]
        self.assertIn(EVIDENCE_SCHEMA, section,
                      "the parity plan's section 12 must register this schema")
        self.assertIn("conservation", section,
                      "and say that it does not feed the conservation check")


class ReportTests(unittest.TestCase):
    def record(self, verdict, **overrides):
        base = {"verdict": verdict, "pair": "ingress-ingress", "transport": {"delivered": True}}
        base.update(overrides)
        return base

    def test_a_clean_run_does_not_escalate(self):
        result = report([self.record(CLEAN), self.record(CLEAN, pair="ingress-public")])
        self.assertEqual(result["verdicts"], {CLEAN: 2})
        self.assertIs(result["escalate_issue_234_to_blocker"], False)
        self.assertEqual(result["pairs"], ["ingress-ingress", "ingress-public"])

    def test_a_stored_foreign_token_escalates_issue_234(self):
        """#234's own acceptance criteria: a confirmed stored foreign token
        makes it `severity: blocker` by parity plan section 1.3."""
        result = report([self.record(CLEAN), self.record(FOREIGN_PREFIX_STORED)])
        self.assertIs(result["escalate_issue_234_to_blocker"], True)

    def test_an_unaccounted_prefix_escalates_as_well(self):
        result = report([self.record(UNKNOWN_PREFIX_STORED)])
        self.assertIs(result["escalate_issue_234_to_blocker"], True)

    def test_a_run_whose_transport_never_delivered_is_visible(self):
        result = report([self.record(CLEAN, transport={"delivered": False})])
        self.assertEqual(result["transport_delivered"], [False])


class MarkerTests(unittest.TestCase):
    """#263: a marker has to be unique to the run, and one helper has to mint it."""

    def test_both_sessions_markers_come_from_the_one_helper(self):
        self.assertEqual(marker("WOOW-PEER-20261002T015318Z", "A"),
                         "WOOW-PEER-20261002T015318Z-A")
        self.assertEqual(marker("WOOW-PEER-20261002T015318Z", "B"),
                         "WOOW-PEER-20261002T015318Z-B")

    def test_neither_command_stages_a_constant_marker(self):
        """The defect in one assertion. `probe` typed the literal
        `WOOW-PEER-PROBE`; because it also *wrote* the field, the next probe
        found that string in the receiving editable on its first poll and
        reported a delivery that never happened. A marker built from the run id
        cannot be satisfied by a value a previous run stored."""
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            self.assertIn("marker(run_id", source,
                          "%s must build its marker from the run id" % command.__name__)
            self.assertNotIn(PROBE_RUN_PREFIX, source,
                             "%s must not type a constant marker" % command.__name__)

    def test_a_minted_probe_run_id_is_the_shape_run_takes(self):
        minted = mint_run_id(datetime(2026, 10, 2, 1, 53, 18, tzinfo=timezone.utc))
        self.assertEqual(minted, "WOOW-PEER-PROBE-20261002T015318Z")
        self.assertTrue(minted.startswith(PROBE_RUN_PREFIX))

    def test_a_minted_run_id_is_different_for_a_different_run(self):
        """Uniqueness is the whole point of it, so it is checked and not assumed."""
        first = datetime(2026, 10, 2, 1, 53, 18, tzinfo=timezone.utc)
        self.assertNotEqual(mint_run_id(first), mint_run_id(first + timedelta(seconds=1)))

    def test_a_minted_run_id_is_utc_whatever_it_was_given(self):
        """`-<UTC timestamp>` is what the shape claims, and a naive local clock
        reaching this would make two runs an hour apart collide."""
        utc = datetime(2026, 10, 2, 1, 53, 18, tzinfo=timezone.utc)
        self.assertEqual(mint_run_id(utc.astimezone(timezone(timedelta(hours=8)))),
                         mint_run_id(utc))


class TransportWaitTests(unittest.TestCase):
    """#263: "it was already there" and "it arrived" are different readings."""

    def poll(self, *reads):
        """A reader that answers each call in turn, and a sleep that counts."""
        values = list(reads)
        slept = []
        return (lambda: values.pop(0) if values else ""), slept.append, slept

    def test_a_marker_already_in_the_baseline_is_not_a_delivery(self):
        read, sleep, slept = self.poll("the marker M is right here")
        result = await_marker(read, "M", baseline="a value holding M already",
                              sleep=sleep, seconds=30)
        self.assertIs(result["delivered"], False)
        self.assertIs(result["marker_pre_existing"], True)
        self.assertEqual(result["waited_seconds"], 0.0)
        self.assertEqual(slept, [], "a pre-existing marker is refused without waiting")

    def test_a_marker_that_arrives_is_a_delivery_with_the_seconds_it_took(self):
        read, sleep, slept = self.poll("nothing", "nothing", "here comes M")
        result = await_marker(read, "M", baseline="clean", sleep=sleep, seconds=30)
        self.assertIs(result["delivered"], True)
        self.assertIs(result["marker_pre_existing"], False)
        self.assertEqual(result["waited_seconds"], 1.0)
        self.assertEqual(slept, [500, 500])

    def test_an_arrival_on_the_first_read_is_zero_seconds_and_still_a_delivery(self):
        """The shape to distrust is not the shape to refuse. The receiving
        session joins *after* the sender typed, so the snapshot it is handed can
        legitimately carry the marker on the first poll -- what made #243's
        reading false was the baseline, not the clock. Both are recorded."""
        read, sleep, _ = self.poll("M arrived with the snapshot")
        result = await_marker(read, "M", baseline="clean", sleep=sleep, seconds=30)
        self.assertEqual((result["delivered"], result["waited_seconds"]), (True, 0.0))
        self.assertIs(result["marker_pre_existing"], False)

    def test_nothing_arriving_is_a_finding_and_not_a_failure(self):
        read, sleep, slept = self.poll()
        result = await_marker(read, "M", baseline="clean", sleep=sleep, seconds=2)
        self.assertIs(result["delivered"], False)
        self.assertIs(result["marker_pre_existing"], False)
        self.assertEqual(result["waited_seconds"], 2.0)
        self.assertIn("never arrived", result["detail"])
        self.assertEqual(len(slept), 4, "two polls a second for the whole wait")

    def test_an_empty_baseline_is_not_a_match(self):
        """A session whose editable read empty must not make every marker
        pre-existing, and `None` must not raise."""
        for baseline in (None, ""):
            read, sleep, _ = self.poll("M is here")
            result = await_marker(read, "M", baseline=baseline, sleep=sleep, seconds=1)
            self.assertIs(result["delivered"], True, repr(baseline))

    def test_the_guard_cannot_be_skipped_by_a_caller(self):
        """`baseline` is keyword-only with no default on both the pure loop and
        the browser wrapper, so a future caller cannot quietly drop the thing
        that distinguishes the two readings."""
        for function in (await_marker, wait_for_transport):
            parameter = inspect.signature(function).parameters["baseline"]
            self.assertIs(parameter.default, inspect.Parameter.empty, function.__name__)
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY, function.__name__)

    def test_the_baseline_is_read_before_the_sender_types(self):
        """Which is the only order that makes it a baseline. Read from A, because
        B has not joined yet and both sessions load the same stored value."""
        source = inspect.getsource(stage)
        self.assertLess(source.index("baseline = editable_html(first)"),
                        source.index("type_marker(first"),
                        "the baseline must be read before anything is typed")
        self.assertIn("baseline=baseline", source)


class TransportNoteTests(unittest.TestCase):
    """A record has to say *which* way its transport failed, not just that it did."""

    def test_a_delivered_transport_needs_no_note(self):
        self.assertEqual(transport_note({"delivered": True, "waited_seconds": 0.0}), "")

    def test_a_marker_that_never_arrived_says_so(self):
        note = transport_note(await_marker(lambda: "", "M", baseline="clean",
                                           sleep=lambda ms: None, seconds=1))
        self.assertIn("never arrived", note)
        self.assertIn("not evidence about the peer transport", note)

    def test_a_pre_existing_marker_is_not_described_as_one_that_never_arrived(self):
        """The two are different findings, and a pre-existing marker says the run
        id collided -- which makes the whole record suspect, not only its
        transport half. One fixed sentence for both would have been a false
        account of this case."""
        note = transport_note(await_marker(lambda: "M", "M", baseline="M was here",
                                           sleep=lambda ms: None, seconds=1))
        self.assertIn("already in the editable", note)
        self.assertNotIn("never arrived", note)

    def test_a_transport_with_no_detail_still_reads_as_a_sentence(self):
        self.assertEqual(transport_note({"delivered": False}),
                         "the marker did not arrive -- so the stored value is not "
                         "evidence about the peer transport")


class StoredPrefixLabelTests(unittest.TestCase):
    """A reading of which prefixes are in a value, separate from any verdict."""

    def test_the_labels_in_order(self):
        value = '<img src="%s%s"/><img src="%s%s"/>' % (PREFIX_B, PICTURE, PREFIX_A, PICTURE)
        self.assertEqual(stored_prefix_labels(value, LABELS), ["B", "A"])

    def test_a_clean_value_has_none(self):
        self.assertEqual(stored_prefix_labels('<img src="%s"/>' % PICTURE, LABELS), [])

    def test_an_unclaimed_prefix_is_unknown(self):
        self.assertEqual(stored_prefix_labels('<img src="%s"/>' % PREFIX_C, LABELS),
                         ["unknown"])

    def test_the_ingress_ingress_pair_collapses_to_one_label(self):
        """Which is why `probe` reports labels and no verdict. Both sessions are
        served the add-on's one `ingress_token`, so `labels_for` writes one entry
        and the later session wins it. Asking `classify` for a verdict with
        `saver="A"` then calls every prefix foreign -- the verdict the parity plan
        escalates #234 to `blocker` on -- for a value nobody saved."""
        collapsed = {PREFIX_A: "B"}  # what labels_for produces when A and B match
        value = '<img src="%s%s"/>' % (PREFIX_A, PICTURE)
        self.assertEqual(stored_prefix_labels(value, collapsed), ["B"])
        self.assertEqual(classify(value, collapsed, "A")[0], FOREIGN_PREFIX_STORED)
        self.assertEqual(classify(value, collapsed, "B")[0], OWN_PREFIX_STORED)

    def test_probe_reports_the_labels_and_asks_for_no_verdict(self):
        source = inspect.getsource(do_probe)
        self.assertIn("stored_prefix_labels(stored, labels)", source)
        self.assertNotIn("classify(", source,
                         "a saver-relative verdict has no saver on a step that saves nothing")


class ProbeVerdictTests(unittest.TestCase):
    """#263: `probe`'s claim to write nothing is measured, not asserted."""

    def verdict(self, **overrides):
        base = dict(transport={"delivered": True},
                    stored="<p>the onboarding to-do, untouched</p>",
                    run_id="WOOW-PEER-PROBE-20261002T015318Z",
                    discarded={"A": {"dirty": True, "discarded": True},
                               "B": {"dirty": False, "discarded": False}})
        base.update(overrides)
        return probe_verdict(**base)

    def test_a_probe_that_left_the_field_alone_passes(self):
        verdict = self.verdict()
        self.assertIs(verdict["wrote_nothing"], True)
        self.assertEqual(verdict["forms_left_dirty"], [])
        self.assertEqual(verdict["detail"], "")
        self.assertEqual(verdict["exit_code"], 0)

    def test_a_probe_whose_run_id_is_in_the_field_wrote_and_fails(self):
        run_id = "WOOW-PEER-PROBE-20261002T015318Z"
        verdict = self.verdict(stored="<p>to-do %s-A</p>" % run_id)
        self.assertIs(verdict["wrote_nothing"], False)
        self.assertIn("wrote the field", verdict["detail"])
        self.assertEqual(verdict["exit_code"], 1)

    def test_an_earlier_runs_marker_is_not_this_probes_write(self):
        """The field may still hold what the constant-marker probes left on a
        host nobody has cleaned. That is a pre-existing value, and reporting it
        as this run's write would make the check cry wolf forever."""
        verdict = self.verdict(stored="<p>to-do WOOW-PEER-PROBE WOOW-PEER-PROBE</p>")
        self.assertIs(verdict["wrote_nothing"], True)

    def test_a_probe_that_wrote_nothing_but_never_delivered_still_fails(self):
        """Both claims gate the exit code: a probe is also how the transport is
        attributed, and #243's run is the reason that reading is worth a code."""
        verdict = self.verdict(transport={"delivered": False})
        self.assertIs(verdict["wrote_nothing"], True)
        self.assertEqual(verdict["exit_code"], 1)

    def test_a_missing_delivered_is_not_a_pass(self):
        self.assertEqual(self.verdict(transport={})["exit_code"], 1)

    def test_a_form_left_dirty_fails_even_on_a_clean_read_back(self):
        """The read-back only sees writes that already happened. A session still
        holding unsaved content gets written afterwards -- by the unload or by the
        ungated `visibilitychange` save -- so a clean field here means "not yet".
        Reporting `wrote_nothing` and exiting 0 on that is the one outcome #263
        must not allow."""
        verdict = self.verdict(discarded={"A": {"dirty": True, "discarded": False},
                                          "B": {"dirty": True, "discarded": True}})
        self.assertIs(verdict["wrote_nothing"], True)
        self.assertEqual(verdict["forms_left_dirty"], ["A"])
        self.assertIn("not yet", verdict["detail"])
        self.assertEqual(verdict["exit_code"], 1)

    def test_a_form_that_was_never_dirty_is_not_a_form_left_dirty(self):
        """`discarded: False` on a clean form is the normal reading, not a fault."""
        verdict = self.verdict(discarded={"A": {"dirty": False, "discarded": False},
                                          "B": {"dirty": False, "discarded": False}})
        self.assertEqual(verdict["forms_left_dirty"], [])
        self.assertEqual(verdict["exit_code"], 0)

    def test_a_discard_that_raised_counts_as_left_dirty(self):
        verdict = self.verdict(discarded={"A": {"dirty": True, "discarded": False,
                                                "error": "TimeoutError"}})
        self.assertEqual(verdict["forms_left_dirty"], ["A"])
        self.assertEqual(verdict["exit_code"], 1)

    def test_an_actual_write_is_reported_over_a_dirty_form(self):
        """Both are wrong, and the one that already happened is the one to act on."""
        run_id = "WOOW-PEER-PROBE-20261002T015318Z"
        verdict = self.verdict(stored="%s-A" % run_id,
                               discarded={"A": {"dirty": True, "discarded": False}})
        self.assertIn("wrote the field", verdict["detail"])


class ProbeWritesNothingTests(unittest.TestCase):
    """#263: pinned at the shape, because the behaviour needs a host to see.

    These are source pins and they are deliberate. What went wrong was never a
    value a function returned -- it was a step the command did and a step it did
    not do, and the only tier that can watch the browser do it is the one that
    needs the test host. So the shape is held here: the discard happens, the
    read-back happens, and the navigation that did the writing is gone.
    """

    def test_probe_discards_both_sessions_forms(self):
        source = inspect.getsource(do_probe)
        self.assertIn("discard_quietly(side)", source)
        self.assertIn('("A", first), ("B", second)', source,
                      "both sessions' forms are dirty: A typed, and B may have received")

    def test_probe_no_longer_navigates_away_from_a_dirty_form(self):
        """The regression pin. `side.goto("/odoo")` in the old `finally` is what
        persisted the editor's content, on a step whose comment said that only a
        save writes the field."""
        source = inspect.getsource(do_probe)
        self.assertNotIn('goto("/odoo")', source)

    def test_probe_reads_the_field_back_and_reports_what_it_found(self):
        source = inspect.getsource(do_probe)
        self.assertIn("read_description(", source)
        self.assertIn("probe_verdict(", source)
        self.assertIn('"wrote_nothing"', source,
                      "the output must carry the claim, so the evidence can be read for it")
        # The exit code is the verdict's, wherever the statement sits. It is read
        # one line and returned the next since #264, outside the ambient
        # accounting: a `return` from inside it leaves the body exception-free, so
        # a figure that could not be written would be raised as the run's only
        # failure and `main`'s catch-all would turn this measured non-zero into a
        # harness error.
        self.assertIn('verdict["exit_code"]', source)
        self.assertIn("return exit_code", source)

    def test_probe_reads_the_receiving_editable_before_it_discards(self):
        """A discard reloads the record, so the delivered content is gone after
        it -- and that reading is the only thing in the report that says what the
        transport did."""
        source = inspect.getsource(do_probe)
        self.assertLess(source.index("second_editable = "), source.index("discard_quietly"))

    def test_run_discards_the_sending_sessions_leftover(self):
        """`run` is documented to store what B saved. A's form is still dirty
        with A's own marker when B is done, and leaving it dirty writes it on the
        way out -- the same defect, on the command that is allowed to write."""
        source = inspect.getsource(do_run)
        self.assertIn("discard_quietly(first)", source)
        self.assertLess(source.index("save_form(second)"),
                        source.index("discard_quietly(first)"),
                        "A is discarded after B's save, or B would never see A's marker")

    def test_run_has_its_record_on_disk_before_it_cleans_up(self):
        """Cleanup must never be what loses a measurement. By the time A is
        discarded the run has already cost a deploy, a host and a 30-second wait,
        and `discard_form` can raise -- the `wait_for` times out whenever the form
        will not go clean, which an invalid record guarantees. So the record is
        appended and printed first."""
        source = inspect.getsource(do_run)
        self.assertLess(source.index("handle.write("), source.index("discard_quietly(first)"))
        self.assertLess(source.index("print(json.dumps(record"),
                        source.index("discard_quietly(first)"))

    def test_both_commands_discard_through_the_wrapper_that_cannot_throw(self):
        """One session's failed discard must not stop the other's, nor stop the
        report: on that path `probe` would read the field back on no run at all,
        while its own docstring promises every run."""
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            self.assertIn("discard_quietly(", source, command.__name__)
            self.assertNotIn("discard_form(", source,
                             "%s must go through the wrapper" % command.__name__)

    def test_a_failed_discard_is_a_reading_and_not_an_exception(self):
        class Unusable:
            @property
            def root(self):
                raise RuntimeError("the frame went away")

        outcome = discard_quietly(Unusable())
        self.assertEqual(outcome["discarded"], False)
        self.assertEqual(outcome["error"], "RuntimeError")
        self.assertIs(outcome["dirty"], True,
                      "unknown is reported as dirty, because the verdict must fail closed")

    def test_the_discard_button_is_matched_on_visibility_not_on_dom_order(self):
        """`.first` takes the first match whatever its state, so one hidden
        earlier indicator -- a dialog's, a sub-form's -- would make the check
        decide the form has no discard button and skip the real one. This
        repository's idiom for the same button is `>> visible=true`."""
        source = inspect.getsource(discard_form)
        self.assertIn('DISCARD_BUTTON + " >> visible=true"', source)

    def test_a_discard_is_only_clicked_on_a_form_that_shows_the_button(self):
        """The button is in the DOM on a clean form too, behind
        `o_form_status_indicator_buttons.invisible`. Playwright's `click()` waits
        for visibility, so a clean form would burn the whole timeout -- #238's
        run lost a measurement to exactly that on the save button."""
        source = inspect.getsource(discard_form)
        self.assertIn("is_visible()", source)
        self.assertIn("dirty", source, "and it reports whether there was anything to discard")

    def test_a_discard_is_waited_on_rather_than_clicked_and_left(self):
        """`FormController.discard()` is asynchronous and `click()` returns well
        before it resolves. Anything that navigates in that window leaves the
        field still dirty, and the form's `beforeunload` save -- a `sendBeacon`
        nothing can intercept or cancel -- writes it anyway. The wait on the
        indicator going clean is what closes that window."""
        source = inspect.getsource(discard_form)
        self.assertIn('wait_for(state="hidden"', source)
        self.assertLess(source.index("button.click()"),
                        source.index('wait_for(state="hidden"'))


class BehaviourIsWrittenDownTests(unittest.TestCase):
    """#263: three documents state what `probe` does, and all three were wrong.

    The docstring, `docs/agents/live-tier.md` and the parity plan all said the
    step wrote nothing while it wrote on every run. A reader trusted them and ran
    it on a host. So each is pinned to the code here -- not the prose, but the
    claim that misled: *how* nothing is written, and what a `delivered` of 0.0
    seconds is worth.
    """

    def test_the_module_says_discarding_is_what_makes_probe_safe(self):
        import e2e_collab_peer_snapshot_live as module

        docstring = module.__doc__
        self.assertIn("Discard", docstring,
                      "the module must say *how* `probe` writes nothing")
        self.assertIn("#263", docstring)
        self.assertIn("wrote_nothing", docstring,
                      "and that the claim is measured and reported")
        self.assertIn("Discard", inspect.getdoc(module.do_probe),
                      "and so must the command's own docstring")

    def test_the_module_records_the_write_path_a_discard_cannot_close(self):
        """Odoo also saves a form on `visibilitychange`, ungated on dirtiness, and
        the sending session is necessarily dirty while the receiving one opens.
        That cannot be designed away here, so it is written down -- and the
        read-back, not the discard, is what the module offers as the guarantee. A
        future editor tidying the docstring must not quietly drop it."""
        import e2e_collab_peer_snapshot_live as module

        self.assertIn("visibilitychange", module.__doc__)
        self.assertIn("read-back is the guarantee", module.__doc__)
        self.assertIn("visibilitychange", LIVE_TIER_DOC.read_text(encoding="utf-8"))

    def test_the_live_tier_doc_says_how_probe_writes_nothing(self):
        """It is the file an agent reads before the first command, and the one
        whose "writes nothing" a reader acted on."""
        doc = LIVE_TIER_DOC.read_text(encoding="utf-8")
        self.assertIn("e2e_collab_peer_snapshot_live.py", doc)
        self.assertIn("Discard", doc,
                      "the Live-tier doc must say that `probe` discards both forms")
        self.assertIn("#263", doc)

    def test_the_evidence_conventions_distrust_a_zero_second_delivery(self):
        """Section 12 is where a record's fields and their readings are declared,
        and `waited_seconds: 0.0` is a reading: it is what a constant marker
        produced on #243's run while the transport delivered nothing."""
        plan = PARITY_PLAN.read_text(encoding="utf-8")
        section = plan[plan.index("## 12. "):]
        self.assertIn("waited_seconds", section,
                      "section 12 must name the field a reader has to distrust")
        self.assertIn("0.0", section)
        self.assertIn("#263", section)


class AmbientFigureTests(unittest.TestCase):
    """#264: this run counts the ambient rows it left, and does not assume them.

    Source pins, for this file's own reason: the counting happens in a browser
    against a host, and what went wrong in the family it belongs to was a figure
    nobody read rather than a value some function returned. #243's run left no
    figure at all and its evidence had to state an absolute count read on the
    host afterwards.
    """

    def test_both_commands_read_the_figure(self):
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            with self.subTest(command.__name__):
                self.assertIn("ambient_accounting(", source)
                self.assertIn("ambient_figure(first, second)", source)
                self.assertIn("navigation_basis=AMBIENT_BASIS", source)

    def test_the_window_opens_before_the_staging_navigates(self):
        """`stage` opens the to-do on both sessions, and those navigations have to
        be inside the figure. So the pair is opened by the command -- the first
        reading goes over a session's own RPC and cannot be taken before one
        exists -- and `stage` takes the two sessions it was given."""
        self.assertEqual(list(inspect.signature(stage).parameters),
                         ["first", "second", "task_id", "marker_text"])
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            with self.subTest(command.__name__):
                self.assertLess(source.index("open_pair("), source.index("ambient_accounting("))
                self.assertLess(source.index("ambient_accounting("), source.index("stage("))

    def test_a_failure_in_staging_now_closes_both_contexts(self):
        """It used to leave them to `browser.close()` in `main`, because `stage`
        both opened them and could raise before handing them back."""
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            with self.subTest(command.__name__):
                self.assertLess(source.index("open_pair("), source.index("try:"))
                self.assertIn("side.close()", source)

    def test_run_appends_its_figure_beside_the_records_it_appends(self):
        source = inspect.getsource(do_run)
        self.assertIn("out_path, command=\"run\", append=True", source)

    def test_probe_keeps_no_file_so_its_figure_is_printed(self):
        """`probe` prints and keeps nothing, which is the one thing about it that
        #263 did not change. A figure with nothing to sit beside is still read:
        "it writes nothing" is a claim about the field, never about the rows a
        page view leaves."""
        source = inspect.getsource(do_probe)
        self.assertIn("None, command=\"probe\"", source)

    def test_the_counts_come_over_the_session_and_never_over_ssh(self):
        """#256's rule, and the reason the figure is the run's own: a count read
        on the host afterwards is a different measurement, and two of them taken
        on different days cannot be subtracted."""
        import e2e_collab_peer_snapshot_live as module

        source = inspect.getsource(module.ambient_figure)
        self.assertIn("SessionAmbientDriver(first, second", source)
        self.assertNotIn("ssh", source)
        self.assertIn("mask=", source, "a reason in the record carries the host and the prefix")

    def test_a_measured_exit_code_is_returned_outside_the_accounting(self):
        """`ambient_accounting` raises a figure it could not write when the body
        left no exception of its own -- and a `return` from inside the `with` is
        exactly that. Both commands' exit codes are measurements: `probe`'s carries
        `wrote_nothing` (#263) and `run`'s carries the stored verdict, and `main`'s
        catch-all turns anything raised into exit 2. So the code is read inside the
        window and returned outside it, the way the adapter returns its own."""
        for command in (do_probe, do_run):
            source = inspect.getsource(command)
            lines = source.splitlines()
            opened = [len(line) - len(line.lstrip()) for line in lines
                      if line.lstrip().startswith("with ambient_accounting(")]
            returns = [len(line) - len(line.lstrip()) for line in lines
                       if line.lstrip().startswith("return ")]
            with self.subTest(command.__name__):
                self.assertEqual(len(opened), 1)
                self.assertTrue(returns)
                for indent in returns:
                    self.assertLessEqual(indent, opened[0],
                                         "a return inside the accounting makes its body look clean")

    def test_the_module_says_the_expected_zero_is_a_reading(self):
        """The delta here should be zero -- `/odoo/...` renders no tracked page --
        and that is the reason to read it rather than to skip it."""
        import e2e_collab_peer_snapshot_live as module

        said = " ".join(module.__doc__.split())
        self.assertIn("peer.ambient.json", said)
        self.assertIn("a zero that is read is a reading", said)
        self.assertIn("#264", said)
        self.assertIn("never over `ssh`", said)


if __name__ == "__main__":
    unittest.main()
