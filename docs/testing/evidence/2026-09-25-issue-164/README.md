# Live tier for the Canonical URL catch-up (#164)

Run on 2026-09-25 against the test host, two targets:

- **Local build of branch `issue-164`** (`local_odoo18ce`, built on the host
  from the branch per `docs/testing/LOCAL_BUILD_ON_HOST.md`; no `public_url`,
  so its Canonical URL is the LAN origin on the published port 8169). This is
  where the fix itself was exercised. `<LAN_IPV4>` stands for the host's LAN
  address (ADR 0003), `<HA_BASE>` for the Home Assistant entrance,
  `<INGRESS_PREFIX>` for the add-on's Ingress path.
- **Released add-on `1b7b4ce7_odoo18ce` at 0.4.4**, database `odoo_parity`,
  for the P-Check rerun and `U-D8`. Its `website.domain` was set by the
  maintainer's restart workaround (#164 comment), not by this fix.

## The scenario, twice

The add-on was pointed at a fresh `default_db`, so the database was created
at that start with `base` only and the bootstrap logged
`website module not installed` for it. Then `website` was installed through
the Ingress Apps screen (`odoo18ce/tests/e2e_ingress_install.py`,
`install.jsonl`), while a watcher fetched the Ingress home page every
20 seconds (`ingress-home-head.txt`). The add-on log is in
`addon-log-excerpt.txt`. No restart at any point after the install.

| | Run 1: PR #173 as opened | Run 2: with the post-commit signal |
|---|---|---|
| Build | `0.4.4-202609252034` | `0.4.4-202609252144` |
| Database | `catchup164` | `catchup164b` |
| Bootstrap at start | 21:35:38 `website module not installed` | 21:46:35 `website module not installed` |
| `website` installed via Ingress | 21:37:13 (48 s) | 21:48:26 (50 s) |
| Catch-up line in the add-on log | 21:40:17 `maintenance db=catchup164: … website.domain=http://<LAN_IPV4>:8169` | 21:51:13 `maintenance db=catchup164b: … website.domain=http://<LAN_IPV4>:8169` |
| `select domain from website` | `http://<LAN_IPV4>:8169` | `http://<LAN_IPV4>:8169` |
| Ingress home page `og:url`, `og:image`, `twitter:image` after the write | **still `<HA_BASE>`** at +18 s, +60 s, +2 min | **`http://<LAN_IPV4>:8169`** from the first sample after the write (+15 s) |

Acceptance item 1 (the log line within one round, no restart) held in both
runs: 3 min 4 s and 2 min 47 s after the install.

Acceptance item 2 (the home page's outbound links on the Canonical URL
without a restart) **failed in run 1**: the ORM-cache concern the brief
raised was real. `og:url` is built from `request.website.domain or
request.httprequest.url_root` (`website/models/mixins.py`), `website.write`
marks every registry cache invalidated, but only an RPC request calls
`registry.signal_changes()` after its commit (`odoo/service/model.py`);
`odoo shell` does not. The workers kept the stale website until the next
restart. Confirmed by hand: `clear_cache()` + `commit()` +
`signal_changes()` from an `odoo shell` on `catchup164` at 21:42, and the
next watcher sample (21:42:56) carried the Canonical URL. The maintenance
library now makes that call after its commit, and run 2 passed without any
manual step. The `canonical` link was on the Canonical URL in both runs even
before the write: it falls back to `web.base.url`, which the bootstrap
already wrote.

## P-Check rerun on `odoo_parity` (Released add-on)

`e2e_parity_shared_layers_live.py pcheck --db odoo_parity`, 2026-09-25:

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | **PASS**: `website.domain` = `<PUBLIC_BASE>` (was FAIL in the #143 run) |
| P-6 | PASS: same login on both surfaces, both serving `odoo_parity` |

## `U-D8` rerun — `checks-rerun.jsonl`

`run --only U-D8 --db odoo_parity`, run id `WOOW-PARITY-20260925T124620Z`,
one record: still **`GAP`**, Public `all SEO URLs on <PUBLIC_BASE>`, Ingress
`SEO URLs on <HA_BASE>` with bases `[<HA_BASE>, <PUBLIC_BASE>]`. Fetched
directly through Ingress to say which is which: the home page's `canonical`,
`og:url`, `og:image` and `twitter:image` are all on `<PUBLIC_BASE>`;
`sitemap.xml`'s 12 `<loc>` entries are all on `<HA_BASE>`. The remaining
gap is the sitemap only, which is **#172**; the website-domain half of
`U-D8` is closed by this fix. The record's `issue` field is `#172`, with a
note saying which URLs are on which base.

## What the run left on the host

`local_odoo18ce` stays at `0.4.4-202609252144` with `default_db=catchup164b`
and the two throwaway databases `catchup164` and `catchup164b` (plus the
pre-existing `dbleak`); ports 8169/8172. The Released add-on and
`odoo_parity` were not changed. Restore per `LOCAL_BUILD_ON_HOST.md` section 7
when the local build is no longer needed.
