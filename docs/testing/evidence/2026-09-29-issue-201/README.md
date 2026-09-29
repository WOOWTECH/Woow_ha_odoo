# The six Live reruns the 2026-09-28 sweep owed, on Release 0.4.5 (#201)

Run `WOOW-PARITY-20260929T040919Z` on 2026-09-29 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.5**, database **`odoo_parity`**
(the 29 modules of #144). Each check verifies a fix that shipped in the
2026-09-28 sweep (PRs #192–#199) and whose Live acceptance box the sweep could
not tick — the sweep had sibling worktrees on the checkout, and the two-surface
verdicts need a Release the store can serve, which did not exist until 0.4.5
(PR #200). Drivers:

    e2e_parity_shared_layers_live.py run --only U-A1,U-A6,U-B2,U-D2,U-D6
    e2e_parity_outbound_live.py       run --only U-E4

## Deploy

0.4.5 was published by `release.yml` on the merge of PR #200 (`v0.4.5`,
`ghcr.io/woowtech/woow-ha-odoo-{amd64,aarch64}:0.4.5`). The Supervisor's own
`ha apps update` failed on this host's slow link with `unexpected EOF` — the
#153 symptom — so the image was placed with the resumable puller #157 shipped:
`docs/runbooks/slow-link-pull.sh` (taken from the `v0.4.5` tag, sha256 matched
against the repo), which downloaded the 759 MB image over ~40 min of a flaky
link and passed its gate (loaded image ID = the manifest's config digest).
`ha apps update` then completed against the local image and the add-on reports
`0.4.5`, `started`. A cold backup `before-0.4.5` was taken first.

The rendered nginx config on the running container carries both `browser.location`
rewrites from #174 (lines 504–505 of the template), `$safe_ingress_path`
substituted.

## P-Check

`pcheck --db odoo_parity`, 2026-09-29, all PASS.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `<PUBLIC_BASE>` |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |

## Checks

Shared-layer set — `checks.jsonl`. Every re-run item that was a `GAP` in the
last full run (#183, `WOOW-PARITY-20260925T043539Z` / #143) is now `PARITY`.

| Control identity | Fix | Verdict |
|---|---|---|
| `check:U-A1\|shared\|generic` | #166 (PR #194) | **`PARITY`** — no route escape; entity-quoted inline-style backgrounds carry the prefix |
| `check:U-A6\|shared\|generic` | #169 (PR #192) | **`PARITY`** — covered ways (`sendBeacon`, `EventSource`, the three `<use>` reference settings) do not escape; the escapes listed (`css-import`, `innerHTML-img`, `insertAdjacentHTML-use`, `style-attr`, `style-url`) are the accepted ways, recorded `PARITY` with their screen issues in the notes |
| `check:U-B2\|shared\|generic` | #165 (PR #195) | **`PARITY`** — Public `session_id` reads `Secure=True, SameSite=Lax, Path=/, HttpOnly` after the bus socket opened (was `GAP`/RC-4); Ingress unchanged (`Path=<prefix>/, SameSite=Lax`, not `Secure` over plain http) |
| `check:U-B2\|website_sale\|/shop/cart` | #165 | **`PARITY`** — cart kept after reload on both surfaces |
| `check:U-D2\|shared\|generic` | #170 (PR #198) | **`PARITY`** — editor opens, `AssetsLoadingError 0`, `route_escape 0`; snippet thumbnails carry the prefix |
| `check:U-D6\|shared\|generic` | #167 (PR #197) | **`PARITY`** — form submitted, thank-you page shown (not HA's 404) |
| `check:U-D6\|hr_recruitment\|job application` | #167 | **`PARITY`** — applied, thank-you shown |
| `check:U-D6\|survey\|survey fill` | #167 | **`PARITY`** — submitted, thank-you shown |
| `check:U-D6\|event\|event registration` | — | `NOT-RUN` — `odoo_parity` has `event` but not `website_event`, so there is no front-end registration form (unchanged) |

Outbound set — `outbound.jsonl` (`U-E4`, #174, PR #199):

| Control identity | Verdict |
|---|---|
| `check:U-E4\|event\|event ticket PDF` | **`PARITY`** — one QR each, no URL in the QR, `route_escape 0`; the gear-menu Download/Print path (`ActionMenus.onItemSelected` → `browser.location`) obtains the PDF identically on both surfaces |
| `check:U-E4\|account\|invoice PDF` | `NOT-RUN` — the PDF **downloads on both surfaces with `route_escape 0`** (before #174 the Ingress frame navigated to the HA root and no download fired); the verdict is `NOT-RUN` only on U-E4's QR-content axis, which is blocked because a Taiwan Odoo CE company has no QR payment method (`#146`) |
| `check:U-E4\|account\|invoice PDF without Payment` | `NOT-RUN` — same block; this is the `/report/` path, which the Download > PDF action does not take |

The RC-1 escape #174 fixed (Action menu > Download > PDF navigating the Ingress
frame to the HA root) is gone: the invoice PDF is obtained under Ingress with no
route escape, and the event-ticket row confirms the download-via-`location` path
end to end. The `target: self` branch (`browser.location.assign`, template line
505) is deployed in the running config; the `browser.location=item.url` branch
(line 504) is exercised by the downloads above.

## Conservation (parity plan section 12) — `reconciled.jsonl`

`reconciled.jsonl` is #183's reconciled set (76 records) with this run's eleven
shared-layer records substituted for the ones the prior run wrote.
`conservation.json` is `report` over it:

    76 observed = 60 PARITY + 1 GAP + 2 APPROVED-DIVERGENCE + 6 STRUCTURAL + 7 NOT-RUN

Balanced, no record missing, unplanned, duplicated or unclassified; no
`gap_without_issue`, no `structural_without_path`. The one remaining `GAP` is
`U-C25` (`event registration desk`, citing **#159**) — the registration-desk
media-source path, which was **not in #201's scope** (U-A1/A6/B2/D2/D6/E4) and
whose Live rerun and the owed `U-A6` media-way probe remain follow-up work. The
six `GAP`s that cited #165–#167, #169, #170 are gone, now `PARITY`.

`report` exits 1 for the same reason #143/#172/#183 did — the same seven
`NOT-RUN` checks, each blocked outside the add-on. Nothing in this run changes
that. As with #172/#183, this file only shows the report reconciles; the parity
plan's section 10.6 carries the numbers above.

## What the run left on the host

Both `fixtures` steps write, so records were left behind, all named with the run
marker `WOOW-PARITY-20260929T040919Z`:

- **Shared P-7 fixtures**: `res.partner` 65, `product.template` 57, `sale.order`
  25 and 26, `survey.survey` 4, `event.event` 4, `hr.job` 3, `discuss.channel`
  13, `mrp.workcenter` 3, `project.task` 8, `ir.attachment` 1371.
- **Outbound fixtures**: customer 66, `sale.order` 27, `account.move` (posted
  invoice) 16, `purchase.order` 2, plus the per-surface mail/leave/expense
  records the outbound plan builds; the capture mail server (`ir.mail_server` 2)
  is left active — archive with `e2e_parity_outbound_live.py teardown` if a
  later run needs it off.
- Two pre-existing leftovers from the #145 outbound run blocked `fixtures` until
  the fixture was made idempotent on the true uniqueness keys (see the commit):
  a `link.tracker` on `/contactus` (unique key is the URL, not the title) and an
  `hr.employee` for a reused `res.users` (one employee per user per company).

`e2e_parity_outbound_live.py` gained no `active` field on `link.tracker` cleanup;
nothing was deleted — the fixtures now reuse the prior records.
