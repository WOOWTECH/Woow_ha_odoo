# `U-D8` split into head links and the sitemap (#172)

Run `WOOW-PARITY-20260927T104614Z` on 2026-09-27 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`**
(the 29 modules of #144). Driver:
`odoo18ce/tests/e2e_parity_shared_layers_live.py run --only U-D8`
(pure decisions in `e2e_parity_shared_layers.py`, static tests in
`test_e2e_parity_shared_layers.py`). The run itself writes nothing: three
HTTP GETs per surface (`/robots.txt` twice, `/sitemap.xml`) and the home
page, with the usual login on each surface.

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
| `check:U-D8\|website\|sitemap.xml` | **`APPROVED-DIVERGENCE`** (severity `none`, `AD-8`) | HTTP 200, 14 sitemap URL(s) on `<PUBLIC_BASE>` | HTTP 200, 14 sitemap URL(s) on `<HA_BASE>` |

- **Head links and `robots.txt`** (`generic`): the home page's `canonical`,
  `alternate`, `og:url`, `og:image`, `twitter:image` and icon links plus
  `robots.txt`, on both surfaces, every base `<PUBLIC_BASE>`. This is the
  half #164's catch-up and the restart workaround closed; the record's
  `by_source` says which source each base came from.
- **`sitemap.xml`** (`website`): `AD-8` verified in reverse, every statement
  held — both surfaces answered 200 with 14 URLs; Ingress's `robots.txt`
  carries `Disallow: /` **and** `Sitemap: <PUBLIC_BASE>/sitemap.xml`;
  Ingress's sitemap is on `<HA_BASE>` and none of its URLs holds an Ingress
  prefix (`ingress_prefix: 0` — a prefixed URL would be a leaked Supervisor
  token, so only the count is recorded, never the URL); the Public origin's
  sitemap is on `<PUBLIC_BASE>` and its `robots.txt` has no `Disallow: /`,
  so crawlers still reach the site. Any of those failing is a `GAP`,
  including the divergence disappearing and an empty `website.domain`
  (P-5 failing), which takes `Disallow: /` away and leaves nothing steering
  crawlers off the Ingress copy. Those directions are covered in the static
  tier (`SeoOutputTests`), not by this run.

## Conservation (parity plan section 12) — `reconciled.jsonl`

The planned set now holds both `U-D8` records, so a run's `checks.jsonl`
must carry both. `reconciled.jsonl` is #143's `checks.jsonl` with this run's
two records substituted for its single `U-D8` record (76 records against 76
planned checks); `conservation.json` is the `report` over it:

    76 observed = 54 PARITY + 8 GAP + 2 APPROVED-DIVERGENCE + 5 STRUCTURAL + 7 NOT-RUN

no check missing, unplanned, duplicated or unclassified, every `GAP` with an
issue (#159, #165–#170) and every `STRUCTURAL` with its Public origin path.
`report` still exits 1, because the run does not *qualify* as complete for
the same reason #143 did not: the same seven `NOT-RUN` checks, each blocked
outside the add-on. This file only shows the report reconciles; #143's own
evidence and counts are left as that run recorded them, and the parity plan's
section 10.6 carries the numbers above.

## What the run left on the host

No Odoo record was created or changed by the run. Odoo itself caches each
sitemap as an `ir.attachment` per (website, URL root) for 12 hours and
regenerates it on a miss, so the two GETs may have caused Odoo to write its
own cache rows; nothing else was touched, and no add-on, host or database
setting was changed.
