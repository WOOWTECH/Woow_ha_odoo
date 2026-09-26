#!/usr/bin/env python3
"""A full ECPay stage payment on the Public origin (#146, parity plan U-E6, RC-10).

    python odoo18ce/tests/e2e_ecpay_stage_live.py run --env-file .env \
        --env-file <scratchpad>/ecpay-stage.env --db odoo_parity --out checks.jsonl

Follows WOOWTECH/ecpay_odoo18 `docs/testing_quick_start.md`: a price-included
5% tax, a published product with it, the ECPay provider in test mode, a guest
checkout on the Public origin, the stage cashier's test-payment link,
ECPay's server-to-server callback to `/payment/ecpay/result_notify`, then
Create Invoice, post, and Issue E-Invoice.

The callback is real inbound traffic from ECPay: it can only reach the
Public origin, so the checkout, the callback and the e-invoice are
`STRUCTURAL` records with the Public origin path that carries them. Under
Ingress only the back office is checked -- the provider, the transaction,
the order and the invoice forms -- on both surfaces.

The merchant credentials are the stage values the ECPay modules seed on
install; the run never types them. The payment is the stage cashier's
own test-payment link, not a typed card (see `pay_on_cashier`), so the run
needs no card either. The add-on log is read over SSH (`ECPAY_LOG_SSH`, e.g. `root@host`, and
`ECPAY_LOG_CONTAINER`).

The pure parts are tested in the static tier by test_e2e_ecpay_stage.py.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from e2e_menu_action_adapter import RunInfo
from e2e_parity_outbound import Bases, classify_url, url_shape
from e2e_parity_shared_layers import Outcome, check_record

CALLBACK_PATH = "/payment/ecpay/result_notify"
CHECKOUT_PATH = "/shop/payment"
# The redirect form's fields that ECPay calls back or sends the buyer to.
URL_FIELDS = ("ReturnURL", "OrderResultURL", "ClientBackURL", "PaymentInfoURL")
URLS_OK = "callback and return URLs on the Canonical URL over https"
CALLBACK_OK = "callback reached the Public origin; transaction done"
EINVOICE_OK = "e-invoice issued"


# --- Pure parts (static tier: test_e2e_ecpay_stage.py) -------------------------


def callback_urls_outcome(fields: Mapping[str, str], bases: Bases) -> Outcome:
    """Every URL ECPay is given must be the Canonical URL, and https (ECPay calls 443 only)."""
    if not fields.get("ReturnURL"):
        return Outcome(False, "no ReturnURL in the redirect form")
    urls: dict[str, dict[str, str]] = {}
    for name in URL_FIELDS:
        url = fields.get(name)
        if not url:
            continue
        kind = classify_url(url, bases)
        if kind == "canonical" and urlsplit(url).scheme != "https":
            kind = "not-https"
        urls[name] = {"kind": kind, "url": url_shape(url)}
    off = sum(1 for entry in urls.values() if entry["kind"] != "canonical")
    if not off:
        return Outcome(True, URLS_OK, details={"urls": urls})
    return Outcome(True, "%d callback URL%s off the Canonical URL" % (off, "" if off == 1 else "s"),
                   details={"urls": urls})


_ACCESS = re.compile(r'"POST %s[^"]*" (\d{3}) ' % re.escape(CALLBACK_PATH))


def callback_hits(lines: Iterable[str]) -> dict[str, Any]:
    """What the add-on log says about ECPay's callbacks: counts only, no payload."""
    hits: dict[str, Any] = {"result_notify_posts": [], "notifications_received": 0, "simulated": 0,
                            "mac_failures": 0, "customer_returns": 0}
    for line in lines:
        access = _ACCESS.search(line)
        if access:
            hits["result_notify_posts"].append(int(access.group(1)))
        elif "ECPay payment notification received" in line:
            hits["notifications_received"] += 1
            if re.search(r"""['"]SimulatePaid['"]: ['"]1['"]""", line):
                hits["simulated"] += 1
        elif "CheckMacValue verification failed" in line or "CheckMacValue is not correct" in line:
            hits["mac_failures"] += 1
        elif "ECPay customer return" in line:
            hits["customer_returns"] += 1
    return hits


def callback_outcome(hits: Mapping[str, Any], tx: Mapping[str, Any]) -> Outcome:
    state = tx.get("state") or "missing"
    details = {"log": dict(hits), "transaction_state": state}
    arrived = 200 in hits.get("result_notify_posts", []) and hits.get("notifications_received", 0) > 0
    if not arrived:
        return Outcome(True, "no callback in the add-on log; transaction %s" % state, details=details)
    if hits.get("mac_failures"):
        return Outcome(True, "callback arrived but its CheckMacValue failed; transaction %s" % state,
                       details=details)
    if state != "done":
        return Outcome(True, "callback arrived; transaction %s" % state, details=details)
    return Outcome(True, CALLBACK_OK, details=details)


# A Taiwan uniform invoice number: two letters, eight digits.
_UNIFORM_NUMBER = re.compile(r"^[A-Z]{2}\d{8}$")


def einvoice_outcome(move: Mapping[str, Any] | None) -> Outcome:
    if not move:
        return Outcome(False, "no posted invoice for the order")
    number = (move.get("ecpay_invoice_id") or [None, None])[1]
    details = {key: move.get(key) for key in ("name", "state", "uniform_state", "amount_total")}
    details["uniform_invoice"] = number
    if move.get("uniform_state") != "invoiced" or not number:
        return Outcome(True, "e-invoice not issued (%s)" % move.get("uniform_state"), details=details)
    if not _UNIFORM_NUMBER.match(number):
        return Outcome(True, "e-invoice number is not a uniform invoice number", details=details)
    return Outcome(True, EINVOICE_OK, details=details)


def _structural(run: RunInfo, screen: str, public: Outcome, ok: str, path: str, notes: str) -> dict[str, Any]:
    """Only the Public origin can carry it: STRUCTURAL when it worked there, a blocker GAP when not."""
    worked = public.available and public.result == ok
    return check_record(run, "U-E6", module="payment_ecpay", screen=screen, public=public, ingress=None,
                        verdict="STRUCTURAL" if worked else "GAP",
                        severity="none" if worked else "blocker",
                        public_path=path, route=path,
                        notes=notes if worked else "; ".join([notes, "public: %s" % public.result]))


def ecpay_records(run: RunInfo, urls: Outcome, callback: Outcome, invoice: Outcome,
                  back_office: Sequence[tuple[str, Outcome, Outcome]]) -> list[dict[str, Any]]:
    records = [
        _structural(run, "ECPay callback and return URLs", urls, URLS_OK, CALLBACK_PATH,
                    "The URLs in the redirect form the checkout posts to ECPay's stage cashier."),
        _structural(run, "ECPay stage payment callback", callback, CALLBACK_OK, CALLBACK_PATH,
                    "ECPay's server-to-server callback after a stage card payment; it has no Home "
                    "Assistant session, so only the Public origin can take it (RC-10)."),
        _structural(run, "ECPay e-invoice for the paid order", invoice, EINVOICE_OK, CHECKOUT_PATH,
                    "Create Invoice, post, Issue E-Invoice (manual mode) against ECPay's e-invoice stage."),
    ]
    for screen, public, ingress in back_office:
        records.append(check_record(run, "U-E6", module="payment_ecpay", screen=screen, public=public,
                                    ingress=ingress, notes="Back office only; the external traffic is "
                                                           "Public origin only."))
    return records


# --- Live part ---------------------------------------------------------------

import argparse  # noqa: E402 -- the live part keeps its imports with it
import datetime as dt  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from urllib.parse import parse_qsl  # noqa: E402

from e2e_menu_action_adapter import new_run_id, parse_env_file  # noqa: E402
from e2e_parity_shared_layers_live import ARTIFACTS, Env, PublicSide, Run, Side, open_sides  # noqa: E402

TIMEOUT = 60_000
STAGE_CASHIER = "payment-stage.ecpay.com.tw"
PRICE = 100.0
CALLBACK_WAIT_S = 180


def state_path(run_id: str) -> str:
    return os.path.join(ARTIFACTS, "%s-ecpay.json" % run_id)


def load_state(run_id: str) -> dict[str, Any]:
    if os.path.exists(state_path(run_id)):
        with open(state_path(run_id), encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def save_state(run_id: str, state: Mapping[str, Any]) -> None:
    os.makedirs(ARTIFACTS, exist_ok=True)
    with open(state_path(run_id), "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1)


def setup(admin: Side, marker: str, state: dict[str, Any]) -> None:
    """Quick start step 2: the 5% tax, a published product with it, the provider in test mode."""
    tax_name, product_name = "%s 營業稅 5%%" % marker, "%s ECPay" % marker
    found = admin.rpc("account.tax", "search", [[["name", "=", tax_name]]])
    if found:
        state["tax_id"] = found[0]
    else:
        country = admin.rpc("res.company", "read", [[1]], {"fields": ["account_fiscal_country_id"]})[0]
        country_id = country["account_fiscal_country_id"][0]
        group = admin.rpc("account.tax.group", "create", [{"name": "稅 5%", "country_id": country_id}])
        state["tax_id"] = admin.rpc("account.tax", "create", [{
            "name": tax_name, "amount": 5.0, "amount_type": "percent", "type_tax_use": "sale",
            "price_include_override": "tax_included", "tax_group_id": group, "country_id": country_id}])
    found = admin.rpc("product.template", "search", [[["name", "=", product_name]]])
    state["product_id"] = found[0] if found else admin.rpc("product.template", "create", [{
        "name": product_name, "list_price": PRICE, "type": "service", "sale_ok": True,
        "is_published": True, "taxes_id": [(6, 0, [state["tax_id"]])]}])
    provider = admin.rpc("payment.provider", "search_read", [[["code", "=", "ECPay"]]], {"fields": ["id"]})[0]
    method = admin.rpc("payment.method", "search_read",
                       [[["code", "=", "ecpay"], ["active", "in", [True, False]]]], {"fields": ["id"]})[0]
    # The provider first: Odoo refuses a method no enabled provider supports.
    admin.rpc("payment.provider", "write", [[provider["id"]], {
        "state": "test", "is_published": True, "ecpay_credit": True, "ecpay_domain": admin.env.public + "/"}])
    admin.rpc("payment.method", "write", [[method["id"]], {"active": True}])
    admin.rpc("payment.provider", "write", [[provider["id"]], {"payment_method_ids": [(4, method["id"])]}])
    state["provider_id"] = provider["id"]


def shot(page, run_id: str, name: str) -> None:
    os.makedirs(ARTIFACTS, exist_ok=True)
    page.screenshot(path=os.path.join(ARTIFACTS, "%s-ecpay-%s.png" % (run_id, name)), full_page=True)


def guest_checkout(page, public: str, product_url: str, marker: str) -> dict[str, str]:
    """Quick start step 3 as a guest: cart, address, the e-invoice defaults, ECPay, Pay Now.
    Returns the redirect form's fields, taken from the POST to the stage cashier."""
    posted: dict[str, str] = {}

    def on_request(request) -> None:
        if STAGE_CASHIER in request.url and request.method == "POST" and not posted:
            posted.update(parse_qsl(request.post_data or "", keep_blank_values=True))

    page.on("request", on_request)
    page.goto(public + product_url, wait_until="domcontentloaded", timeout=TIMEOUT)
    page.locator("#add_to_cart, a[data-action='add_to_cart'], button:has-text('Add to cart')").first.click()
    page.wait_for_timeout(2000)
    page.goto(public + "/shop/cart", wait_until="domcontentloaded", timeout=TIMEOUT)
    page.locator("a[name='website_sale_main_button'], a:has-text('Checkout')").first.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)
    if "/shop/address" in page.url:
        address = page.locator("form.checkout_autoformat, form[action*='/shop/address']").first
        for name, value in (("name", "%s Buyer" % marker), ("email", "buyer@example.com"),
                            ("phone", "0912345678"), ("street", "No. 1, Section 1, Test Rd."),
                            ("city", "Taipei"), ("zip", "100")):
            field = address.locator("[name='%s']" % name)
            if field.count():
                field.first.fill(value)
        country = address.locator("select[name='country_id']")
        if country.count():
            country.first.select_option(label="Taiwan")
            page.wait_for_timeout(1000)
        page.locator("button[name='website_sale_main_button'], a[name='website_sale_main_button'], "
                     "button:has-text('Continue checkout'), a:has-text('Continue checkout')").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1500)
    if "/shop/payment" not in page.url:
        # A confirm-order step (address review) sits between them on some configs.
        page.locator("a[name='website_sale_main_button'], button[name='website_sale_main_button']").first.click()
        page.wait_for_url("**/shop/payment**", timeout=TIMEOUT)
    page.locator("input[name='o_payment_radio'][data-provider-code='ECPay']").first.check()
    page.wait_for_timeout(1000)
    page.locator("button[name='o_payment_submit_button']").first.click()
    page.wait_for_url("**%s/**" % STAGE_CASHIER, timeout=TIMEOUT)
    page.wait_for_load_state("domcontentloaded")
    return posted


def pay_on_cashier(page, run_id: str, public: str) -> str | None:
    """Quick start 3.5 through the stage cashier's own "測試付款請點此" (test payment) link.

    Typing the test card does not work from Playwright: after Pay and the
    amount confirmation the cashier shows its test-environment notice and
    sends nothing (2026-09-27, headless and headed alike). The link opens
    ECPay's 模擬付款 page with the stage test card filled in; 交易成功 marks the
    order paid on ECPay's side, which then sends the same server-to-server
    callback, with SimulatePaid=1. Returns the path the buyer comes back to, if any."""
    with page.context.expect_page() as opened:
        page.locator("#aCREDIT").click()
    mock = opened.value  # 模擬付款: the stage test card prefilled, and 交易成功
    mock.wait_for_load_state("domcontentloaded")
    # Only the card number comes filled in; the rest is what the cashier's card form asks.
    for label, value in (("信用卡有效年(YY)", "30"), ("信用卡有效月(MM)", "12"),
                         ("信用卡安全碼", os.environ.get("ECPAY_TEST_CVV", "")), ("持卡人姓名", "TEST BUYER"),
                         ("手機號碼", "0912345678"), ("電子郵件", "buyer@example.com"), ("國碼", "886"),
                         ("地址", "Taipei")):
        field = mock.locator("xpath=//*[normalize-space(text())='%s']/following::input[1]" % label)
        if value and field.count() and not field.first.input_value():
            field.first.fill(value)
    shot(mock, run_id, "simulate")
    mock.get_by_text("交易成功").first.click()
    # The mock page closes itself; the cashier hears of the payment and moves on.
    try:
        mock.wait_for_event("close", timeout=30_000)
    except Exception:  # noqa: BLE001 -- still open is fine too
        mock.close()
    try:
        page.wait_for_url(public + "/**", timeout=TIMEOUT * 3)
    except Exception:  # noqa: BLE001 -- the buyer's return is not what U-E6 judges
        shot(page, run_id, "no-return")
        return None
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3000)
    shot(page, run_id, "back")
    return urlsplit(page.url).path
