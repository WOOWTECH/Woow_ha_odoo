# A search pattern is no longer prefixed, and the Documents tab lists documents (#271)

**Result: the fix passes on a real host. Under Ingress the served
`DocumentSelector.attachmentsDomain` carries its `'/web/assets/%'` search
pattern **unprefixed** — `served_domain_asset_exclusion_prefixed: false`,
`served_domain_has_web_assets_literal: true`, getter length **320** against the
**383** #266 read on the Released add-on the day before. The Documents tab
lists **1** tile and selects it, where the same database's rows would have put
**19** there without the fix. Nothing is stored: `stored_verdict` `CLEAN` on
both `body_arch` and `body_html`, 0 prefixes each.**

Run on 2026-10-03 (UTC) against the test host's **local build**
`local_odoo18ce` at **0.4.10-202610031232**, database **`catchup164b`**, target
`test-6`, Ingress only. One verdict run id,
`WOOW-MARKUP-20261003T124016Z`, and one earlier attempt,
`WOOW-MARKUP-20261003T123902Z`.

**No Release and no Deploy, by decision.** #271's agent brief settles this:
the fix only moves the Ingress side, the Public origin's reading is unchanged
and was already measured by #266 the day before, so the Live reading goes
through the local build (`docs/agents/live-tier.md`, deploy option 2) and no
Release is cut. The local add-on has no `public_url`, so it cannot be diffed on
both surfaces — which is why this run has one surface and why the Public figure
it is compared against is #266's.

Driver:

    odoo18ce/tests/e2e_ingress_markup_live.py  media-document-mailing \
      --db catchup164b --surface ingress --mailing-id 1 --cleanup

| File | What it is |
| --- | --- |
| `markup.jsonl` | 2 records, `woow.ingress-markup/v1` — the `NOT-RUN` attempt and the verdict |
| `markup.ambient.json` | the ambient figure, one line per invocation — 2 lines, matching the records |

`conservation.json` and `reconciled.jsonl` are absent for #243's, #265's and
#266's reason: this run drove the markup driver and not
`e2e_parity_shared_layers_live.py run` / `report`, so there is no planned set
to reconcile against. §12 of the parity plan records why this schema does not
feed `conservation`, and §10.6 why the 76-item figure does not move for it.

## There is no P-Check table, and what stands in its place

`pcheck`'s P-1 to P-5 are read off `ODOO_PUBLIC_URL`, which is the **Released**
add-on's Public origin — a different add-on and a different database from the
one this run drove. Running it would have produced a table about the wrong
surface, so it was not run, and the readings that actually make this run
interpretable are these, each taken by the run or off the host:

| Reading | Value | Why it matters |
|---|---|---|
| `local_odoo18ce` version | `0.4.10-202610031232` | the branch, built on the host |
| the image it runs | `local/amd64-addon-odoo18ce:0.4.10-202610031232` | a real local build and not a pulled Release image (`LOCAL_BUILD_ON_HOST.md`, trap a) |
| `network` after the update | `{8069: 8169, 8072: 8172}` | the custom ports survived (trap c) |
| counter-rules in the rendered `/etc/nginx/nginx.conf` | **2**, lines 616–617 | the fix is in the config the gateway loaded |
| the same count in the Released add-on's config | **0** | the before-state is on the same host, not a memory |
| Odoo package, both containers | `18.0.20260930` | the pinned `.deb` the fixtures were derived from |
| `dialog.rule_in_served_method` / `legacy_rule_in_served_method` | `true` / `true` | #239's rules reached the browser, so the screen is the one it describes |
| `dialog.markup_out_global` | `"function"` | the Runtime shim ran |

## The reading

| | this run (local build, fixed) | #266 on Release 0.4.10 (Ingress) | #266 (Public origin) |
|---|---|---|---|
| `operand.served_domain_asset_exclusion_prefixed` | **`false`** | `true` | `false` |
| `operand.served_domain_has_web_assets_literal` | `true` | `true` | `true` |
| `operand.served_domain_length` | **320** | 383 | 320 |
| `dialog.tiles` | **1** | 30 (the page limit) | 1 |
| `dialog.tiles_selected` | 1 | 1 | 1 |
| `dialog.tile_sources` | the fixture alone | the fixture, then `mass_mailing.assets_wysiwyg.min.js`, … | the fixture alone |
| `stored_verdict` | `CLEAN` | `CLEAN` | `CLEAN` |

The getter is bundle code and not data, so its length does not depend on which
database serves it: **320** is the same number the Public origin read and the
same number the captured fixture
`odoo18ce/tests/fixtures/bundles/media_dialog_document_domain.js` is long. That
is the Static tier and the Live tier agreeing on one figure.

**63 bytes, measured rather than arithmetic.** 383 − 320 = 63 was #266's
reading of the difference. This run read the add-on's own Ingress prefix length
off the Supervisor: **63**. So the difference was exactly one prefix insertion
and nothing else.

## The before, on this database's own rows

The fix is deployed, so the 19 tiles cannot be photographed here. Both halves
of why it is 19 are measured instead, read-only, over the session's own data:

| Count on `catchup164b` | Value |
|---|---|
| `ir.attachment` rows whose `url` is `=like '/web/assets/%'` | **18** |
| of those, how many survive the exclusion as Odoo writes it (an `or` of "no url" with "not `=like '/web/assets/%'`") | **0** — all excluded |
| of those, how many survive the same clause with the prefix on the pattern | **18** — none excluded |
| `url like '/api/hassio_ingress/%/web/assets/%'` | **0** — no stored value has a prefix |

So the prefixed exclusion excludes nothing on this host's real rows, and the
unprefixed one excludes every bundle. 18 bundles plus the one document the
check builds is 19 tiles; the run measured **1**.

## What this run seeded, and what it left

`media-document-mailing` builds its own attachment and restores the fields it
touches, but it **looks up** the mailing rather than building one:
`editable_mailing_id` searches for a `mailing.mailing` in `draft` or
`in_queue`, and returns `NOT-RUN` when there is none. `catchup164b` had no
mailing at all, which is what the first attempt
(`WOOW-MARKUP-20261003T123902Z`) recorded — `NOT-RUN`, with
`"no mailing.mailing in state draft or in_queue on this database"`. One scratch
mailing was seeded for the second attempt and removed afterwards.

The host is back to the state it was in before the run, except where this
README says otherwise:

- `mailing.mailing`: **0 rows** on `catchup164b` after the run (the seeded
  scratch mailing was removed; `body_restored: true` had already put its
  `body_arch` back first, so the removal is not what hid a write).
- the fixture attachment: removed (`fixture_removed.attachment: true`), and
  `ir.attachment` matching `woow-document-fixture%` is **0**.
- the mail designer was **discarded** rather than saved (`discarded: true`),
  and both fields were read back before the session closed:
  `body_arch` and `body_html` `CLEAN`, 0 prefixes each.
- ambient rows: `website.track` **+0**, `website.visitor` **+0**, over 1
  navigation, absolute 42 on either side of the window. Read over the session's
  own `search_count` (#256, #264), never over `ssh`.

Two changes to the host that are **not** undone, both inside ADR 0012 and both
on the local build only:

1. **`mass_mailing` is now installed on `catchup164b`** (44 installed modules,
   up from 38; `contacts`, `link_tracker`, `social_media`, `web_tour` came with
   it), and `-u all` was run against the pinned `18.0.20260930` in the same
   command so the schema matches the image. The check needs the module; the
   database did not have it.
2. **`catchup164b`'s `admin` password now equals the Released add-on's**, so
   `.env`'s credential works on both. The stored hash was copied from
   `odoo_parity` to `catchup164b` on the host; no plaintext was read, typed or
   transferred. Before this, the first driver attempt failed with
   `Login failed for db:catchup164b login:admin` in the add-on log.

The local add-on is left **started** on `0.4.10-202610031232`, which is this
branch. `LOCAL_BUILD_ON_HOST.md` §7 is the restore procedure when it is no
longer wanted; it is deliberately left in place, because the next run of this
family on a branch needs it.

## A gap this run found in the driver

`media-document-mailing` cannot run on a database that has no draft mailing,
and it says so rather than building one — while the other three media checks
build everything they measure, which is exactly what #266 changed them to do.
On `odoo_parity` a draft mailing happens to exist, so the gap is invisible
there and appears the moment the check is pointed at any other database. It is
one `create` away from being closed, and it is the only thing that stopped this
run from being unattended. Recorded here rather than fixed, because #271's
brief puts driver changes out of scope; worth filing against the driver.

## What this does not change

- **#239's severity and its `PARITY` verdict are unchanged.** This run read
  `tiles_selected: 1` and `rule_in_served_method: true`, which is #239's own
  measurement taken again and passing. #239 stores nothing either way.
- **The 76-item conservation tally does not move**, and §10.6's denominator
  does not change. `G-09` is a §11 register entry and not a plan item.
- **§9 gains no row.** The issue body's criterion 5 says "§9 gains this row";
  #266 registered the divergence as §11 `G-09`, and §9 already carries the
  #239 annotation pointing here. §11 `G-09` is updated to what this run read.
