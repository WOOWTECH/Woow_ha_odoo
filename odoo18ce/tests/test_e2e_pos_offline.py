#!/usr/bin/env python3
"""Static-tier tests for the pure parts of the POS offline run (#161).

Nothing here opens a browser or reads credentials.
"""
import unittest

from e2e_menu_action_adapter import RunInfo
from e2e_parity_shared_layers import Outcome
from e2e_pos_offline_live import net_error, pos_records, reload_outcome, sale_outcome

RUN = RunInfo(run_id="WOOW-PARITY-20260926T000000Z", target="local", database="example_db")
UUID = "0f6c1d9e-1111-4222-8333-944455556666"


def local(**overrides):
    facts = {"uuid": UUID, "went_offline": True, "validated_offline": True, "offline_notice": "Connection Lost"}
    facts.update(overrides)
    return facts


def row(**overrides):
    order = {"id": 7, "uuid": UUID, "session_id": [5, "POS/00002"], "state": "paid",
             "amount_total": 2.0, "pos_reference": "Order 00005-001-0001"}
    order.update(overrides)
    return order


class SaleOutcomeTests(unittest.TestCase):
    def test_an_order_sold_offline_and_found_in_the_session_after_reconnect_is_synced(self) -> None:
        outcome = sale_outcome(local(), [row()], session_id=5)
        self.assertTrue(outcome.available)
        self.assertEqual(outcome.result, "offline sale reached the server after reconnect")
        self.assertEqual(outcome.details["server_order"]["state"], "paid")

    def test_an_order_missing_on_the_server_is_not_synced(self) -> None:
        outcome = sale_outcome(local(), [], session_id=5)
        self.assertEqual(outcome.result, "offline sale not on the server after reconnect")

    def test_an_order_in_another_session_does_not_count(self) -> None:
        outcome = sale_outcome(local(), [row(session_id=[9, "POS/00009"])], session_id=5)
        self.assertEqual(outcome.result, "offline sale landed in another session")

    def test_a_till_that_never_went_offline_did_not_test_anything(self) -> None:
        outcome = sale_outcome(local(went_offline=False), [row()], session_id=5)
        self.assertFalse(outcome.available)
        self.assertIn("never offline", outcome.result)

    def test_a_sale_the_till_refused_to_validate_offline_is_its_own_result(self) -> None:
        outcome = sale_outcome(local(validated_offline=False), [], session_id=5)
        self.assertEqual(outcome.result, "till could not validate the sale offline")


class ReloadOutcomeTests(unittest.TestCase):
    def test_net_error_takes_the_chromium_code_out_of_a_playwright_message(self) -> None:
        message = "Page.reload: net::ERR_INTERNET_DISCONNECTED at https://example.test/pos/ui"
        self.assertEqual(net_error(message), "net::ERR_INTERNET_DISCONNECTED")
        self.assertIsNone(net_error("Timeout 60000ms exceeded."))

    def test_a_failed_reload_names_the_code_and_not_the_url(self) -> None:
        outcome = reload_outcome("Frame.goto: net::ERR_INTERNET_DISCONNECTED at https://h/api/x/pos/ui",
                                 till_loaded=False)
        self.assertEqual(outcome.result, "offline reload fails (net::ERR_INTERNET_DISCONNECTED)")

    def test_a_reload_that_brings_the_till_back_is_a_different_result(self) -> None:
        self.assertEqual(reload_outcome(None, till_loaded=True).result, "offline reload loads the till")
        self.assertEqual(reload_outcome(None, till_loaded=False).result, "offline reload shows no till")


class RecordTests(unittest.TestCase):
    def test_both_surfaces_alike_give_two_parity_records_under_u_c27(self) -> None:
        sale = Outcome(True, "offline sale reached the server after reconnect")
        reload = Outcome(True, "offline reload fails (net::ERR_INTERNET_DISCONNECTED)")
        records = pos_records(RUN, sale, sale, reload, reload)
        self.assertEqual([r["control_identity"] for r in records],
                         ["check:U-C27|point_of_sale|POS offline sale",
                          "check:U-C27|point_of_sale|POS offline reload"])
        self.assertEqual([r["verdict"] for r in records], ["PARITY", "PARITY"])
        self.assertEqual(records[0]["screen"]["route"], "/pos/ui")

    def test_an_ingress_only_failure_is_a_gap(self) -> None:
        good = Outcome(True, "offline sale reached the server after reconnect")
        bad = Outcome(True, "offline sale not on the server after reconnect")
        reload = Outcome(True, "offline reload fails (net::ERR_INTERNET_DISCONNECTED)")
        sale_record, _ = pos_records(RUN, good, bad, reload, reload)
        self.assertEqual(sale_record["verdict"], "GAP")
        self.assertIn("result: public=", sale_record["notes"])


if __name__ == "__main__":
    unittest.main()
