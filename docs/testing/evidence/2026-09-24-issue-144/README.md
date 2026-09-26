# Parity run: 29 modules installed through Ingress (#144)

Run on 2026-09-24 against the test host's Released add-on `1b7b4ce7_odoo18ce`
at **0.4.4**, on a fresh database `odoo_parity` set as `default_db` so the
**Public origin** serves it. `odoo_test` was not touched.

## Setup

| Step | Result |
|---|---|
| Deploy 0.4.4 | Done by the issue-141 session at 16:17 host time (two ghcr pulls failed first, #153); start-time self-check passed |
| `odoo_parity` | Created in the container with `db._create_empty_database` + `db._initialize_db` (no demo, `en_US`, country TW), then `default_db: odoo_parity` and a restart. Bootstrap froze `web.base.url` to the Public origin (P-3, P-4 pass) |
| ECPay | `ecpay_invoice_tw`, `ecpay_invoice_website`, `payment_ecpay`, `payment_ecpay_ecpg` copied to `/share/odoo_addons/` from **WOOWTECH/ecpay_odoo18 `56cb04c36d455ae76d3d78a33602c2bf322a2c8f`** (the commit is also in `/share/odoo_addons/ECPAY_COMMIT` on the host) |

**Create the database with the add-on's own config.** The first attempt used
`/etc/odoo/odoo.conf`, whose `data_dir` is not under `/data`; the add-on runs
with `/data/odoo.conf`. The 12 attachments written by `base` at init went to a
non-persistent directory and were gone after the restart, so the company
partner's image answered 500 on both surfaces. They were rewritten from their
module files with `odoo shell -c /data/odoo.conf`. Crawl groups 1 and 2 ran
before the repair and had no signal; every later group ran after it.

## Installs — `install.jsonl`

One record per module, in dependency order (`odoo18ce/tests/e2e_ingress_install.py`):
Activate pressed on the module's form in the Apps screen under the Ingress
prefix, then the next **Rewrite scan** round read from the add-on log and the
new Rewrite scan notifications read over the HA websocket.

- All 29 are `installed` through Ingress. 25 by their own Activate; `mail`,
  `hr_skills`, `project_todo` came in with `contacts`, `hr`, `project`
  ("already installed" records); `mrp` was activated by a run the PC stopped
  for low memory, and its round was read from the log afterwards (`note`).
- Every install has a scan round within 5 minutes (152–290 s), each
  `unchanged` or `up to date`: no **Generated rewrite** was added and no
  notification was raised (handoff #10).
- `rewrite-scan-final-round.txt` is the full round after the last install:
  34 bundles, **FAIL 0**, WARN 37, INFO 486.
- The records are appended run by run, so a module listed in two runs has
  two records (`contacts`: installed, then "already installed"; `mrp`:
  "already installed" in the resumed run, then the round read from the log).
- The recorded round is the first one logged after the module showed as
  installed (polled every 15 s). It can have started a few seconds before
  the install ended; the next round, five minutes later, would then be the
  first to read the new bundles. Every later round was `up to date` or
  `unchanged` too, and the final round above covers all 29 modules.
- These records predate `problems` (added after review); the driver now
  fails an install whose round is late, unhealthy, or adds rules without a
  notification.

## Crawl and diff — `crawl-diff.jsonl`

`e2e_menu_action_adapter.py crawl` on both surfaces for the 24 top-level apps,
in groups (the PC was short of memory), then `diff` per group, merged here.
The crawl ran once after all 29 installs, not after each install: a crawl
during installs would race Odoo's registry reloads.

- 290 menus = **272 PARITY + 4 GAP + 14 skipped** (not read-only actions).
- Per owning module (the menu xmlid's module): every module has `PARITY`
  only, except `survey` (2 GAP, one action), `event` (1), `website` (1).
- Modules with no menu of their own are covered through the menus they add
  (`website_sale` 15, `ecpay_invoice_tw` 1, `payment_ecpay` 1) or through
  their parent app (`sale_management` → `sale`, `ecpay_invoice_website` →
  `website`, `payment_ecpay_ecpg` → `account`).
- `project_todo`'s one menu is a server action, skipped by the read-only
  rule, so it has no judged screen.
- `url_literals` keep public third-party links as they are (Odoo
  documentation, Google Cloud console, sample `http://sampleN.com`); they
  do not identify the host under test. Host URLs are masked to base codes
  and every query string to `<redacted>`.
- Two crawler false positives were fixed during the run (in this PR): sample
  records of an empty view show avatars picked at random, and a wizard
  action opens in a dialog. See the commit message.

| GAP | Issue |
|---|---|
| Survey sample pictures in the action help escape the Ingress prefix (RC-12, `innerHTML`) | #158 |
| Event Registration Desk barcode sound escapes the Ingress prefix (`new Audio(url(...))`) | #159 |
| Website visitor page views opened through Ingress store the HA root as their URL (`U-C5`, RC-9) | #160 |

## POS offline (`U-C27`, ADR 0011) — #161

Odoo 18 CE's POS has no service worker, so `/pos/ui` does not reload offline
on the Public origin either. With the page loaded, cutting the network shows
"Connection Lost … limited functionality" and the till stays usable on the
Public origin. The full offline sale and sync was not finished: the POS then
hung on its splash screen on both surfaces. #161 holds the rest.

Done on 2026-09-26: the offline sale synced and the offline reload failed on both
surfaces, both `PARITY`. See `../2026-09-26-issue-161/`.

## Must-run U items owned elsewhere

`U-E2`/`U-E3`/`U-E4` outbound URLs → #145; `U-E6` ECPay callback → #146;
`U-F1`, `U-C24`, `U-C25`, `U-C26`, `U-F5`, `U-D1`–`U-D6`, `U-B2` and the
mobile viewport → #143. Parity plan section 10.4 maps each module to these.
