#!/usr/bin/env python3
"""Static-tier tests for the pure parts of the shared-layer parity run (#143).

Nothing here opens a browser, a websocket or reads credentials.
"""
import json
import unittest

from e2e_menu_action_adapter import EVIDENCE_SCHEMA, RunInfo, Surface
from e2e_parity_shared_layers import (
    CATALOG,
    MODULE_SCREENS,
    NOT_RUN,
    Outcome,
    attach_issues,
    capability_upper_bound,
    check_record,
    conservation,
    judge,
    new_tab_verdict,
    planned_checks,
    seo_head_verdict,
    session_cookie_problems,
    sitemap_divergence,
)

RUN = RunInfo(run_id="WOOW-PARITY-20260925T000000Z", target="local", database="example_db")
PREFIX = "/api/hassio_ingress/tok_ABC123"


def ok(result: str = "done", **details) -> Outcome:
    return Outcome(available=True, result=result, details=details)


class CatalogTests(unittest.TestCase):
    def test_the_catalog_holds_groups_f_a_b_c_d_e_of_the_parity_plan(self) -> None:
        counts = {}
        for item in CATALOG.values():
            counts[item.group] = counts.get(item.group, 0) + 1
        self.assertEqual(counts, {"F": 5, "A": 10, "B": 8, "C": 27, "D": 8, "E": 7})
        self.assertEqual(CATALOG["U-C4"].root_cause, ("RC-3",))
        self.assertEqual(CATALOG["U-F5"].layer, "L0/L2")
        self.assertEqual(CATALOG["U-D7"].root_cause, ("RC-10",))

    def test_module_screens_name_catalogued_items(self) -> None:
        for item, module, screen in MODULE_SCREENS:
            self.assertIn(item, CATALOG)
            self.assertTrue(module and screen)

    def test_the_plan_runs_every_item_once_plus_each_module_screen(self) -> None:
        plan = planned_checks()
        shared = [item for item in CATALOG.values() if item.group != "E"]
        self.assertEqual(len(plan), len(shared) + len(MODULE_SCREENS))
        self.assertEqual(len(set(plan)), len(plan))
        self.assertIn(("U-C4", "shared", "generic"), plan)
        self.assertIn(("U-C4", "survey", "survey share dialog"), plan)
        self.assertIn(("U-F5", "point_of_sale", "POS receipt print"), plan)
        # U-D8 is two records: the head links plus robots.txt, and the sitemap (AD-8).
        self.assertIn(("U-D8", "shared", "generic"), plan)
        self.assertIn(("U-D8", "website", "sitemap.xml"), plan)


class JudgeTests(unittest.TestCase):
    def test_equal_clean_outcomes_are_parity(self) -> None:
        self.assertEqual(judge(ok(), ok()), ("PARITY", "none", []))

    def test_different_results_are_an_important_gap(self) -> None:
        verdict, severity, reasons = judge(ok("copied"), ok("nothing copied"))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons, ["result: public=copied ingress=nothing copied"])

    def test_an_unavailable_surface_or_an_escape_is_a_blocker(self) -> None:
        down = Outcome(available=False, result="blank page")
        self.assertEqual(judge(ok(), down)[:2], ("GAP", "blocker"))
        escaped = Outcome(available=True, result="done", signals={"route_escape": 1})
        self.assertEqual(judge(ok(), escaped), ("GAP", "blocker", ["ingress route_escape=1"]))

    def test_a_console_error_is_important(self) -> None:
        noisy = Outcome(available=True, result="done", signals={"console_error": 2})
        self.assertEqual(judge(noisy, ok()), ("GAP", "important", ["public console_error=2"]))


class RecordTests(unittest.TestCase):
    def test_a_check_record_has_the_v1_shape_and_both_surfaces(self) -> None:
        record = check_record(RUN, "U-C4", module="survey", screen="survey share dialog",
                              public=ok("copied"), ingress=ok("copied"))
        self.assertEqual(record["schema"], EVIDENCE_SCHEMA)
        self.assertEqual((record["item"], record["layer"], record["root_cause"]), ("U-C4", "L3", ["RC-3"]))
        self.assertEqual(record["screen"], {"route": None, "model": None, "view": None, "name": "survey share dialog"})
        self.assertEqual(record["control_identity"], "check:U-C4|survey|survey share dialog")
        self.assertEqual((record["verdict"], record["severity"]), ("PARITY", "none"))
        self.assertEqual(record["ingress"]["signals"]["route_escape"], 0)
        json.dumps(record)

    def test_an_explicit_verdict_overrides_the_judge(self) -> None:
        record = check_record(RUN, "U-B8", module="shared", screen="generic", public=ok("anonymous"),
                              ingress=ok("401"), verdict="APPROVED-DIVERGENCE", severity="none", notes="AD-6")
        self.assertEqual(record["verdict"], "APPROVED-DIVERGENCE")

    def test_structural_must_name_the_public_origin_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "Public origin path"):
            check_record(RUN, "U-D7", module="website_sale", screen="/shop", public=ok(), ingress=ok(),
                         verdict="STRUCTURAL", severity="none")
        record = check_record(RUN, "U-D7", module="website_sale", screen="/shop", public=ok(), ingress=ok(),
                              verdict="STRUCTURAL", severity="none", public_path="<PUBLIC_BASE>/shop")
        self.assertEqual(record["public_path"], "<PUBLIC_BASE>/shop")

    def test_not_run_must_name_its_blocker(self) -> None:
        with self.assertRaisesRegex(ValueError, "blocked_by"):
            check_record(RUN, "U-F5", module="point_of_sale", screen="POS receipt print",
                         public=None, ingress=None, verdict=NOT_RUN)
        record = check_record(RUN, "U-F5", module="point_of_sale", screen="POS receipt print",
                              public=None, ingress=None, verdict=NOT_RUN, blocked_by="#161")
        self.assertEqual((record["verdict"], record["severity"], record["blocked_by"]), (NOT_RUN, None, "#161"))
        self.assertIsNone(record["public"])

    def test_an_unknown_verdict_or_item_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            check_record(RUN, "U-C4", module="shared", screen="generic", public=ok(), ingress=ok(), verdict="PASS")
        with self.assertRaises(KeyError):
            check_record(RUN, "U-Z9", module="shared", screen="generic", public=ok(), ingress=ok())


class CapabilityTests(unittest.TestCase):
    ALL = ["clipboard-write", "fullscreen", "camera", "microphone"]

    def test_an_unrestricted_frame_in_a_secure_context_can_do_everything(self) -> None:
        bound = capability_upper_bound({"allow": None, "sandbox": None}, self.ALL, secure_context=True)
        self.assertTrue(all(entry["usable"] for entry in bound.values()))
        self.assertEqual(sorted(bound), ["camera", "clipboard-write", "downloads", "fullscreen", "microphone"])

    def test_an_insecure_context_blocks_only_the_secure_context_features(self) -> None:
        bound = capability_upper_bound({"allow": None, "sandbox": None}, self.ALL, secure_context=False)
        self.assertEqual({name for name, entry in bound.items() if not entry["usable"]},
                         {"clipboard-write", "camera", "microphone"})
        self.assertEqual(bound["camera"], {"policy": True, "usable": False, "limit": "insecure context"})
        self.assertEqual(bound["fullscreen"], {"policy": True, "usable": True, "limit": None})

    def test_the_iframe_policy_and_sandbox_are_limits_of_their_own(self) -> None:
        bound = capability_upper_bound({"allow": "fullscreen", "sandbox": "allow-scripts"}, ["fullscreen"],
                                       secure_context=True)
        self.assertEqual(bound["camera"]["limit"], "iframe policy")
        self.assertEqual(bound["downloads"], {"policy": False, "usable": False, "limit": "iframe sandbox"})
        sandboxed = capability_upper_bound({"sandbox": "allow-scripts allow-downloads"}, [], secure_context=True)
        self.assertTrue(sandboxed["downloads"]["usable"])


class CookieTests(unittest.TestCase):
    def cookie(self, **overrides) -> dict:
        values = {"name": "session_id", "path": PREFIX + "/", "secure": False, "httpOnly": True, "sameSite": "Lax"}
        values.update(overrides)
        return values

    def test_the_ingress_cookie_is_scoped_to_the_prefix(self) -> None:
        self.assertEqual(session_cookie_problems(self.cookie(), surface=Surface.HA_INGRESS,
                                                 ingress_prefix=PREFIX, https=False), [])
        self.assertEqual(session_cookie_problems(self.cookie(path="/"), surface=Surface.HA_INGRESS,
                                                 ingress_prefix=PREFIX, https=False),
                         ["Path=/ (expected %s/)" % PREFIX])

    def test_secure_follows_the_scheme(self) -> None:
        self.assertEqual(session_cookie_problems(self.cookie(), surface=Surface.HA_INGRESS,
                                                 ingress_prefix=PREFIX, https=True),
                         ["Secure=False (expected True)"])

    def test_the_public_cookie_is_root_scoped_and_secure(self) -> None:
        public = self.cookie(path="/", secure=True)
        self.assertEqual(session_cookie_problems(public, surface=Surface.PUBLIC, ingress_prefix=None, https=True), [])
        self.assertEqual(
            session_cookie_problems(dict(public, httpOnly=False, sameSite="None"), surface=Surface.PUBLIC,
                                    ingress_prefix=None, https=True),
            ["HttpOnly=False (expected True)", "SameSite=None (expected Lax)"],
        )

    def test_a_missing_cookie_is_one_problem(self) -> None:
        self.assertEqual(session_cookie_problems(None, surface=Surface.PUBLIC, ingress_prefix=None, https=True),
                         ["no session_id cookie"])


class SeoOutputTests(unittest.TestCase):
    """U-D8 as two decisions: the head links with `robots.txt`, and the sitemap (AD-8)."""

    def head(self, *wrong: str) -> Outcome:
        bases = ["<PUBLIC_BASE>", *(base for base in wrong if base.startswith("<"))]
        return Outcome(available=True, details={"bases": sorted(set(bases)), "wrong": list(wrong)},
                       result="all SEO URLs on <PUBLIC_BASE>" if not wrong else "SEO URLs on %s" % ", ".join(wrong))

    def test_head_links_on_the_canonical_url_on_both_surfaces_are_parity(self) -> None:
        self.assertEqual(seo_head_verdict(self.head(), self.head()), ("PARITY", "none", []))

    def test_a_base_that_is_not_the_canonical_url_is_a_gap(self) -> None:
        verdict, severity, reasons = seo_head_verdict(self.head(), self.head("<HA_BASE>"))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons, ["result: public=all SEO URLs on <PUBLIC_BASE> ingress=SEO URLs on <HA_BASE>",
                                   "ingress SEO URLs on <HA_BASE>"])

    def test_both_surfaces_wrong_in_the_same_way_is_still_a_gap(self) -> None:
        # judge() sees two equal results; U-D8's PASS rule is absolute, as in group E.
        verdict, severity, reasons = seo_head_verdict(self.head("relative URLs"), self.head("relative URLs"))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons, ["public SEO URLs on relative URLs", "ingress SEO URLs on relative URLs"])

    def test_an_unavailable_surface_stays_a_blocker(self) -> None:
        down = Outcome(available=False, result="error: blank page")
        self.assertEqual(seo_head_verdict(self.head(), down)[:2], ("GAP", "blocker"))

    ROBOTS = ("User-agent: *", "Disallow: /", "Sitemap: <PUBLIC_BASE>/sitemap.xml")
    PUBLIC_ROBOTS = ("User-agent: *", "Sitemap: <PUBLIC_BASE>/sitemap.xml")

    def sitemap(self, *, public=("<PUBLIC_BASE>",), ingress=("<HA_BASE>",), robots=ROBOTS,
                public_robots=PUBLIC_ROBOTS, status=200, prefixed=0, available=True) -> tuple[Outcome, Outcome]:
        def side(bases, robots_lines) -> Outcome:
            return Outcome(available=available, result="%d sitemap URL(s) on %s" % (len(bases),
                                                                                   ", ".join(bases) or "nothing"),
                           details={"bases": list(bases), "status": status, "robots": list(robots_lines)})
        public_side, ingress_side = side(public, public_robots), side(ingress, robots)
        if prefixed:
            ingress_side = Outcome(available, ingress_side.result,
                                   details={**ingress_side.details, "ingress_prefix": prefixed})
        return public_side, ingress_side

    def test_the_ingress_sitemap_following_the_request_address_is_ad_8(self) -> None:
        self.assertEqual(sitemap_divergence(*self.sitemap()), ("APPROVED-DIVERGENCE", "none", []))

    def test_a_robots_txt_that_no_longer_steers_crawlers_is_a_gap(self) -> None:
        verdict, severity, reasons = sitemap_divergence(*self.sitemap(robots=("User-agent: *",)))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons, ["ingress robots.txt has no 'Disallow: /'",
                                   "ingress robots.txt has no 'Sitemap: <PUBLIC_BASE>/sitemap.xml'"])
        # An empty website.domain (P-5) is exactly this: no Disallow, and the sitemap line follows the request.
        self.assertEqual(sitemap_divergence(*self.sitemap(
            robots=("User-agent: *", "Sitemap: <HA_BASE>/sitemap.xml")))[2],
            ["ingress robots.txt has no 'Disallow: /'",
             "ingress robots.txt has no 'Sitemap: <PUBLIC_BASE>/sitemap.xml'"])

    def test_the_divergence_disappearing_is_a_gap_too(self) -> None:
        verdict, _, reasons = sitemap_divergence(*self.sitemap(ingress=("<PUBLIC_BASE>",)))
        self.assertEqual(verdict, "GAP")
        self.assertEqual(reasons, ["ingress sitemap on <PUBLIC_BASE>: AD-8 no longer holds"])

    def test_the_public_origin_sitemap_must_stay_on_the_canonical_url_and_crawlable(self) -> None:
        self.assertEqual(sitemap_divergence(*self.sitemap(public=("<HA_BASE>",)))[2],
                         ["public sitemap on <HA_BASE>"])
        self.assertEqual(sitemap_divergence(*self.sitemap(public=()))[2], ["public sitemap on nothing"])
        self.assertEqual(sitemap_divergence(*self.sitemap(public_robots=("Disallow: /",)))[2],
                         ["public robots.txt says 'Disallow: /'"])

    def test_a_sitemap_with_no_url_at_all_is_a_gap(self) -> None:
        self.assertEqual(sitemap_divergence(*self.sitemap(ingress=()))[2], ["ingress sitemap has no URL"])

    def test_a_sitemap_that_was_not_served_is_a_gap(self) -> None:
        verdict, severity, reasons = sitemap_divergence(*self.sitemap(status=404))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons[:2], ["public sitemap.xml HTTP 404", "ingress sitemap.xml HTTP 404"])

    def test_an_ingress_prefix_inside_the_sitemap_is_a_blocker(self) -> None:
        verdict, severity, reasons = sitemap_divergence(*self.sitemap(prefixed=3))
        self.assertEqual((verdict, severity), ("GAP", "blocker"))
        self.assertEqual(reasons, ["ingress sitemap carries the Ingress prefix in 3 URL(s)"])

    def test_an_unavailable_surface_is_a_blocker_not_an_approved_divergence(self) -> None:
        verdict, severity, reasons = sitemap_divergence(*self.sitemap(available=False))
        self.assertEqual((verdict, severity), ("GAP", "blocker"))
        self.assertEqual(reasons[:2], ["public unavailable: 1 sitemap URL(s) on <PUBLIC_BASE>",
                                       "ingress unavailable: 1 sitemap URL(s) on <HA_BASE>"])

    def test_both_u_d8_records_reconcile_with_no_remainder(self) -> None:
        plan = [("U-D8", "shared", "generic"), ("U-D8", "website", "sitemap.xml")]
        public, ingress = self.sitemap()
        records = [
            check_record(RUN, "U-D8", module="shared", screen="generic", public=self.head(), ingress=self.head()),
            check_record(RUN, "U-D8", module="website", screen="sitemap.xml", public=public, ingress=ingress,
                         verdict="APPROVED-DIVERGENCE", severity="none", notes="AD-8"),
        ]
        report = conservation(records, plan)
        self.assertTrue(report["qualified"], report)
        self.assertEqual(report["counts"]["PARITY"], 1)
        self.assertEqual(report["counts"]["APPROVED-DIVERGENCE"], 1)


class NewTabTests(unittest.TestCase):
    """U-C23: a tab Odoo opens in the browser, and where its address lands.

    The shapes are the ones the #143 run recorded (`check:U-C23|shared|generic`,
    run `WOOW-PARITY-20260925T043539Z`): the survey's Test button.
    """

    PAGE = "This is a Test Survey Entry.\n\nGo to Survey"
    PUBLIC_SHAPE = "<PUBLIC_BASE>/survey/<token>"
    INGRESS_SHAPE = "<HA_BASE><INGRESS_PREFIX>/survey/<token>"

    def tab(self, shape: str, page_text: str | None = None) -> Outcome:
        text = self.PAGE if page_text is None else page_text
        carries = "<INGRESS_PREFIX>" in shape
        return Outcome(available=True, details={"shape": shape, "page_text": text},
                       result="new tab at %s%s" % (shape, " (carries the Ingress token)" if carries else ""))

    def pair(self, *, public: str | None = None, ingress: str | None = None,
             public_text: str | None = None, ingress_text: str | None = None) -> tuple[Outcome, Outcome]:
        return (self.tab(public or self.PUBLIC_SHAPE, public_text),
                self.tab(ingress or self.INGRESS_SHAPE, ingress_text))

    def test_the_same_page_under_the_ingress_prefix_is_structural(self) -> None:
        self.assertEqual(new_tab_verdict(*self.pair()),
                         ("STRUCTURAL", "none", [], "<PUBLIC_BASE>/survey/<token>"))

    def test_a_tab_that_did_not_open_stays_a_gap(self) -> None:
        public, _ = self.pair()
        down = Outcome(available=False, result="error at survey Test button: Timeout 20000ms exceeded")
        verdict, severity, reasons, public_path = new_tab_verdict(public, down)
        self.assertEqual((verdict, severity), ("GAP", "blocker"))
        self.assertEqual(reasons, ["ingress unavailable: error at survey Test button: Timeout 20000ms exceeded"])
        self.assertIsNone(public_path)

    def test_an_ingress_tab_off_the_prefix_is_a_gap(self) -> None:
        verdict, severity, reasons, public_path = new_tab_verdict(*self.pair(ingress="<HA_BASE>/survey/<token>"))
        self.assertEqual((verdict, severity), ("GAP", "important"))
        self.assertEqual(reasons, ["ingress tab at <HA_BASE>/survey/<token>, "
                                   "not under <HA_BASE><INGRESS_PREFIX>"])
        self.assertIsNone(public_path)

    def test_a_public_tab_off_the_canonical_url_is_a_gap(self) -> None:
        self.assertEqual(new_tab_verdict(*self.pair(public="<HA_BASE>/survey/<token>"))[2],
                         ["public tab at <HA_BASE>/survey/<token>, not under <PUBLIC_BASE>"])

    def test_two_tabs_on_different_pages_are_a_gap(self) -> None:
        verdict, _, reasons, _ = new_tab_verdict(*self.pair(ingress="<HA_BASE><INGRESS_PREFIX>/odoo/survey"))
        self.assertEqual(verdict, "GAP")
        self.assertEqual(reasons, ["the tabs opened different pages: public /survey/<token>, ingress /odoo/survey"])
        self.assertEqual(new_tab_verdict(*self.pair(ingress_text="Internal Server Error"))[2],
                         ["the two tabs do not render the same page"])

    def test_a_tab_with_nothing_in_it_is_not_the_same_page(self) -> None:
        self.assertEqual(new_tab_verdict(*self.pair(public_text="", ingress_text=""))[2],
                         ["public tab rendered no text", "ingress tab rendered no text"])

    def test_the_ingress_prefix_in_the_public_tab_address_is_a_leak_and_a_blocker(self) -> None:
        # Section 1.3: an Ingress token in an outbound address is a Blocker, not an Important.
        verdict, severity, reasons, public_path = new_tab_verdict(
            *self.pair(public="<PUBLIC_BASE><INGRESS_PREFIX>/survey/<token>"))
        self.assertEqual((verdict, severity), ("GAP", "blocker"))
        self.assertEqual(reasons, ["public tab address carries the Ingress prefix"])
        self.assertIsNone(public_path)

    def test_a_route_escape_under_ingress_is_a_blocker(self) -> None:
        public, ingress = self.pair()
        escaped = Outcome(True, ingress.result, signals={"route_escape": 1}, details=dict(ingress.details))
        verdict, severity, reasons, _ = new_tab_verdict(public, escaped)
        self.assertEqual((verdict, severity), ("GAP", "blocker"))
        self.assertEqual(reasons, ["ingress route_escape=1"])

    def test_the_structural_record_names_the_public_origin_path(self) -> None:
        verdict, severity, _, public_path = new_tab_verdict(*self.pair())
        record = check_record(RUN, "U-C23", module="shared", screen="generic", public=self.tab(self.PUBLIC_SHAPE),
                             ingress=self.tab(self.INGRESS_SHAPE), verdict=verdict, severity=severity,
                             public_path=public_path, model="survey.survey")
        self.assertEqual(record["verdict"], "STRUCTURAL")
        self.assertEqual(record["severity"], "none")
        self.assertEqual(record["root_cause"], ["RC-15"])
        self.assertEqual(record["public_path"], "<PUBLIC_BASE>/survey/<token>")


class ConservationTests(unittest.TestCase):
    PLAN = [("U-C4", "shared", "generic"), ("U-C4", "survey", "survey share dialog"), ("U-F5", "shared", "generic")]

    def records(self) -> list:
        return [
            check_record(RUN, "U-C4", module="shared", screen="generic", public=ok(), ingress=ok()),
            check_record(RUN, "U-C4", module="survey", screen="survey share dialog",
                         public=ok("copied"), ingress=ok("nothing")),
            check_record(RUN, "U-F5", module="shared", screen="generic", public=None, ingress=None,
                         verdict=NOT_RUN, blocked_by="#161"),
        ]

    def test_counts_add_up_to_the_observed_total(self) -> None:
        report = conservation(self.records(), self.PLAN)
        self.assertEqual(report["observed"], 3)
        self.assertEqual(report["counts"], {"PARITY": 1, "GAP": 1, "APPROVED-DIVERGENCE": 0, "STRUCTURAL": 0,
                                            NOT_RUN: 1})
        self.assertEqual(report["missing"], [])

    def test_a_gap_without_an_issue_or_a_not_run_disqualifies_the_run(self) -> None:
        report = conservation(self.records(), self.PLAN)
        self.assertFalse(report["qualified"])
        self.assertEqual(report["gaps_without_issue"], ["check:U-C4|survey|survey share dialog"])
        self.assertEqual(report["not_run"], ["check:U-F5|shared|generic"])

    def test_missing_and_unplanned_checks_are_listed(self) -> None:
        report = conservation(self.records()[:2], self.PLAN + [("U-D1", "shared", "generic")])
        self.assertEqual(report["missing"], ["check:U-D1|shared|generic", "check:U-F5|shared|generic"])
        extra = check_record(RUN, "U-D2", module="shared", screen="generic", public=ok(), ingress=ok())
        self.assertEqual(conservation(self.records() + [extra], self.PLAN)["unplanned"],
                         ["check:U-D2|shared|generic"])

    def test_a_run_with_every_gap_filed_and_nothing_left_out_qualifies(self) -> None:
        records = attach_issues(self.records()[:2], {"check:U-C4|survey|survey share dialog": 170})
        self.assertEqual(records[1]["issue"], "#170")
        report = conservation(records, self.PLAN[:2])
        self.assertTrue(report["qualified"], report)

    def test_attaching_an_issue_to_a_record_that_is_not_a_gap_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a GAP"):
            attach_issues(self.records(), {"check:U-C4|shared|generic": 170})


class LiveHelperTests(unittest.TestCase):
    """Pure helpers of the Live module; importing it opens no browser."""

    def test_path_tokens_are_masked_everywhere(self) -> None:
        from e2e_parity_shared_layers_live import _mask_tokens

        value = {"a": ["<PUBLIC_BASE>/survey/start/fd2b63b2-c0a7-4d71-9e52-bbf91e663dd7",
                       "/hr_attendance/0123456789abcdef0123456789abcdef"], "n": 3}
        self.assertEqual(_mask_tokens(value), {"a": ["<PUBLIC_BASE>/survey/start/<token>", "/hr_attendance/<token>"],
                                               "n": 3})
        self.assertEqual(_mask_tokens("S00001 /odoo/res.partner/9"), "S00001 /odoo/res.partner/9")

    def test_pdf_link_targets_are_read_from_uri_annotations(self) -> None:
        from e2e_parity_shared_layers_live import pdf_urls

        data = b"%PDF-1.4 << /A << /S /URI /URI (https://example.test/terms) >> >> /URI(https://example.test/terms)"
        self.assertEqual(pdf_urls(data), ["https://example.test/terms"])

    def test_xlsx_rows_counts_the_first_sheet(self) -> None:
        import io
        import zipfile

        from e2e_parity_shared_layers_live import xlsx_rows

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", '<sheetData><row r="1"/><row r="2"/></sheetData>')
        self.assertEqual(xlsx_rows(buffer.getvalue()), 2)


class LiveMaskTests(unittest.TestCase):
    ENVIRON = {"ODOO_PUBLIC_URL": "https://odoo.example.test", "HA_BASE_URL": "http://10.1.2.3:8123",
               "HA_HTTPS_BASE_URL": "https://ha.example.test", "HA_TOKEN": "tok-SECRET-123",
               "ADDON_SLUG": "abc_odoo18ce", "ODOO_TEST_LOGIN": "tester@example.test",
               "ODOO_TEST_PASSWORD": "pw-SECRET-456"}

    def env(self):
        from unittest import mock

        from e2e_parity_shared_layers_live import Env

        with mock.patch.dict("os.environ", self.ENVIRON, clear=False):
            env = Env("example_db")
        env.prefix = PREFIX
        return env

    def test_bases_hosts_prefix_and_credentials_are_masked(self) -> None:
        env = self.env()
        text = ("http://10.1.2.3:8123%s/odoo https://odoo.example.test/shop https://ha.example.test/x "
                "ws://10.1.2.3:8123/api/websocket host 10.1.2.3 and ha.example.test "
                "tok-SECRET-123 tester@example.test pw-SECRET-456" % PREFIX)
        masked = env.mask({"notes": text})["notes"]
        for secret in ("10.1.2.3", "odoo.example.test", "ha.example.test", "tok-SECRET-123", "tester@example.test",
                       "pw-SECRET-456", "tok_ABC123"):
            self.assertNotIn(secret, masked)
        self.assertIn("<INGRESS_BASE>/odoo", masked)
        self.assertIn("<PUBLIC_BASE>/shop", masked)
        self.assertIn("<HA_HTTPS_BASE>/x", masked)
        self.assertIn("<HA_HOST>", masked)
        self.assertIn("<HA_HTTPS_HOST>", masked)


class ScreenRecordTests(unittest.TestCase):
    def recorded(self, public: str, ingress: str) -> dict:
        from e2e_parity_shared_layers_live import record_screen

        written = []

        class FakeRun:
            def record(self, item, module, screen, public, ingress, **kwargs):
                written.append(check_record(RUN, item, module=module, screen=screen, public=public,
                                            ingress=ingress, **kwargs))

        record_screen(FakeRun(), "U-C25", "mrp", "MRP work order scan", ok(public), ok(ingress), "camera")
        return written[0]

    def test_a_screen_without_the_control_tested_nothing(self) -> None:
        record = self.recorded("scan: no camera control", "scan: no camera control")
        self.assertEqual(record["verdict"], NOT_RUN)
        self.assertIn("no camera control", record["blocked_by"])

    def test_a_screen_with_the_control_is_judged(self) -> None:
        self.assertEqual(self.recorded("scan: camera streaming", "scan: camera streaming")["verdict"], "PARITY")
        self.assertEqual(self.recorded("scan: camera streaming", "scan: no camera control")["verdict"], "GAP")


if __name__ == "__main__":
    unittest.main()
