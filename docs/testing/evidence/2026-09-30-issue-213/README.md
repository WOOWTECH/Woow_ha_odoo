# Live check — the reworked cart step of #213, on a cart that starts empty (2026-09-30)

**Result: the cart step PR #229 shipped works on the real host, on both surfaces.**
The Public run added one line to an empty cart with a single answered click and reported
the write; the Ingress run found that cart holding one item, added nothing, and said so.
Both surfaces judged the same `sale.order`, the screen was available on both, and the one
`GAP` the diff records is the known `U-A2` doubled-prefix literal (#211), on every website
page an editor can see and nothing to do with the cart step.

| | |
|---|---|
| Owed by | PR #229 ("a Live-tier `open` run with a cart target on `odoo_parity` … is owed once this merges"), closing #213 |
| Adapter | `e2e_menu_action_adapter.py` at `0fabe9b` (the #229 squash-merge) — the change under test is client-side, in the test script, so the add-on Release does not gate it |
| Add-on | `1b7b4ce7_odoo18ce`, **0.4.6**, `state: started` |
| Database | `odoo_parity` (the 29 modules of #144); `ODOO_DB=odoo_parity` exported in the shell over the `.env`'s `odoo_test`, as recorded runs do |
| Surfaces | Public origin (`<PUBLIC_BASE>` = the Cloudflare tunnel) and HA Ingress |
| Scripts | `e2e_parity_shared_layers_live.py pcheck`, `e2e_menu_action_adapter.py open` (both surfaces) and `diff` |
| Runs | Public `WOOW-PARITY-20260930T153537Z`, Ingress `WOOW-PARITY-20260930T153647Z` |

## P-Checks — the baseline

All six PASS, before the run:

```
P-1 PASS public_url is https
P-2 PASS GET /web/login -> 200
P-3 PASS web.base.url = <PUBLIC_BASE>
P-4 PASS web.base.url.freeze = True
P-5 PASS website.domain = ['<PUBLIC_BASE>']
P-6 PASS same login on both surfaces, db ['odoo_parity', 'odoo_parity']
```

## The target

One target (`targets.jsonl`): `/shop/cart` with `expect_selector: "#cart_products"` and
`cart: /shop/woow-parity-20260929t045315z-service-58` — the #163 fixture product, still
published on `odoo_parity`. `#cart_products` renders only when the session's cart holds a
line (`website_sale/views/templates.xml`, `cart_lines`), so the selector showing *is* the
cart step having filled the cart. Preflight over JSON-RPC before the run: product 58
published and saleable, `S00002` (Administrator's website cart) a draft holding **0**
items — the empty cart the reworked click path exists for.

## What the cart step recorded

- **Public** (`public-open.jsonl`): `available: true`, `result: loaded`, and

  ```json
  {"model": "sale.order", "id": "2", "items": 1,
   "how": "added the product on /shop/woow-parity-20260929t045315z-service-58 to the cart (0 -> 1 items)"}
  ```

  One click, whose own POST answered — no retry note in `how`, no badge-wait fallback,
  and the order id came through the readings intact.

- **Ingress** (`ingress-open.jsonl`): `available: true`, `result: loaded`, and

  ```json
  {"model": "sale.order", "id": "2", "items": 1,
   "how": "the cart already held 1 item(s); nothing was added"}
  ```

  The second surface left the cart alone, so both judged the same cart of the same size —
  the cross-surface discipline `ensure_cart`'s docstring is about, and the write is still
  accounted on both records, including the surface that wrote nothing.

## The diff

`open-diff.jsonl`: 1 judged = 0 PARITY + 1 GAP. The GAP is URL literals only:
`/@/shop/cart` on the Public origin against `/@<INGRESS_PREFIX>/shop/cart` under Ingress —
the "Edit this content" link's doubled prefix, recorded as `U-A2` and tracked as **#211**
(open, `severity: important`). #163's run found the same literal on `/shop/payment` and
noted it is on every website page. Nothing about the cart, the screen or its signals
differs between the surfaces, so this run adds no new finding to the plan; it re-confirms
#211 on one more page.

What this run could not exercise: the retry arm (the first click landed, so no second
click ran) and the dead-element path — those stay covered by the 39 unit tests of #229,
which fake the pages. What only this run could show — a real shop bundle, a real
`/shop/cart/update` answer as the commit barrier, the badge readings over a real ingress
prefix, and the write accounting on both surfaces — is what it showed.

## Host state left behind

- `sale.order` `S00002`: the run's one line (product 58, qty 1) was **removed over
  JSON-RPC after the run**; the order is back to the empty draft the run found
  (`cart_quantity: 0`).
- Product 58 (`WOOW-PARITY-20260929T045315Z Service`) untouched, still published — it is
  #163's fixture, not this run's.
- Nothing was installed, restarted or reconfigured.
