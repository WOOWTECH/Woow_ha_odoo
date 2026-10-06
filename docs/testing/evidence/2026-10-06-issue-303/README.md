# #271's fix on a Released image, read on both surfaces (#303)

**Result: Release 0.4.11 carries #271's fix, and the reading matches what the
local build showed. On both surfaces the served `DocumentSelector.attachmentsDomain`
keeps its `'/web/assets/%'` pattern unprefixed
(`served_domain_asset_exclusion_prefixed: false`), and the getter is **320**
bytes long. The Documents tab lists **1** tile and selects it. Ingress reads
`UNDER-PREFIX` and the Public origin `AT-ORIGIN-ROOT`, each the verdict expected
for its surface. Nothing is stored: `stored_verdict` is `CLEAN` on `body_arch`
and on `body_html`, with 0 prefixes in each.**

The run was on 2026-10-06 (UTC) against the **Released** add-on
`1b7b4ce7_odoo18ce` at **0.4.11**, which came from the App Store. The database
was **`odoo_parity`** and the target `test-28`: the test host is now
`192.168.2.28`, and it still owns the Public origin
`woowtech-odoo-test-6.woowtech.io`. Before the run, the add-on's options were
read off the Supervisor (`public_url` that origin, `default_db: odoo_parity`)
to confirm that both surfaces are one add-on and one database. #271 could not
take this reading, because its local build has no `public_url`.

Driver:

    odoo18ce/tests/e2e_ingress_markup_live.py  media-document-mailing \
      --db odoo_parity --surface both --cleanup

| File | What it is |
| --- | --- |
| `markup.jsonl` | 4 records, `woow.ingress-markup/v1`: the `NOT-RUN` pair of `WOOW-MARKUP-20261006T054048Z` and the verdict pair of `WOOW-MARKUP-20261006T062153Z` |
| `markup.ambient.json` | the ambient figure, one line per surface of the verdict run: `website.track` +0, `website.visitor` +0 |

**The `NOT-RUN` pair is a login, not a reading.** The first attempt had no
`ODOO_TEST_LOGIN` that `odoo_parity` accepts, and both surfaces timed out
waiting for `.o_main_navbar`. A dedicated user,
`e2e-markup@example.invalid` (uid 15), was then created on the host with
`base.user_admin`'s groups, and the second run used it. `admin`'s password was
left alone. The HA long-lived token the Ingress side needs was created for the
run and deleted after it.

## The reading

| | Ingress, 0.4.11 | Public origin, 0.4.11 | #271, local build (Ingress) | #266, Release 0.4.10 (Ingress) |
|---|---|---|---|---|
| verdict | **UNDER-PREFIX** | **AT-ORIGIN-ROOT** | — | — |
| `operand.served_domain_asset_exclusion_prefixed` | **`false`** | `false` | `false` | `true` |
| `operand.served_domain_has_web_assets_literal` | `true` | `true` | `true` | `true` |
| `operand.served_domain_length` | **320** | 320 | 320 | 383 |
| `dialog.tiles` | **1** | 1 | 1 | 30 (the page limit) |
| `dialog.tiles_selected` | 1 | 1 | 1 | 1 |
| `dialog.tile_sources` | the fixture alone | the fixture alone | the fixture alone | the fixture, then `mass_mailing.assets_wysiwyg.min.js`, … |
| `stored_verdict` | `CLEAN` | `CLEAN` | `CLEAN` | `CLEAN` |
| `signals` (console errors, failed requests, 4xx/5xx, route escapes) | all 0 | all 0 | — | — |

## What the run touched, and what it put back

- **Mailing 3**, `mailing_source: found`, which means it was borrowed and not
  built. `discarded` and `body_restored` are both `true` on both surfaces.
- **The fixture attachments** 1432 (Ingress) and 1433 (Public):
  `fixture_removed.attachment: true` on each.
- **`replace_control_present: true`, `replace_control_visible: false`.** This
  is #266's reading of the legacy toolbar on a non-image `data-mimetype`, not a
  regression.

## The Release this reads

#303's other acceptance items were read off the Release itself:

- **Layers.** The `0.4.11` manifests carry `0.4.10`'s L1–L7 digests on both
  architectures. Only L8 (rootfs) and L9 (chmod) differ: amd64
  `58a659f01512`→`1ee2204a0fb0` and `c1bfd6066421`→`f8319d67a6c5`, aarch64
  `9cd91b0ec8bb`→`691ee1a23ad4` and `aeb5627c6622`→`1caa9cdc1b4d`. Both
  `publish image` jobs imported `…:buildcache`.
- **Size.** The Release notes' table reads **0.1 MiB** on both architectures,
  updating from 0.4.10, 0.4.9 and 0.4.8.
- **The store.** The first store Sync left odoo18ce at
  `waiting-for-source-notification`, because Woow_HA_App_Store `26bb83d` had
  moved every source to notifications 18 minutes before the Release. #305 added
  `.github/workflows/woow-addon-sync.yml`. Its first run published `0.4.11`,
  and a store Sync limited to `odoo18ce` reported `synced`.
- **The Deploy.** A Supervisor `store/reload` moved `version_latest` from a
  stale `0.4.10` to `0.4.11`, which is #235's trap. The update then ended at
  `version: 0.4.11`, `version_latest: 0.4.11`, `update_available: false`,
  `state: started`. This was driven over the HA websocket `supervisor/api`
  through a logged-in browser, because the `ssh ha` alias still points at the
  host's old address.
