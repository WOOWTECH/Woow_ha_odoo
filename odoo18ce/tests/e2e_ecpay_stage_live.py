#!/usr/bin/env python3
"""A full ECPay stage payment on the Public origin (#146, parity plan U-E6, RC-10).

    python odoo18ce/tests/e2e_ecpay_stage_live.py checkout --env-file .env \
        --env-file <scratchpad>/ecpay-log.env --db odoo_parity --run-id WOOW-PARITY-... --headed
    (a person pays on the stage cashier)
    python odoo18ce/tests/e2e_ecpay_stage_live.py verify --env-file .env \
        --env-file <scratchpad>/ecpay-log.env --db odoo_parity --run-id WOOW-PARITY-... \
        --order S00022 --out checks.jsonl

Follows WOOWTECH/ecpay_odoo18 `docs/testing_quick_start.md`. `checkout` makes
the price-included 5% tax, a published product with it and the ECPay
provider in test mode, then does a guest checkout on the Public origin up to
ECPay's stage cashier. A person pays there with the stage test card: from a
Playwright browser the cashier sends nothing after Pay and the amount
confirmation (2026-09-27, headless and headed alike), and its 測試付款請點此
link gave no callback either. `verify` then reads ECPay's server-to-server
callback to `/payment/ecpay/result_notify` and the redirect form Odoo
rendered from the add-on logs, and does Create Invoice, post and Issue
E-Invoice (manual mode).

The callback is real inbound traffic from ECPay: it can only reach the
Public origin, so the redirect form, the callback and the e-invoice are
`STRUCTURAL` records with the Public origin path that carries them. Under
Ingress only the back office is checked -- the provider, the transaction,
the order and the invoice forms -- on both surfaces.

The merchant credentials are the stage values the ECPay modules seed on
install; the run never types them, and it types no card. The add-on logs are
read over SSH: `ECPAY_LOG_SSH` (e.g. `root@host`) and `ECPAY_LOG_CONTAINER`.
Other environment as in e2e_parity_shared_layers_live.py.

The pure parts are tested in the static tier by test_e2e_ecpay_stage.py.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from e2e_menu_action_adapter import RunInfo, new_run_id, parse_env_file
from e2e_parity_outbound import Bases, classify_url, url_shape
from e2e_parity_shared_layers import Outcome, check_record
from e2e_parity_shared_layers_live import Env, PublicSide, Run, open_sides

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
_ENTRY_START = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ")
_FIELD = re.compile(r"'(\w+)': '([^']*)'")


def log_entries(lines: Iterable[str]) -> list[str]:
    """Odoo's log, one entry per record: a dict it logs runs over several lines."""
    entries: list[str] = []
    for line in lines:
        if _ENTRY_START.match(line) or not entries:
            entries.append(line)
        else:
            entries[-1] += "\n" + line
    return entries


def _fields(entry: str) -> dict[str, str]:
    return dict(_FIELD.findall(entry))


def rendering_urls(odoo_lines: Iterable[str], reference: str) -> dict[str, str]:
    """The URLs in the redirect form Odoo rendered for this transaction (Odoo's payment module logs it)."""
    marker = "rendering values for transaction with reference %s:" % reference
    for entry in log_entries(odoo_lines):
        if marker in entry:
            fields = _fields(entry)
            return {name: fields[name] for name in URL_FIELDS if name in fields}
    return {}


def callback_hits(odoo_lines: Iterable[str], access_lines: Iterable[str], reference: str) -> dict[str, Any]:
    """What the add-on logs say about ECPay's callbacks for one transaction: no payload is kept."""
    hits: dict[str, Any] = {"result_notify_posts": [], "notifications": [], "mac_failures": 0,
                            "customer_returns": 0}
    for line in access_lines:
        access = _ACCESS.search(line)
        if access:
            hits["result_notify_posts"].append(int(access.group(1)))
    for entry in log_entries(odoo_lines):
        fields = _fields(entry)
        if "ECPay payment notification received" in entry and fields.get("CustomField1") == reference:
            hits["notifications"].append({"rtn_code": fields.get("RtnCode"), "payment_type": fields.get("PaymentType"),
                                          "simulated": fields.get("SimulatePaid") == "1"})
        elif "CheckMacValue verification failed" in entry or "CheckMacValue is not correct" in entry:
            hits["mac_failures"] += 1
        elif "ECPay customer return" in entry and fields.get("CustomField1") == reference:
            hits["customer_returns"] += 1
    return hits


def callback_outcome(hits: Mapping[str, Any], tx: Mapping[str, Any]) -> Outcome:
    state = tx.get("state") or "missing"
    details = {"log": dict(hits), "transaction_state": state}
    arrived = 200 in hits.get("result_notify_posts", []) and bool(hits.get("notifications"))
    if not arrived:
        return Outcome(True, "no callback in the add-on log; transaction %s" % state, details=details)
    if hits.get("mac_failures"):
        return Outcome(True, "callback arrived but its CheckMacValue failed; transaction %s" % state,
                       details=details)
    if state != "done":
        return Outcome(True, "callback arrived; transaction %s" % state, details=details)
    if any(notification["simulated"] for notification in hits["notifications"]):
        return Outcome(True, "callback reached the Public origin; simulated payment", details=details)
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

TIMEOUT = 60_000
STAGE_CASHIER = "payment-stage.ecpay.com.tw"
PRICE = 100.0
ODOO_LOG = "/data/odoo/logs/odoo-server.log"
# Back-office forms, the ECPay field each must show on both surfaces, and the
# notebook page it sits on when that is not the first one.
BACK_OFFICE = (
    ("ECPay provider form", "payment.provider", "MerchantID", None),
    ("ECPay transaction form", "payment.transaction", "provider_reference", None),
    ("ECPay sale order form", "sale.order", "ecpay_info_ids", None),
    ("ECPay invoice form", "account.move", "uniform_state", "uniform_invoice"),
)


def setup(admin, marker: str) -> dict[str, int]:
    """Quick start step 2: the 5% tax, a published product with it, the provider in test mode.
    Records are named with the run marker and found again on a rerun."""
    ids: dict[str, int] = {}
    tax_name, product_name = "%s 營業稅 5%%" % marker, "%s ECPay" % marker
    found = admin.rpc("account.tax", "search", [[["name", "=", tax_name]]])
    if found:
        ids["tax"] = found[0]
    else:
        country = admin.rpc("res.company", "read", [[1]], {"fields": ["account_fiscal_country_id"]})[0]
        country_id = country["account_fiscal_country_id"][0]
        group = admin.rpc("account.tax.group", "create", [{"name": "稅 5%", "country_id": country_id}])
        ids["tax"] = admin.rpc("account.tax", "create", [{
            "name": tax_name, "amount": 5.0, "amount_type": "percent", "type_tax_use": "sale",
            "price_include_override": "tax_included", "tax_group_id": group, "country_id": country_id}])
    found = admin.rpc("product.template", "search", [[["name", "=", product_name]]])
    ids["product"] = found[0] if found else admin.rpc("product.template", "create", [{
        "name": product_name, "list_price": PRICE, "type": "service", "sale_ok": True,
        "is_published": True, "taxes_id": [(6, 0, [ids["tax"]])]}])
    provider = admin.rpc("payment.provider", "search_read", [[["code", "=", "ECPay"]]], {"fields": ["id"]})[0]
    method = admin.rpc("payment.method", "search_read",
                       [[["code", "=", "ecpay"], ["active", "in", [True, False]]]], {"fields": ["id"]})[0]
    # The provider first: Odoo refuses a method no enabled provider supports.
    admin.rpc("payment.provider", "write", [[provider["id"]], {
        "state": "test", "is_published": True, "ecpay_credit": True, "ecpay_domain": admin.env.public + "/"}])
    admin.rpc("payment.method", "write", [[method["id"]], {"active": True}])
    admin.rpc("payment.provider", "write", [[provider["id"]], {"payment_method_ids": [(4, method["id"])]}])
    ids["provider"] = provider["id"]
    return ids


def guest_checkout(page, public: str, product_url: str, marker: str) -> None:
    """Quick start step 3 as a guest, up to the stage cashier: cart, address, the
    e-invoice defaults (電子發票, 無載具), ECPay, Pay Now."""
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


def read_logs(since: str) -> tuple[list[str], list[str]]:
    """The add-on's Odoo log and its access log (the container's stdout), over SSH."""
    host, container = os.environ["ECPAY_LOG_SSH"], os.environ["ECPAY_LOG_CONTAINER"]

    def remote(command: str) -> list[str]:
        result = subprocess.run(["ssh", "-o", "BatchMode=yes", host, command], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120)
        return (result.stdout + result.stderr).splitlines()

    odoo = remote("docker exec %s cat %s" % (container, ODOO_LOG))
    access = remote("docker logs --since %s %s 2>&1 | grep 'POST /payment/ecpay/'" % (since, container))
    return odoo, access


def issue_einvoice(admin, order_id: int) -> dict[str, Any] | None:
    """Quick start 4.2-4.3: Create Invoice (regular), Confirm, Issue E-Invoice (manual mode)."""
    context = {"active_model": "sale.order", "active_ids": [order_id], "active_id": order_id}
    order = admin.rpc("sale.order", "read", [[order_id]], {"fields": ["invoice_ids"]})[0]
    if not order["invoice_ids"]:
        wizard = admin.rpc("sale.advance.payment.inv", "create", [{
            "advance_payment_method": "delivered", "sale_order_ids": [(6, 0, [order_id])]}], {"context": context})
        admin.rpc("sale.advance.payment.inv", "create_invoices", [[wizard]], {"context": context})
        order = admin.rpc("sale.order", "read", [[order_id]], {"fields": ["invoice_ids"]})[0]
    if not order["invoice_ids"]:
        return None
    move_id = order["invoice_ids"][0]
    fields = ["name", "state", "uniform_state", "ecpay_invoice_id", "amount_total"]
    move = admin.rpc("account.move", "read", [[move_id]], {"fields": fields})[0]
    if move["state"] == "draft":
        admin.rpc("account.move", "action_post", [[move_id]])
    if not move["ecpay_invoice_id"]:
        admin.rpc("account.move", "create_ecpay_invoice", [[move_id]])
    return admin.rpc("account.move", "read", [[move_id]], {"fields": fields})[0]


def form_check(model: str, record_id: int, field: str, page: str | None) -> Callable:
    def check(side) -> Outcome:
        side.goto("/odoo/%s/%d" % (model, record_id))
        side.wait_webclient()
        if page:
            side.root.locator(".o_notebook_headers a[name='%s']" % page).first.click()
            side.settle()
        shown = side.root.locator(".o_form_view [name='%s']" % field).count() > 0
        return Outcome(True, "form opens; %s %s" % (field, "shown" if shown else "missing"))
    return check


def load_env(files: Sequence[str] | None, db: str) -> Env:
    for path in files or ():
        with open(path, encoding="utf-8") as handle:
            parse_env_file(handle, os.environ)
    os.environ["ODOO_DB"] = db
    return Env(db)


def command_checkout(args) -> int:
    """Setup, then a guest checkout left on the stage cashier for a person to pay."""
    env = load_env(args.env_file, args.db)
    run_id = args.run_id or new_run_id()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        admin = PublicSide(env, browser)
        try:
            admin.start()
            ids = setup(admin, run_id)
            product = admin.rpc("product.template", "read", [[ids["product"]]], {"fields": ["website_url"]})[0]
            buyer = browser.new_context()
            guest_checkout(buyer.new_page(), env.public, product["website_url"], run_id)
            tx = admin.rpc("payment.transaction", "search_read", [[["provider_code", "=", "ECPay"]]],
                           {"fields": ["reference"], "order": "id desc", "limit": 1})[0]
            print("%s: %s is on the stage cashier" % (run_id, tx["reference"]), file=sys.stderr)
            if args.headed:
                input("Pay it in the browser, then press Enter... ")
            return 0
        finally:
            admin.close()
            browser.close()


def command_verify(args) -> int:
    """After the payment: the callback, the paid order, the e-invoice, and the back office."""
    env = load_env(args.env_file, args.db)
    info = RunInfo(args.run_id or new_run_id(), env.target, env.db)
    odoo_log, access_log = read_logs(args.since)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        public = ingress = None
        try:
            public, ingress = open_sides(env, browser)
            bases = Bases(public=env.public, ha=[base for base in (env.ha, env.ha_https) if base], prefix=env.prefix)
            tx = public.rpc("payment.transaction", "search_read", [[["reference", "=", args.order]]],
                            {"fields": ["state", "sale_order_ids", "provider_id"]})[0]
            order_id = tx["sale_order_ids"][0]
            urls = callback_urls_outcome(rendering_urls(odoo_log, args.order), bases)
            callback = callback_outcome(callback_hits(odoo_log, access_log, args.order), tx)
            order = public.rpc("sale.order", "read", [[order_id]], {"fields": ["state"]})[0]
            callback = Outcome(callback.available, callback.result,
                               details={**callback.details, "order_state": order["state"]})
            move = issue_einvoice(public, order_id)
            invoice = einvoice_outcome(move)
            targets = {"payment.provider": tx["provider_id"][0], "payment.transaction": tx["id"],
                       "sale.order": order_id, "account.move": move and move["id"]}
            with open(args.out, "a", encoding="utf-8") as out:
                run = Run(env, info, public, ingress, out, browser)
                back_office = [(screen, *run.both(form_check(model, targets[model], field, page)))
                               for screen, model, field, page in BACK_OFFICE if targets[model]]
                for record in ecpay_records(info, urls, callback, invoice, back_office):
                    run.write(record)
            return 0
        finally:
            for side in (public, ingress):
                if side is not None:
                    side.close()
            browser.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("checkout", "verify"):
        sub = commands.add_parser(name)
        sub.add_argument("--env-file", action="append", help="NAME=value file; may be given more than once")
        sub.add_argument("--db", required=True, help="the database both surfaces must serve")
        sub.add_argument("--run-id", help="the run marker; keep one across checkout and verify")
        sub.add_argument("--headed", action="store_true")
    verify = commands.choices["verify"]
    verify.add_argument("--order", required=True, help="the paid transaction's reference, e.g. S00022")
    verify.add_argument("--since", default="6h", help="how far back the access log is read (docker logs --since)")
    verify.add_argument("--out", required=True, help="JSONL file; records are appended")
    args = parser.parse_args(argv)
    return command_checkout(args) if args.command == "checkout" else command_verify(args)


if __name__ == "__main__":
    sys.exit(main())
