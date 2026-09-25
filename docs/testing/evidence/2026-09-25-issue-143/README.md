# Parity run: shared layers F, A, B, C, D (#143)

Run `WOOW-PARITY-20260925T043539Z` on 2026-09-25 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`**
(the 29 modules of #144). Driver: `odoo18ce/tests/e2e_parity_shared_layers_live.py`
(pure parts in `e2e_parity_shared_layers.py`, static tests in
`test_e2e_parity_shared_layers.py`).

- **Public side**: a top-level page on the Public origin.
- **Ingress side**: the add-on's panel in the Home Assistant frontend with
  Odoo in its iframe, over the **plain-http LAN** entrance; the frontend is
  signed in with the long-lived token. `U-C25` ran through the **https** HA
  entrance with Chromium's fake camera instead.
- Desktop Chrome at 1920x1080, plus the menu crawler at **390x844**.

## P-Check

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` 200 on the Public origin |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | **FAIL**: `website.domain` is empty. The bootstrap writes it only when `website` is installed at add-on start; `website` came later (#144). Left as found by the maintainer's decision; filed as #164. `U-D8` is the downstream GAP |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |
| P-7 | Created: partner, service product, quotation (and one for the test user, marked sent for `/my/quotes`), survey, event, job, Discuss channel, work center, task, a Unicode attachment, a low-rights user for `U-B7`; the test user joined the live chat channel. Every record is named with the run marker; nothing was deleted |
| P-8 | Writes on `odoo_parity` approved by the maintainer for this run (fixtures and what the checks create); no host, add-on or `odoo_test` change |

## Checks — `checks.jsonl`

One `odoo-parity-evidence/v1` record per check (item x screen), both
surfaces in one record. Every catalogued item of groups F, A, B, C, D ran
once on an ordinary screen (`generic`), plus the module screens the issue
lists (parity plan section 10).

**Conservation (parity plan section 12)**: 75 planned, 75 observed =
54 `PARITY` + 9 `GAP` + 1 `APPROVED-DIVERGENCE` + 5 `STRUCTURAL` + 6 `NOT-RUN`;
no check missing, duplicated or unclassified. The run does **not qualify** as
complete: six checks are `NOT-RUN` (below). Every `GAP` has an issue and every `STRUCTURAL` names its Public origin path; `conservation.json` is the report.
`python odoo18ce/tests/e2e_parity_shared_layers_live.py report <checks.jsonl>`
recomputes it.

Six records were rerun inside the same run after a harness fix, because
their first attempt gave the same wrong result on both surfaces (`U-C6`,
`U-C9`, `U-C17`, `U-F5` with `U-C18`/`U-C20`); each says so in its notes.

### GAP

| Check | What | Issue |
|---|---|---|
| `U-A1` generic | `/contactus`'s parallax background (inline `style="background-image:url('/web/image/…')"` in page HTML) loads from the HA root | #166 |
| `U-A6` generic | All seven injection ways tried escape under Ingress: `innerHTML` img, dynamic `<style>` url, CSS `@import`, `sendBeacon`, `EventSource`, SVG `<use xlink:href>` and `<use href>` | #169 |
| `U-B2` generic | The Public origin's `/websocket` handshake re-sets `session_id` without `Secure`/`SameSite` | #165 |
| `U-C23` generic | The survey Test button's new tab opens at `<HA_BASE><INGRESS_PREFIX>/survey/…`: the Ingress token is in the address | #168 |
| `U-C25` event registration desk | The desk's barcode error sound loads from the HA root | #159 |
| `U-D2` generic | The website editor's 36 snippet thumbnails (client-side `style` url) load from the HA root | #170 |
| `U-D6` generic, job application | After Contact Us or a job application is sent, the success page (`data-success-page`) opens at the HA root: 404 instead of the thank-you page | #167 |
| `U-D8` generic | Under Ingress, sitemap, canonical, `og:` and icon URLs are on `<HA_BASE>` (P-5) | #164 |

### STRUCTURAL (the Public origin path that carries it)

| Check | Carried by |
|---|---|
| `U-B3` generic: a copied address opens the HA panel's start screen, not the record | `<PUBLIC_BASE>/odoo/res.partner/<id>`, the screen's own Public address |
| `U-C27` generic: no service worker under Ingress (PWA install, offline page) | `<PUBLIC_BASE>/odoo` |
| `U-D7` `/`, `/shop`, `/jobs`: anonymous visitors get HA's 401 | `<PUBLIC_BASE>/`, `<PUBLIC_BASE>/shop`, `<PUBLIC_BASE>/jobs` |

`odoo18ce/DOCS.md` "What only the Public origin can do" already lists these;
its sidebar-address row now also says a copied address opens the panel's
start screen.

### APPROVED-DIVERGENCE

`U-B8` (AD-6): the Ingress prefix without an HA session answers 401 and shows
nothing of Odoo; the Public origin answers anonymously.

### NOT-RUN

| Check | Blocked by |
|---|---|
| `U-F5` POS receipt print, `U-C25` POS product scan | #161: POS hangs on its splash screen |
| `U-A9` generic | No server action on `odoo_parity` runs longer than 60 s |
| `U-C22` generic | Only `en_US` is active; the translation button needs a second language |
| `U-D6` event registration, `U-D7` `/event` | `website_event` is not among the 29 installed modules |

## Results worth knowing

- **`U-F1` capability list.** The Ingress iframe has **no `allow` and no
  `sandbox` attribute and is same-origin with Home Assistant**, so its
  feature policy grants clipboard-write, fullscreen, camera, microphone and
  downloads. The only limit is the insecure context of the plain-http
  entrance, which withholds clipboard-write, camera and microphone; on the
  https entrance `getUserMedia` is granted (`U-C25`), and over http the copy
  buttons work through the add-on's fallback (`U-C4`, both Share dialogs).
- **`U-F5` downloads** land inside the HA iframe: sale order PDF (its one
  link is on `<PUBLIC_BASE>`), xlsx export, attachment with a matching
  SHA-256.
- **`U-A8`/`U-F4` uploads**: Ingress accepted 100 MiB; the Public origin
  refused 100 MiB with 413 (the Cloudflare tunnel's 100 MB body limit), 10 MiB
  passed. 500 MiB was not tried for that reason.
- **`U-A4`**: `e2e_literal_rewrite_gate.py` against the Public origin's
  bundles exits 0 (no unregistered `FAIL`).
- **`U-A7`**: Ingress load of `/odoo` took 2.5x the Public origin's at worst
  (458 vs 273 ms cold, 465 vs 189 ms median warm), under the plan's 3x Minor
  line; a trial run earlier the same day, with single warm samples, measured
  3.1x, so the margin is thin. The Ingress bundle is gzip and `no-store`, the
  Public one brotli and `immutable`, by design (RC-5).
- **`U-B6`**: the HA tab was frozen for 960 s (past the Supervisor's 15-minute
  Ingress session life) and resumed; the Odoo screen came back without an
  authorization box.
- **`U-C26`**: `/websocket` answers 101 on both surfaces; a message posted on
  either surface shows on the other within a second. Live chat: an anonymous
  visitor on the Public origin reached the operator, who answered from each
  surface's Discuss.
- **`U-D5`**: the Share link produced under Ingress is on `<PUBLIC_BASE>` and
  opens for a browser with no session (task and quotation).
- **Found while building the harness**: the attendance kiosk page logs the
  current user out, and a live chat visitor's chat window stays open on the
  operator's screen across pages; the driver logs back in and closes chat
  windows before each check.

## Mobile layout — `crawl-diff-390x844.jsonl`

`e2e_menu_action_adapter.py crawl --viewport 390x844` (new option; records
carry `client: mobile-emulation-chrome-390x844`) on both surfaces for the 24
apps of #144, then `diff`. This is Chrome's mobile layout emulation, not a
phone or the Companion app.

299 menus = **281 `PARITY` + 4 `GAP` + 14 skipped** (server actions, as on
desktop). The four GAPs are the ones the desktop crawl of #144 found: the
survey sample pictures (#158, two menus), the Registration Desk sound (#159)
and the website visitors' page URLs (#160). The mobile layout added none.

Five apps (`contacts`, `crm`, `website`, `hr_recruitment`, `im_livechat`)
were crawled a second time, both surfaces back to back: the first crawl ran
while the shared-layer checks were creating partners, so the two surfaces saw
different avatar lists (7 false GAPs on URL literal sets). Their records here
come from the second crawl, which had none of those.

## Masking

URLs are base codes (`<PUBLIC_BASE>`, `<HA_BASE>`, `<HA_HTTPS_BASE>`,
`<INGRESS_PREFIX>`); query strings, access tokens in paths, the login,
password and HA token are redacted. The scan of these files for the hosts,
the token, the login and IP addresses found none.
