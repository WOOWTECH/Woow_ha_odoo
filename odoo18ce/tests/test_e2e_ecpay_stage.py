#!/usr/bin/env python3
"""Static-tier tests for the pure parts of the ECPay stage payment run (#146).

Nothing here opens a browser, reads credentials or talks to ECPay.
"""
import unittest

from e2e_ecpay_stage_live import (
    callback_hits,
    callback_outcome,
    callback_urls_outcome,
    ecpay_records,
    einvoice_outcome,
)
from e2e_menu_action_adapter import RunInfo
from e2e_parity_outbound import Bases
from e2e_parity_shared_layers import Outcome

RUN = RunInfo(run_id="WOOW-PARITY-20260927T000000Z", target="local", database="example_db")
BASES = Bases(public="https://odoo.example.com", ha=("http://192.0.2.10:8123",),
              prefix="/api/hassio_ingress/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")


def form(**overrides):
    fields = {
        "ReturnURL": "https://odoo.example.com/payment/ecpay/result_notify",
        "OrderResultURL": "https://odoo.example.com/payment/ecpay/website_return",
        "ClientBackURL": "https://odoo.example.com/payment/ecpay/website_return",
        "PaymentInfoURL": "https://odoo.example.com/payment/ecpay/info_notify",
        "MerchantTradeNo": "odoo10927101010",
    }
    fields.update(overrides)
    return fields


class CallbackUrlTests(unittest.TestCase):
    def test_every_callback_and_return_url_on_the_canonical_url_over_https_passes(self) -> None:
        outcome = callback_urls_outcome(form(), BASES)
        self.assertTrue(outcome.available)
        self.assertEqual(outcome.result, "callback and return URLs on the Canonical URL over https")
        self.assertEqual(outcome.details["urls"]["ReturnURL"],
                         {"kind": "canonical", "url": "https://odoo.example.com/payment/ecpay/result_notify"})

    def test_a_return_url_under_the_ingress_prefix_is_a_token_leak(self) -> None:
        outcome = callback_urls_outcome(
            form(ReturnURL="http://192.0.2.10:8123" + BASES.prefix + "/payment/ecpay/result_notify"), BASES)
        self.assertEqual(outcome.result, "1 callback URL off the Canonical URL")
        self.assertEqual(outcome.details["urls"]["ReturnURL"]["kind"], "ingress-token")
        self.assertNotIn(BASES.prefix, str(outcome.details))

    def test_a_url_on_home_assistant_is_off_the_canonical_url(self) -> None:
        outcome = callback_urls_outcome(
            form(OrderResultURL="http://192.0.2.10:8123/payment/ecpay/website_return"), BASES)
        self.assertEqual(outcome.details["urls"]["OrderResultURL"]["kind"], "ha")
        self.assertEqual(outcome.result, "1 callback URL off the Canonical URL")

    def test_plain_http_on_the_public_host_is_not_enough_for_ecpay(self) -> None:
        plain = {name: url.replace("https:", "http:") for name, url in form().items()}
        outcome = callback_urls_outcome(plain, Bases(public="http://odoo.example.com"))
        self.assertEqual(outcome.details["urls"]["ReturnURL"]["kind"], "not-https")
        self.assertEqual(outcome.result, "4 callback URLs off the Canonical URL")

    def test_a_form_without_return_url_has_no_callback_to_judge(self) -> None:
        fields = form()
        del fields["ReturnURL"]
        outcome = callback_urls_outcome(fields, BASES)
        self.assertFalse(outcome.available)
        self.assertEqual(outcome.result, "no ReturnURL in the redirect form")

    def test_fields_that_are_not_urls_stay_out_of_the_evidence(self) -> None:
        outcome = callback_urls_outcome(form(), BASES)
        self.assertEqual(sorted(outcome.details["urls"]),
                         ["ClientBackURL", "OrderResultURL", "PaymentInfoURL", "ReturnURL"])


ACCESS_OK = ('172.30.33.0 - - [27/Sep/2026:10:15:02 +0800] "POST /payment/ecpay/result_notify HTTP/1.1" '
             '200 4 "-" "Mozilla/5.0" xfo="-" up')
ACCESS_OTHER = ('172.30.33.0 - - [27/Sep/2026:10:15:03 +0800] "POST /web/dataset/call_kw HTTP/1.1" '
                '200 43 "-" "Mozilla/5.0" xfo="-" up')
RECEIVED = ("2026-09-27 02:15:02,120 57 INFO odoo_parity odoo.addons.payment_ecpay.controllers.main: "
            "ECPay payment notification received: {'CustomField1': 'S00042', 'CheckMacValue': 'ABCDEF'}")
MAC_FAILED = ("2026-09-27 02:15:02,121 57 WARNING odoo_parity odoo.addons.payment_ecpay.controllers.main: "
              "ECPay CheckMacValue verification failed")
RETURN = ("2026-09-27 02:15:05,000 57 INFO odoo_parity odoo.addons.payment_ecpay.controllers.main: "
          "ECPay customer return, post data: {'RtnCode': '1'}")


class CallbackLogTests(unittest.TestCase):
    def test_the_callback_post_and_the_add_on_log_line_are_counted(self) -> None:
        hits = callback_hits([ACCESS_OTHER, ACCESS_OK, RECEIVED, RETURN])
        self.assertEqual(hits, {"result_notify_posts": [200], "notifications_received": 1,
                                "simulated": 0, "mac_failures": 0, "customer_returns": 1})

    def test_a_notification_from_the_cashiers_simulate_button_is_counted_as_simulated(self) -> None:
        simulated = RECEIVED.replace("{'CustomField1'", "{'SimulatePaid': '1', 'CustomField1'")
        hits = callback_hits([ACCESS_OK, simulated])
        self.assertEqual((hits["notifications_received"], hits["simulated"]), (1, 1))

    def test_nothing_of_the_payload_is_kept(self) -> None:
        hits = callback_hits([RECEIVED])
        self.assertNotIn("CheckMacValue", str(hits))

    def test_a_callback_with_a_good_mac_and_a_done_transaction_passes(self) -> None:
        outcome = callback_outcome(callback_hits([ACCESS_OK, RECEIVED]), {"state": "done", "reference": "S00042"})
        self.assertTrue(outcome.available)
        self.assertEqual(outcome.result, "callback reached the Public origin; transaction done")

    def test_no_callback_in_the_log_is_its_own_result(self) -> None:
        outcome = callback_outcome(callback_hits([ACCESS_OTHER]), {"state": "pending"})
        self.assertEqual(outcome.result, "no callback in the add-on log; transaction pending")

    def test_a_callback_whose_mac_failed_does_not_pass(self) -> None:
        outcome = callback_outcome(callback_hits([ACCESS_OK, RECEIVED, MAC_FAILED]), {"state": "pending"})
        self.assertEqual(outcome.result, "callback arrived but its CheckMacValue failed; transaction pending")

    def test_a_callback_that_arrived_but_left_the_transaction_open_does_not_pass(self) -> None:
        outcome = callback_outcome(callback_hits([ACCESS_OK, RECEIVED]), {"state": "error"})
        self.assertEqual(outcome.result, "callback arrived; transaction error")


def move(**overrides):
    record = {"id": 9, "name": "INV/2026/00002", "state": "posted", "uniform_state": "invoiced",
              "ecpay_invoice_id": [3, "GS20004636"], "amount_total": 100.0}
    record.update(overrides)
    return record


class EinvoiceTests(unittest.TestCase):
    def test_a_posted_invoice_with_an_ecpay_number_is_issued(self) -> None:
        outcome = einvoice_outcome(move())
        self.assertTrue(outcome.available)
        self.assertEqual(outcome.result, "e-invoice issued")
        self.assertEqual(outcome.details["uniform_invoice"], "GS20004636")

    def test_an_invoice_still_to_invoice_is_not_issued(self) -> None:
        outcome = einvoice_outcome(move(uniform_state="to invoice", ecpay_invoice_id=False))
        self.assertEqual(outcome.result, "e-invoice not issued (to invoice)")

    def test_a_number_that_is_not_a_taiwan_uniform_invoice_number_does_not_count(self) -> None:
        outcome = einvoice_outcome(move(ecpay_invoice_id=[3, "pending"]))
        self.assertEqual(outcome.result, "e-invoice number is not a uniform invoice number")

    def test_no_invoice_at_all(self) -> None:
        outcome = einvoice_outcome(None)
        self.assertFalse(outcome.available)
        self.assertEqual(outcome.result, "no posted invoice for the order")


class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.urls = callback_urls_outcome(form(), BASES)
        self.callback = callback_outcome(callback_hits([ACCESS_OK, RECEIVED]), {"state": "done"})
        self.invoice = einvoice_outcome(move())
        same = Outcome(True, "form opens; ECPay fields shown")
        self.records = ecpay_records(RUN, self.urls, self.callback, self.invoice,
                                     [("ECPay provider form", same, same)])

    def test_the_external_parts_are_structural_and_name_their_public_path(self) -> None:
        by_screen = {record["screen"]["name"]: record for record in self.records}
        for screen, path in (("ECPay callback and return URLs", "/payment/ecpay/result_notify"),
                             ("ECPay stage payment callback", "/payment/ecpay/result_notify"),
                             ("ECPay e-invoice for the paid order", "/shop/payment")):
            record = by_screen[screen]
            self.assertEqual(record["verdict"], "STRUCTURAL", screen)
            self.assertEqual(record["public_path"], path)
            self.assertEqual(record["item"], "U-E6")
            self.assertIsNone(record["ingress"])

    def test_a_structural_record_whose_public_side_failed_is_a_gap(self) -> None:
        failed = callback_outcome(callback_hits([]), {"state": "pending"})
        records = ecpay_records(RUN, self.urls, failed, self.invoice, [])
        record = next(r for r in records if r["screen"]["name"] == "ECPay stage payment callback")
        self.assertEqual(record["verdict"], "GAP")
        self.assertEqual(record["severity"], "blocker")

    def test_back_office_screens_are_judged_on_both_surfaces(self) -> None:
        record = next(r for r in self.records if r["screen"]["name"] == "ECPay provider form")
        self.assertEqual(record["verdict"], "PARITY")
        self.assertEqual(record["ingress"]["result"], "form opens; ECPay fields shown")


if __name__ == "__main__":
    unittest.main()
