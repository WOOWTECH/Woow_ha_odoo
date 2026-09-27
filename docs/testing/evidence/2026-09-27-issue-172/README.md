# `U-D8` split into head links and the sitemap (#172)

Run `WOOW-PARITY-20260927T101656Z` on 2026-09-27 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`**
(the 29 modules of #144). Driver:
`odoo18ce/tests/e2e_parity_shared_layers_live.py run --only U-D8`
(pure decisions in `e2e_parity_shared_layers.py`, static tests in
`test_e2e_parity_shared_layers.py`). Read-only: two HTTP GETs per surface
and the home page; no record was created or changed.

The maintainer accepted the divergence (#172 comment, 2026-09-25): Odoo
builds `/sitemap.xml` from the request's URL root, so the copy served
through Ingress lists the Home Assistant address. It is now **`AD-8`** in
the parity plan's section 3 whitelist, and `U-D8` is recorded as two checks
instead of one.

## P-Check

`pcheck --db odoo_parity`, 2026-09-27, all PASS — P-5 (`website.domain` =
`<PUBLIC_BASE>`) is what the head links are built from, and what makes
Ingress's `robots.txt` say `Disallow: /`.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `<PUBLIC_BASE>` |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |

## Checks — `checks.jsonl`

| Control identity | Verdict | Public | Ingress |
|---|---|---|---|
| `check:U-D8\|shared\|generic` | **`PARITY`** | all SEO URLs on `<PUBLIC_BASE>` | all SEO URLs on `<PUBLIC_BASE>` |
| `check:U-D8\|website\|sitemap.xml` | **`APPROVED-DIVERGENCE`** (severity `none`, `AD-8`) | sitemap URLs on `<PUBLIC_BASE>` | sitemap URLs on `<HA_BASE>` |

- **Head links and `robots.txt`** (`generic`): the home page's `canonical`,
  `alternate`, `og:url`, `og:image`, `twitter:image` and icon links plus
  `robots.txt`, on both surfaces, every base `<PUBLIC_BASE>`. This is the
  half #164's catch-up and the restart workaround closed; the record's
  `by_source` says which source each base came from.
- **`sitemap.xml`** (`website`): `AD-8` verified in reverse, all four
  statements held — Ingress's `robots.txt` carries `Disallow: /` **and**
  `Sitemap: <PUBLIC_BASE>/sitemap.xml`, Ingress's sitemap is on `<HA_BASE>`
  (14 URLs, the same pages as the Public copy), and the Public origin's
  sitemap is on `<PUBLIC_BASE>` (14 URLs). The Public origin's `robots.txt`
  has no `Disallow`, as `AD-8` says. Any of the four failing is a `GAP`,
  including the divergence disappearing and an empty `website.domain`
  (P-5 failing), which takes `Disallow: /` away and leaves nothing steering
  crawlers off the Ingress copy. That direction is covered in the static
  tier (`SeoOutputTests`), not by this run.

## Conservation (parity plan section 12) — `reconciled.jsonl`

The planned set now holds both `U-D8` records, so a run's `checks.jsonl`
must carry both. `reconciled.jsonl` is #143's `checks.jsonl` with this run's
two records substituted for its single `U-D8` record (76 records against 76
planned checks); `conservation.json` is the `report` over it:

    76 observed = 54 PARITY + 8 GAP + 2 APPROVED-DIVERGENCE + 5 STRUCTURAL + 7 NOT-RUN

no check missing, unplanned, duplicated or unclassified, every `GAP` with an
issue and every `STRUCTURAL` with its Public origin path. It does not
*qualify* as complete for the same reason #143 did not: the same seven
`NOT-RUN` checks, each blocked outside the add-on. This file only shows the
report reconciles; #143's own evidence and counts are left as that run
recorded them.

## What the run left on the host

Nothing. Two GETs per surface (`/robots.txt`, `/sitemap.xml`) and the home
page, with the run's usual login on each surface. Odoo caches a sitemap per
(website, URL root) for 12 hours, so the copies read here may have been
served from that cache.
