# The six Live checks #210, #211 and #160 left owed, on Release 0.4.9 (#235)

**Result: all six pass.** Both `GAP`s #163 recorded are gone, the visitor row a
page view through Ingress writes now carries the **Canonical URL**, and the
to-do the HTML editor saves under Ingress is still stored root-relative.

Run on 2026-10-01 against the test host's Released add-on `1b7b4ce7_odoo18ce` at
**0.4.9**, database **`odoo_parity`** (the 29 modules of #144), which is the
add-on's `default_db`, so the Public origin serves it. `odoo_test` was not
touched.

Each of #210, #211 and #160 shipped with a Static-tier contract and left two
Live acceptance boxes its own Iteration could not tick — six in all, every one
of them resting on a **Release** that carries the three fixes and a **Deploy**
of it. Nothing open was tracking them; #235 is that register. The precedent is
#201, which batched the six owed reruns of the 2026-09-28 sweep onto one
Release.

| File | What it is |
|---|---|
| `public-open.jsonl` | the #163 target file on the Public origin, `WOOW-PARITY-20261001T070918Z` |
| `ingress-open.jsonl` | the same seven targets through Ingress, `WOOW-PARITY-20261001T071125Z` |
| `open-diff.jsonl` | the two joined by `control_identity` and judged |
| `public-crawl.jsonl` | `crawl --apps website` on the Public origin, `WOOW-PARITY-20261001T071432Z` |
| `ingress-crawl.jsonl` | `crawl --apps website` through Ingress, `WOOW-PARITY-20261001T072116Z` |
| `crawl-diff.jsonl` | the two joined and judged |
| `hand-checks.jsonl` | the three actions with no adapter subcommand, on 0.4.9 |
| `host-readings.jsonl` | the three readings those actions are **judged by**, taken on the host afterwards: the base URL, the newest `website.track` rows, and `project.task.description` after the save |
| `baseline-0.4.6-hand-checks.jsonl` | the same two hand-driven readings taken on **0.4.6**, before the Deploy. **Measured by the first version of the driver**, whose `route_escape` field missed a doubled prefix (see "The instrument was corrected mid-run"); its `http_4xx_5xx` row carries the escape that field omitted |
| `website-track-cleared.jsonl` | the 88 `website.track` rows Step 2 cleared, exported before they were deleted |

Drivers:

    e2e_parity_shared_layers_live.py pcheck
    e2e_menu_action_adapter.py       open / crawl / diff
    e2e_ingress_hand_checks.py       visit / editbtn / todosave   (new here)

`e2e_ingress_hand_checks.py` is new. Two of the six checks are a click and a
save, and a third's result is in a database row rather than on a screen, so no
`open` or `crawl` target reaches them. It borrows the adapter's own
`SurfaceDriver`, so the Ingress session, the database reading and the `Masker`
that hides credentials and origins are the same ones every other record here
was written with, and it judges a **Prefix escape** with the adapter's own
`is_prefix_escape` rather than a second opinion. Its pure parts are tested at
the Static tier, `tests/test_e2e_ingress_hand_checks.py`.

`conservation.json` and `reconciled.jsonl`, which `docs/agents/live-tier.md`
names, are not here: this run drove `open`, `crawl` and the three actions, not
`e2e_parity_shared_layers_live.py run`/`report`, so there is no planned set to
reconcile against. §10.6 of the parity plan records why the 76-item
conservation set does not move.

### The instrument was corrected mid-run

A review of this branch found the first version of the driver judging a
**Prefix escape** by asking whether a request reached the Home Assistant origin
*outside* the prefix. That answer is "no" for the one shape #211 is about: a
doubled prefix is still under the prefix. The 0.4.6 baseline record shows the
miss — `route_escape: []` beside `http_4xx_5xx: ["HTTP404 <INGRESS_BASE><INGRESS_PREFIX>"]`,
which is a `U-A2` escape the field did not count.

So the helper now calls `adapter.is_prefix_escape`, a Static-tier test pins the
doubled-prefix case against it, and **the three 0.4.9 actions were run again on
the corrected driver** — `hand-checks.jsonl` holds those runs
(`WOOW-PARITY-20261001T0745…`), not the first ones. The zeros in them are
therefore zeros the adapter would also report. The 0.4.6 baseline cannot be
re-measured, because the host is no longer on 0.4.6; it is kept as it was
recorded, with the caveat above, and nothing in it is load-bearing — what makes
check 3 a pass is the 0.4.9 record, and the doubled literal on `/shop/payment`
is #163's own record on 0.4.5.

The Issue's command block says `--surface ingress`; the adapter's two choices
are `public` and `ha_ingress`, and `ha_ingress` is what ran. `IGNORE_HTTPS_ERRORS`
is absent from the `.env`; the adapter documents it as optional and defaults it
to `0`, so it is not the missing-name stop `docs/agents/live-tier.md` describes.

## Step 0 — the Release and the Deploy

No Release carried the three fixes: all three said "no version bump", the newest
Release was **0.4.8**, and the host was on **0.4.6**. So 0.4.9 was cut the way
#200 and #222 cut theirs — the version in `odoo18ce/config.yaml`, the CHANGELOG's
Unreleased section dated — as PR **#245**, merged to `main` as `98cef60`.
`release.yml` published `ghcr.io/woowtech/woow-ha-odoo-{amd64,aarch64}:0.4.9`,
the tag `v0.4.9` and the GitHub Release, and dispatched the **Sync**; the
**App Store mirror** carries 0.4.9.

The branch was rebased before merging: #156 (PR #246), #226's follow-up
(PR #248) and **#238 (PR #249)** landed on `main` while 0.4.9 was in CI. So
0.4.9 also carries #237's and #238's fixes, and #238 adds 182 lines of
**Literal rewrite** to the nginx template. Two consequences for this run, both
recorded rather than assumed: the seven-target `open` run is the first Live-tier
sighting of those rules, and nothing in it moved (see "A rule that fires where
it should not" below).

| | |
|---|---|
| Deploy | `ssh ha 'ha apps update 1b7b4ce7_odoo18ce'`, exit 0 |
| Supervisor cache | it reported `version_latest: 0.4.8` until `ha store reload`; after it, `0.4.9`. The **Sync** had already landed, so what was stale was the Supervisor's own copy of the **App Store mirror** |
| After | `version: 0.4.9`, `version_latest: 0.4.9`, `state: started`, `update_available: false` — **read before the first check** |
| Slow link | not needed. The ~380 MiB of the 0.4.7 Odoo bump came down in one go; `docs/runbooks/slow-link-pull.sh` (#153/#157) was not used |

## Step 1 — the base URL, read before anything was judged

The Issue makes this mandatory and says why: #160's fix builds the stored URL
from `website.get_base_url()` and the request's path, so a base that is already
the Home Assistant host would make `tracked_url` return the address the request
arrived on, `dispatch_on_the_canonical_url` would take its `stored == arrived`
early return, and **nothing would be logged at all**. That failure is silent,
and a `GAP` on action 596 would look like the fix not working.

Read with `odoo shell` on the add-on's own container, against `odoo_parity`,
**on 0.4.9 and again before the Deploy on 0.4.6**. Identical both times. The
0.4.9 reading is the first record of `host-readings.jsonl`; the 0.4.6 one was
taken and classified the same way before the Deploy, and its raw capture was
not kept — nothing rests on it, since what the checks are judged against is the
base as 0.4.9 serves it.

| Reading | 0.4.6 (before the Deploy) | 0.4.9 |
|---|---|---|
| the default website's `domain` (id 1, "My Website") | `<PUBLIC_BASE>` | `<PUBLIC_BASE>` |
| the `web.base.url` system parameter | `<PUBLIC_BASE>` | `<PUBLIC_BASE>` |
| `website.get_base_url()` | `<PUBLIC_BASE>` | `<PUBLIC_BASE>` |
| `web.base.url.freeze` | `True` | `True` |

**None is the Home Assistant host**, so the stop the Issue describes does not
apply and the six checks are judgeable. `woow_base_url_guard` is holding, which
is what the Issue expected but nothing had read on the host.

`pcheck --db odoo_parity`, taken after the Deploy, agrees — all six PASS:

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: same login on both surfaces, db `['odoo_parity', 'odoo_parity']` |

## Step 2 — the stale `website.track` rows: **cleared**

The Issue names rows `226`, `227`, `239`–`243` and asks for a decision before
the run: clear them, or take the action 596 judgement outside them. **They were
cleared** — and there were far more of them than the Issue knew.

Reading every `website.track` row first: **255 rows, of which 88 carried the
Home Assistant host**, from `9` (2026-09-24) to `253`. The Issue's seven are a
subset; `236`–`238` were left by the same 2026-09-30 rerun and are not in its
list, and the other 78 go back to #144's and #143's runs. Clearing only the
seven would have left action 596 a `GAP` on rows nobody was tracking, which
would have read as the fix not working.

Excluding them from the judgement was the other option and was rejected: the
rows are *on the screen* action 596 opens, so there is no way to judge that
screen with them in the database.

What was deleted is every row whose url names a host other than the Canonical
URL — the host to delete is not hard-coded, it is read from the website itself.
A row with no url at all names no host and was left alone (19 of those remain).

| | |
|---|---|
| Cleared | **88** rows: `9`–`16`, `22`, `23`, `33`–`37`, `40`, `43`, `44`, `46`, `48`, `51`, `54`, `56`, `58`, `62`, `64`, `66`, `69`, `70`, `72`–`79`, `81`, `84`, `85`, `89`, `92`, `93`, `97`, `99`, `101`, `104`, `113`–`120`, `122`, `124`, `126`, `128`, `129`, `131`, `133`, `141`, `143`, `151`, `157`, `191`, `193`, `202`, `203`, `206`, `207`, `209`, `211`, `216`, `220`, `226`, `227`, `236`–`243`, `252`, `253` |
| Exported first | `website-track-cleared.jsonl`, one row per line, origins masked |
| Remaining | 167 rows immediately after the clearing, none of them on the Home Assistant host |
| `252` and `253` | written by this run's own two **0.4.6** baseline readings below, before the Deploy; they carried the Home Assistant host like every other Ingress page view on 0.4.6 |

#160's decision not to **rewrite** old rows is untouched: nothing was rewritten.

## The readings taken on 0.4.6, before the Deploy

Two of the six checks are a before-and-after, so both were read on 0.4.6 first —
`baseline-0.4.6-hand-checks.jsonl`. They are what makes the 0.4.9 readings
decisive rather than merely clean:

| Reading | 0.4.6 | 0.4.9 |
|---|---|---|
| the "Edit this content" `href` | `<INGRESS_PREFIX>/@<INGRESS_PREFIX>/` (read on the website home — the link is on every editable page, and #163 recorded the same shape on `/shop/payment` on 0.4.5) | `<INGRESS_PREFIX>/@/shop/payment` |
| following it | HTTP 404 on `<INGRESS_BASE><INGRESS_PREFIX>`, the editor left on its fallback frame | the page opens, no 404 |
| the To-do form's two pictures, `src` in the DOM | `/project_todo/static/img/…` — no prefix | `<INGRESS_PREFIX>/project_todo/static/img/…` |
| did they load | `[false, false]`, two HTTP 404s on the Home Assistant root | `[true, true]`, no failed request |

## The six checks

| # | From | Verdict |
|---|---|---|
| 1 | #210 | **PASS**. The To-do form (`project.task` 5, the third `project_todo` line of `targets.jsonl`) reads `route_escape=0`, `http_4xx_5xx=0`, `console_error=0`, `pageerror=0`, `failed_requests=0` on **both** surfaces, and the two pictures carry the prefix under Ingress (`<INGRESS_PREFIX>/project_todo/static/img/todo_access.png`, `…/convert_todo.png`) against the same two root-relative literals on the Public origin. `open-diff.jsonl`: `PARITY`. On 0.4.6 this screen was the blocker `GAP` with `route_escape=2` |
| 2 | #210 | **PASS**. The description was edited in the HTML editor under Ingress and saved (`hand-checks.jsonl`: `save_button` true, `unsaved_after_save` false, every signal empty). The stored value is the third record of `host-readings.jsonl`: `every_src_root_relative` **true** for both `/project_todo/static/img/…`, `marker_present` **true** and the marker names this run (`WOOW-PARITY-20261001T074630Z`, so the save really wrote), `holds_hassio_ingress` **false**, `absolute_src_or_href` **0**. Single-session only; the two-session peer-snapshot path is #234 |
| 3 | #211 | **PASS**. Under Ingress the link reads `<INGRESS_PREFIX>/@/shop/payment`, and **following it opens the page in the web client**: the browser lands on route `/shop/payment` with the main navbar, and the editor's second preview frame is the real page — route `/shop/payment`, title "Shop - Select Payment Method \| My Website", with `ecpay_invoice_website`'s own `.ecpay-invoice-info-form` block in it. No 404, no console error, no prefix escape |
| 4 | #211 | **PASS**. `/shop/payment` is `PARITY` in `open-diff.jsonl`, and the Ingress record's `url_literals` carries exactly `<INGRESS_PREFIX>/@/shop/payment` against `<PUBLIC_BASE>/@/shop/payment` on the Public origin. The doubled literal this replaces — `<INGRESS_PREFIX>/@<INGRESS_PREFIX>/shop/payment` — is #163's own record on 0.4.5 (`docs/testing/evidence/2026-09-29-issue-163/open-diff.jsonl`); this run's 0.4.6 baseline read the same defect on the website home, as `<INGRESS_PREFIX>/@<INGRESS_PREFIX>/` |
| 5 | #160 | **PASS**. One website page view through Ingress (`/`, `WOOW-PARITY-20261001T074553Z`, 07:45:53) wrote `website.track` row **275**, and the second record of `host-readings.jsonl` reads that row back: url `<PUBLIC_BASE>/`, `host_is_the_canonical_url` **true**. Not the Home Assistant host, and not a bare path — a bare path would mean the base read in Step 1 was empty. Of the 187 rows then on the host, 167 are on the Canonical URL and the other 20 hold no url at all |
| 6 | #160 | **PASS**. `crawl`/`diff` over `website` reports `PARITY` for `menu:website.menu_visitor_view_menu\|ir.actions.act_window:596`, severity `none`, no `url_violations` on either surface. Every visitor URL on that screen now reads `<PUBLIC_BASE>` — including the four that used to read `<HA_BASE>`: `/`, `/contactus`, `/jobs/…job-3`, `/shop/…service-58` |

Both diffs in full:

    open-diff.jsonl    7 judged = 7 PARITY + 0 GAP;  0 skipped
    crawl-diff.jsonl  30 judged = 30 PARITY + 0 GAP; 1 skipped

The one skipped crawl entry is `menu:website.menu_website_analytics|ir.actions.server:587`, skipped by the read-only rule because a server action may write — the same entry every earlier website crawl skipped.

### What the add-on's own log says

The Issue's warning was that #160 could fail silently. It did not; the module
said so from the inside, in `/data/odoo/logs/odoo-server.log`:

- **24** lines of `website.visitor._handle_webpage_dispatch patched: a page view records the Canonical URL`, one per worker, the newest at 07:06 — the 0.4.9 start.
- **0** lines of `the request's url could not be replaced` after the Deploy. The 12 in the file are all from 05:37–05:38, which is this run's own 0.4.6 baseline readings, and they name the same cause the #160 **Correction** did.
- **0** lines of `could not be put back`, ever. The restore half of the swap has never refused.

### A rule that fires where it should not

The Issue asks for the whole target file rather than the three lines the checks
name, because a **Literal rewrite** that fires on the wrong page shows up as a
changed literal on an unrelated target. Nothing moved: the four targets no check
names — the To-do kanban and list, and `sale_management`'s three screens — are
`PARITY` with the same literals on both surfaces, and every one of the seven
reported `0` on all five signals on both surfaces. That covers #238's 182 new
template lines too, which this Release is the first to deploy.

## Writes

All on `odoo_parity`. `open` refuses to fill a cart unless the session it has
just logged into reports that database (`require_write_database`), and P-6
confirms both surfaces are on it.

| Record | What changed | Why |
|---|---|---|
| `res.partner` 3 (Administrator) | `street`, `city`, `zip`, `country_id` (Taiwan) and `phone` set, over `odoo shell` before the run | `website_sale`'s `_check_addresses` redirects `/shop/payment` to `/shop/address` until the delivery address has every mandatory field. #163 set the same five for the same reason and cleaned them on 2026-09-30, so the target was unreachable again |
| `sale.order` 2 (`S00002`, the Administrator's draft website cart) | the **Public** run added one line of `WOOW-PARITY-20260929T045315Z Service` (0 -> 1 items); the **Ingress** run added nothing, as `ensure_cart` leaves a cart that already holds something alone | `/shop/payment` redirects to `/shop/cart` without a cart, and a cart of a different size on each surface would make the page's own content differ. Both records carry the write |
| `website.track` | 88 rows deleted (Step 2); 19 new rows written by the runs' page views, among them row 258 from the Ingress page view check 5 reads | Step 2's decision; the new rows are the page views the checks are made of |
| `project.task` 5 (`description`) | the HTML editor saved it under Ingress with a run marker appended, then it was **restored** to the exact value the run found (sha `c081911c…` before and after) | Check 2 is a save. The reading that judges it was taken while the marker was stored, and is above |

Nothing was confirmed, no payment was made, no module, setting or group was
changed, and no fixture was created.

## What this run does **not** say

- **The `/shop/payment` GET write is still unreported.** `/shop/payment` is on `GET_WRITING_ROUTES` ("stores a shop_warning on the cart") and #224 — still open — is the issue that makes such a write appear in the record's `writes` field. Until it lands, `_judge` compares `none` against `none` for that write, so check 4's `PARITY` is a verdict on the screen and its literals, not on what the GET wrote. #243's run, which is written to come after #224, is where that is measured. #228 landed later the same day (PR #252) and classifies `/shop/payment` as **convergent**, so the target this run used is one that rule still allows and the run is reproducible on the adapter as it now stands.
- **The two-session peer-snapshot path is untouched.** Check 2 is single-session. #234 is the other one; it closed on the Static tier later the same day (PR #251) and left `e2e_collab_peer_snapshot_live.py` behind unrun, with its Live measurement registered to #243.
- **#237's and #238's own Live boxes are not ticked here.** Both fixes are in this image, but their checks belong to #243's register and nothing in #235's six overlaps them: #210's checks are the **editable** html field, #237's are the readonly one, #238's are the legacy editor.

## What the run left on the host

- **The add-on is on 0.4.9**, `started`. The Supervisor's store was reloaded once (`ha store reload`) so it could see the Release.
- **`res.partner` 3 keeps the address and phone above.** They are what `/shop/payment` needs, and the next run of this target needs them too; #163 cleared them and that is why this run had to set them again.
- **`sale.order` `S00002` is a draft cart holding one line** (1 item) of `WOOW-PARITY-20260929T045315Z Service`. Nothing confirms it.
- **`website.track` holds 186 rows at the end of the run** — 166 on the Canonical URL and 20 with no url at all, and **none on the Home Assistant host**; the 88 deleted ones are in `website-track-cleared.jsonl`. `website.visitor` rows were not touched, so a visitor whose only page views were deleted now lists none.
- **`project.task` 5 is back to the description the run found**, byte for byte.
- Nothing was installed or reconfigured, and the add-on was not restarted beyond the Deploy's own restart.
