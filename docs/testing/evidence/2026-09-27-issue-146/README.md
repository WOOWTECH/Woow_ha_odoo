# An ECPay stage payment on the Public origin (#146)

Run `WOOW-PARITY-20260926T174413Z`, 2026-09-27, against the test host's Released add-on
`1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`**, with the ECPay modules from
WOOWTECH/ecpay_odoo18 `56cb04c` (#144). It follows that repository's
`docs/testing_quick_start.md`. Driver: `odoo18ce/tests/e2e_ecpay_stage_live.py`, with static tests
for its pure parts in `test_e2e_ecpay_stage.py`.

This is the only real inbound external traffic in the round (`U-E6`, `RC-10`): ECPay's server
calls the Public origin back. It has no Home Assistant session, so the payment, the callback and
the e-invoice run on the Public origin only and are `STRUCTURAL`. Under Ingress the run checks
the back office: the provider, the transaction, the order and the invoice.

No credential was typed or written down. The ECPay modules seed the stage merchant and
e-invoice credentials on install. The card was the stage test card from ECPay's developer page
for the AIO cashier (https://developers.ecpay.com.tw/?p=2856), typed by the maintainer.

## Setup (quick start step 2)

The maintainer approved these writes on `odoo_parity` in the session:

| What | Record |
|---|---|
| Tax `WOOW-PARITY-20260926T174413Z 營業稅 5%`: 5 %, sales, 已連稅 (price-included), new tax group `稅 5%` | `account.tax` 3 |
| Product `WOOW-PARITY-20260926T174413Z ECPay`, service, NT$100 with that tax, published | `product.template` 55 |
| ECPay provider: state `test`, published, 信用卡一次付清 on | `payment.provider` 18 |
| Payment method `ecpay`, which ships inactive: activated and linked to the provider | `payment.method` 221 |

Odoo refuses to activate a payment method that no enabled provider supports, so the driver
enables the provider first. The e-invoice settings were already right: test mode, 手動 (manual)
issue, seeded credentials.

## The payment (quick start step 3)

A guest checkout on the Public origin: product, cart, address (a Taipei test address), the
e-invoice defaults (電子發票, 無載具), ECPay, Pay Now. Order **S00022**, NT$100.

The checkout ran in the maintainer's Chrome (Claude in Chrome) up to ECPay's stage cashier. The
maintainer typed the test card and paid. From a Playwright browser the cashier does not pay:

- With the card typed and 立即付款 → 確定 pressed, the cashier shows its test-environment notice
  and sends no request. Headless, headed and without the webdriver flag gave the same.
- Its 測試付款請點此 link opens a 模擬付款 page. 交易成功 there answers 200, but no callback came
  and the cashier did not move. ECPay documents 模擬付款 only in the vendor admin
  (`vendor-stage.ecpay.com.tw`), not on the cashier.

Those attempts left 15 more orders, `S00007`–`S00021`, with ECPay transactions. 14 are `draft`.
`S00021` is `error`: ECPay sent a callback for it at 2026-09-26 20:00 UTC, about 1.5 hours after
the attempt, with RtnCode `10100284` (商店未請求3D授權, "the shop did not ask for 3-D
authorisation"). That callback reached the Public origin too.

## Checks: `checks.jsonl`

| Check | Public origin | Ingress | Verdict |
|---|---|---|---|
| ECPay callback and return URLs | `ReturnURL`, `OrderResultURL`, `ClientBackURL`, `PaymentInfoURL` all on the Canonical URL over https, with no Ingress token | cannot take them | `STRUCTURAL` (`/payment/ecpay/result_notify`) |
| ECPay stage payment callback | `POST /payment/ecpay/result_notify` 200 at 02:12:51 UTC. The notification for `S00022`: RtnCode `1`, `Credit_CreditCard`, not simulated. CheckMacValue passed. Transaction `done`, order `sale` | cannot take it | `STRUCTURAL` (`/payment/ecpay/result_notify`) |
| ECPay e-invoice for the paid order | `INV/2026/00002` posted; Issue E-Invoice gave uniform invoice **`LO22046163`**, `uniform_state` `invoiced` | not run | `STRUCTURAL` (`/shop/payment`) |
| ECPay provider form | opens, `MerchantID` shown | the same | `PARITY` |
| ECPay transaction form | opens, `provider_reference` shown | the same | `PARITY` |
| ECPay sale order form | opens, the ECPay payment rows (`ecpay_info_ids`) shown | the same | `PARITY` |
| ECPay invoice form | opens; on the 綠界電子發票 page `uniform_state` is shown | the same | `PARITY` |

No signals on either surface.

`verify` takes the redirect form's URLs from the add-on's Odoo log, where Odoo's payment module
logs the rendering values of each transaction, not from the browser. So they are the URLs Odoo
gave ECPay for `S00022`, whichever browser posted the form. They come from
`provider.get_base_url()`, which is the website domain, which is the Canonical URL. The
provider's own 網域名稱 field (`ecpay_domain`) is not used by the module.

The callback went through the Cloudflare tunnel to the Public origin and was accepted. The quick
start's note that callbacks cannot go through a CDN such as Cloudflare did not hold here.

## Crawler diff: `crawl-diff.jsonl`

`e2e_menu_action_adapter.py crawl` on both surfaces for `account` (Invoicing) and `sale`: the
ECPay menus have no root menu of their own and sit under those two apps (as in #144), then
`diff`. Result: 51 actions, 51 `PARITY`, 0 `GAP`. One was skipped: `account.menu_action_account_bank_journal_form`
is a server action, which the crawler never runs.

The back-office screens of this run among them, all `PARITY`:

- `payment_ecpay.menuitem_order_ecpay` (the ECPay order data)
- `ecpay_invoice_tw.uniform_invoice_menu` (the e-invoices)
- `account_payment.payment_provider_menu` and `sale.payment_provider_menu` (payment providers)
- `account_payment.payment_method_menu` and `sale.payment_method_menu` (payment methods)
- `account.menu_action_move_out_invoice_type` (customer invoices)
- `account.menu_action_account_payments_receivable` (customer payments)
- `sale.menu_sale_order_invoice` (orders to invoice)

Odoo 18 has no Payment Transactions menu outside debug mode. The transaction form is covered by
`ECPay transaction form` above.

## What the run left

On `odoo_parity`: the four setup records above, the ECPay provider in test mode and published
(the shop offers ECPay at checkout), the guest partner `WOOW-PARITY-20260926T174413Z Buyer`,
`S00022` with `INV/2026/00002` and e-invoice `LO22046163`, and the 15 attempt orders. Nothing
was deleted.

## Acceptance criteria

- [x] Callback and return URLs are the Public origin, with no Ingress token.
- [x] One paid order (`S00022`) and one issued e-invoice (`LO22046163`), with the callback in the
  add-on log.
- [x] The Ingress back-office screens pass the crawler diff.
