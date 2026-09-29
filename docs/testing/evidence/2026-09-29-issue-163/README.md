# The three modules the menu crawler cannot reach (#163)

Run on 2026-09-29 against the test host's Released add-on `1b7b4ce7_odoo18ce`
at **0.4.5**, database **`odoo_parity`** (the 29 modules of #144), which is the
add-on's `default_db`, so the Public origin serves it. `odoo_test` was not
touched.

Driver: the new `open` subcommand of `odoo18ce/tests/e2e_menu_action_adapter.py`
(pure parts in `e2e_menu_action_crawler.py`, static tests in
`test_e2e_menu_action_adapter.py`). `open` names one screen per line of
`targets.jsonl` instead of walking the menu tree, and writes the same
`odoo-parity-evidence/v1` records `crawl` writes -- the same five signals of
parity plan section 7 step 5 and the same URL-literal checks (`U-C5`). The
existing `diff` then judged the two runs with no change.

```sh
set -a; . /projects/Woow_ha_odoo/.env; set +a; export ODOO_DB=odoo_parity
~/venvs/woow/bin/python odoo18ce/tests/e2e_menu_action_adapter.py open \
  --surface public     --targets targets.jsonl --out public-open.jsonl
~/venvs/woow/bin/python odoo18ce/tests/e2e_menu_action_adapter.py open \
  --surface ha_ingress --targets targets.jsonl --out ingress-open.jsonl
~/venvs/woow/bin/python odoo18ce/tests/e2e_menu_action_adapter.py diff \
  public-open.jsonl ingress-open.jsonl --out open-diff.jsonl
```

`ODOO_DB` is set in the shell because the `.env` of the main checkout points at
`odoo_test`, and both surfaces of this run must read `odoo_parity`. P-6 below
confirms both did.

| File | What it is |
|---|---|
| `targets.jsonl` | the seven screens, as `open` reads them |
| `public-open.jsonl` | the Public origin run, `WOOW-PARITY-20260929T071517Z` |
| `ingress-open.jsonl` | the Ingress run, `WOOW-PARITY-20260929T071649Z` |
| `open-diff.jsonl` | the two joined by `control_identity` and judged |

## P-Check

`e2e_parity_shared_layers_live.py pcheck --db odoo_parity`, 2026-09-29, all
PASS. P-5 is what decides which URL literals on the website pages are correct.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: same login on both surfaces, db `['odoo_parity', 'odoo_parity']` |

## Verdicts — `open-diff.jsonl`

Seven screens, both surfaces: **5 `PARITY` + 2 `GAP`**. Every screen loaded on
both surfaces; the two `GAP`s are signal and URL-literal differences, not a
missing screen.

| Module | Screen | Target | Verdict |
|---|---|---|---|
| `project_todo` | To-do kanban | `project_todo.project_task_action_todo` | `PARITY` |
| `project_todo` | To-do list | `/odoo/action-project_todo.project_task_action_todo?view_type=list` | `PARITY` |
| `project_todo` | To-do form (task 5) | `/odoo/action-project_todo.project_task_action_todo/5` | **`GAP`** (blocker) |
| `sale_management` | Quotation form, Optional Products tab | `/odoo/action-sale.action_quotations_with_onboarding/new` | `PARITY` |
| `sale_management` | Quotation Templates list | `sale_management.sale_order_template_action` | `PARITY` |
| `sale_management` | Quotation Template form | `/odoo/action-sale_management.sale_order_template_action/new` | `PARITY` |
| `ecpay_invoice_website` | Website checkout e-invoice step | `/shop/payment` | **`GAP`** (important) |

Per module: `project_todo` 2 `PARITY` + 1 `GAP`, `sale_management` 3 `PARITY`,
`ecpay_invoice_website` 1 `GAP`. All three now have a verdict of their own; the
#144 crawl had one skipped record for `project_todo` and none for the other two.

### How each module was reached

- **`project_todo`.** Its only menu (`project_todo.menu_todo_todos`) runs
  `project_task_preload_action_todo`, an `ir.actions.server`, which the
  read-only crawler skips. That server action ends with
  `action = env["ir.actions.actions"]._for_xml_id("project_todo.project_task_action_todo")`,
  so the run opened **that window action** directly and never ran the server
  action. Its kanban, list (`?view_type=list`) and form views are the three
  targets; the form is the one to-do the database holds for the test user
  (`project.task` 5, "Welcome Administrator!").
- **`sale_management`.** It does own a menu -- `sale_order_template_menu`,
  Sales > Configuration > Quotation Templates -- but the menu carries
  `groups="sale_management.group_sale_order_template"`, which the test user does
  not have, so it is not in the menu tree the crawler reads and #144 saw no
  `sale_management` menu at all. `sale.order.template` is readable by a Sales
  user regardless of that group, so the action opens by xmlid with nothing
  enabled and nothing written. The quotation form is opened as a new record
  (`/new`), and the `expect_selector` is the Optional Products notebook tab
  (`.o_notebook .nav-link[name='optional_products']`) -- the page
  `sale_management` adds to `sale.view_order_form`.
- **`ecpay_invoice_website`.** It inherits `website_sale.payment`, so what it
  adds -- 電子發票 / 紙本發票 / 捐贈 and the 使用載具 selector -- is on the
  checkout's **payment** step, `/shop/payment`, not on `/shop/checkout`. The
  `expect_selector` is the block it injects, `.ecpay-invoice-info-form`; it was
  present on both surfaces. Reaching that step needs a cart, which writes (see
  below). Nothing was paid: the payment and its callback are #146.

## Writes

Writes were made on **`odoo_parity` only**. `open` refuses to fill a cart on any
other database (`require_write_database`, `ODOO_DB` must be `odoo_parity`), and
the run confirmed P-6 (`odoo_parity` on both surfaces) before judging.

| Record | What changed | Why |
|---|---|---|
| `sale.order` id 2 (`S00002`, Administrator's website cart, state `draft`) | one line of `WOOW-PARITY-20260929T045315Z Service` per run: 11 -> 12 items on the Public run, 12 -> 13 on the Ingress run (the trial runs before them added the earlier units) | `/shop/payment` redirects to `/shop/cart` without a cart |
| `res.partner` id 3 (Administrator) | `street`, `city`, `zip`, `country_id` (Taiwan) and `phone` set, over JSON-RPC before the run | website_sale's `_check_addresses` redirects `/shop/payment` to `/shop/address` until the delivery address has every mandatory field (`name`, `street`, `city`, `country_id`, `phone`, and `zip` for Taiwan). The partner had none of them |

The cart write is **not** an `Operation` of the crawler's `OperationPolicy`, on
purpose: `NON_MUTATING_OPERATIONS` is every member of `Operation`, so a WRITE
member added there would be *permitted* by `READ_ONLY_POLICY` rather than
refused. It lives in `SurfaceDriver.fill_cart`, named, bounded by
`require_write_database`, and reported in the record's `writes` field. The
driver checks the navbar cart badge before and after, so a click that did not
reach `/shop/cart/update` fails the run instead of judging a checkout an older
cart had already made reachable.

No sale order was confirmed, no payment was made, no module setting and no
group was changed.

## The two `GAP`s

Neither has a GitHub issue yet: the process that produced this evidence may not
write on the tracker. The full text of both issues is in the Iteration's
`withheld-writes.md`, and the pull request asks for them to be filed; this table
is to be filled in with their numbers when they are.

| `GAP` | Issue |
|---|---|
| To-do form: the onboarding description's two images load from the Home Assistant root under Ingress (404) | (to file — `withheld-writes.md`) |
| Website pages: the frontend "Edit this content" link doubles the Ingress prefix (`/@` + a second prefix) | (to file — `withheld-writes.md`) |

### To-do form, `project.task` 5 — blocker

Ingress: `route_escape=2`, `http_4xx_5xx=2`, `console_error=2`; Public: all
zero. Both surfaces loaded the same screen (`project.task`, form,
`/odoo/action-454/5`) and the same eight URL literals. The two requests that
escaped are

```
<HA_BASE>/project_todo/static/img/todo_access.png    404
<HA_BASE>/project_todo/static/img/convert_todo.png   404
```

They come from the **to-do's own description**: `project_todo`'s
`todo_user_onboarding` template is copied into `project.task.description` when
the app first opens, and it carries
`<img src="/project_todo/static/img/todo_access.png">`. The HTML editor field
renders that stored HTML as markup, which is the path ADR 0004's 2026-09-28
postscript deliberately leaves **uncovered** by the Runtime shim -- a hook there
would write the token-bearing Ingress prefix back into the database when the
editor saves. So this is the same shape as #158 (survey help pictures) but *not*
the same fix: #158's route-scoped Literal rewrite is bound to
`/web/action/load`, an action record; a to-do description arrives on
`/web/dataset/call_kw/project.task/web_read`, which is record content and is the
exact case that decision refuses to rewrite. The issue says so, so nobody
reaches for the same hammer.

### Website checkout e-invoice step — important

Every signal is zero on both surfaces and the e-invoice block rendered on both.
The difference is one URL literal out of 45:

```
public : /@/shop/payment
ingress: <INGRESS_PREFIX>/@<INGRESS_PREFIX>/shop/payment
```

It is the `o_frontend_to_backend_edit_btn` ("Edit this content") link, Odoo 18's
`/@/<website path>` route into the web client. Under Ingress the prefix is put
on the link *and* on the website path inside it, so the second copy becomes part
of the path Odoo is asked to open -- the doubled prefix of `U-A2`. It is not
specific to the checkout: `/shop` shows the same literal, so it is on every
website page an editor can see. Nothing on this screen belongs to
`ecpay_invoice_website`; the target found it.

Neither `GAP` is a Structural gap: both are fixable in the add-on, and the
e-invoice step itself works under Ingress (the block renders, no signal, no
prefix escape), so acceptance criterion 4 of the issue lands on `GAP`, not on
"Ingress cannot do this in principle".

## Host state left behind

- `sale.order` `S00002` is still a draft cart with 13 items; nothing confirms it.
- `res.partner` 3 (Administrator) keeps the address and phone above.
- Nothing was installed, restarted or reconfigured.
