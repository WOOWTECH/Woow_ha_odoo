# #239's two owed lines are measured, and all four media checks now build what they measure (#266)

**Result: line 2 passes — under Ingress the element's `data-original-src` arrives
prefixed and the dialog preselects its tile; on the Public origin the same
attribute is root-relative and the same tile is selected. Line 3's tile is
measured through the **legacy** editor's dialog and passes on both surfaces; the
control that was looked for, `#media-replace`, is **present but hidden**, and a
double-click is what reaches the dialog. Neither result moves #239's severity,
which its own row already says: nothing it measures is stored. One divergence
found beside them and filed as #271 — under Ingress the Documents tab lists every
generated asset bundle, because a generic literal rewrite prefixes an ORM domain
pattern.**

Run on 2026-10-02 against the test host's Released add-on `1b7b4ce7_odoo18ce` at
**0.4.10**, database **`odoo_parity`** (the 29 modules of #144), target `test-6`.
One run id, `WOOW-MARKUP-20261002T074704Z`.

**No Release and no Deploy.** #239's three rules shipped in 0.4.10 (PR #259) and
the host was already on it — `version: 0.4.10`, `version_latest: 0.4.10`,
`update_available: false`, `state: started`, read before the first check. The
only change this run needed was to the driver, which is not in the image. The
rules are confirmed to have reached the browser by the run's own reading rather
than by the version number: `rule_in_served_method` and
`legacy_rule_in_served_method` are both `true` under Ingress and both `false` on
the Public origin, on every record.

Driver:

    odoo18ce/tests/e2e_ingress_markup_live.py  media-image-todo        --surface both --cleanup
    odoo18ce/tests/e2e_ingress_markup_live.py  media-document-todo     --surface both --cleanup
    odoo18ce/tests/e2e_ingress_markup_live.py  media-document-mailing  --surface both --cleanup
    odoo18ce/tests/e2e_ingress_markup_live.py  media-image-website     --surface both --cleanup
    odoo18ce/tests/e2e_ingress_markup_live.py  report markup.jsonl
    odoo18ce/tests/e2e_parity_shared_layers_live.py  pcheck

| File | What it is |
| --- | --- |
| `markup.jsonl` | 14 records, `woow.ingress-markup/v1`, run `WOOW-MARKUP-20261002T074704Z` |
| `markup.ambient.json` | the ambient figure, one line per surface per invocation — 14 lines, matching the records |

`conservation.json` and `reconciled.jsonl` are absent for #243's and #265's
reason: this run drove the markup driver and not
`e2e_parity_shared_layers_live.py run` / `report`, so there is no planned set to
reconcile against. §10.6 of the parity plan records why the 76-item conservation
figure does not move for it, and §12 why this schema does not feed
`conservation`.

**`markup.jsonl` holds every attempt, not only the verdicts.** Two checks were
run twice, and the first attempt of each is a reading that mattered — see **The
first two attempts**. **The last record for a check and surface is its verdict**;
`report` dedupes that way and prints the attempt count beside the tally.

## P-Check

`pcheck --db odoo_parity`, 2026-10-02, all PASS. P-6 is what makes the two
surfaces comparable at all, and P-5 is what the head links are built from.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |

## #239 — the three lines, all measured

| Line | Screen | Ingress | Public | Verdict |
|---|---|---|---|---|
| 1, image | a scratch to-do holding an image, current editor | element `<INGRESS_PREFIX>/web/image/1401-…png`, **4 tiles, 1 selected** | root-relative element, **1 tile, 1 selected** | **`PARITY`** |
| 2, website | the website editor's Replace Media, on a page this run built | `data-original-src` **prefixed**, **4 tiles, 1 selected** | `data-original-src` root-relative, **1 tile, 1 selected** | **`PARITY`** |
| 3, document | the mail designer's **legacy** dialog, on a document this run built | element `href` prefixed, Documents tab, **30 tiles, 1 selected** | root-relative `href`, **1 tile, 1 selected** | **`PARITY`** |
| 3, document | the same, on the **current** editor | unreachable: no control opens the dialog | unreachable, the same way | `NOT-RUN`, with its reason |

`route_escape=0`, `http_4xx_5xx=0`, `console_error=0`, `pageerror=0`,
`failed_requests=0` on every one of the 14 records. `stored_prefix_found=no`.

### Line 2, the one that had never been exercised

This is the line #239's own comment called *the more informative one*, and #243's
run reached its screen and measured nothing: the home page's only visible image
is `/web/image/website/1/logo/My%20Website`, a record-field image whose
`data-original-src` is `None`, so `if (this.props.media.dataset.originalSrc)`
never ran.

What this run measured, with the fixture on the only path the attribute can
arrive prefixed on — a page delivered as an **HTML response**:

| | Ingress | Public |
|---|---|---|
| element `src` | `<INGRESS_PREFIX>/web/image/1409-58a8ca82/woow-image-fixture-….png` | `/web/image/1410-58a8ca82/…` |
| element `data-original-src` | **`<INGRESS_PREFIX>`**`/web/image/1409-…png` | `/web/image/1410-…png` |
| the same attribute **after** the image was selected | unchanged, still prefixed | unchanged, still root-relative |
| `data-mimetype-before-conversion` | `image/png` | `image/png` |
| tiles / selected | 4 / **1** | 1 / **1** |
| the control that opened the dialog | `ReplaceMedia` snippet option | the same |
| `rule_in_served_method` / `legacy_` | `true` / `true` | `false` / `false` |
| served `isInitialMedia` length | 327 | 205 |

So the branch executed, on a prefixed operand, against an unprefixed
`attachment.image_src`, and matched. The 122-byte difference between 327 and 205
is the two `__WOOW_INGRESS_MARKUP_OUT__` insertions.

**Two readings in that table exist because either would have produced a false
pass, and both are new.**

- **The attribute is read again after the click.** `ImageTools._initializeImage`
  loads `data-original-src` and **deletes** the whole `data-original-*` group
  when that load is rejected (`web_editor/static/src/js/editor/snippets.options.js:7679-7686`),
  and that runs between the click and the dialog. A record carrying only the
  before-reading could not tell *the attribute was dropped* from *the comparison
  disagreed*. It was unchanged on both surfaces.
- **The fixture carries `data-mimetype-before-conversion`.** `loadImageInfo`
  early-returns only when **both** that attribute and `data-original-src` are
  present (`image_processing.js:490-496`). Without it, the function would have
  re-fetched the image info in that same window and overwritten
  `data-original-src` with the root-relative value the ORM had just handed back
  — so under Ingress the branch would have compared two unprefixed values and
  passed whether or not the rule shipped. A real image saved from the website
  editor carries all four `data-*`, which is why the fixture does.

### Line 3's tile, and the control that was looked for

**The tile is measured, on the legacy dialog.** `media-document-mailing` seeds a
document link into a draft mailing's `body_arch`, opens the mail designer — which
is one of the two screens still running the legacy `web_editor` editor — and
reopens the dialog on the link. The dialog lands on the **Documents** tab by
construction (`media_dialog.js:82-93` routes by the element's `tagName`, and
`DocumentSelector.tagNames` is `["A"]`) and the fixture's tile is selected on
both surfaces.

Rule 3's premise is re-measured beside it, on the legacy dialog this time:

| | Ingress | Public |
|---|---|---|
| element `href` | `<INGRESS_PREFIX>/web/content/1405?<redacted>` | `/web/content/1406?<redacted>` |
| served `fetchAttachments` literal prefixed | **true** | **false** |
| `.replace(/[?].*/)` present | true | true |
| served method length | 372 | 309 |

Prefixed against prefixed under Ingress, root-relative against root-relative on
the Public origin — the same 63-byte difference #243 recorded for the current
editor's copy, now read on the dialog whose tile was actually shown.

**`#media-replace` is present and hidden, and that is the answer to "the control
that was looked for".** The run records it rather than inferring it:
`replace_control_present: true`, `replace_control_found_in: "page"`,
`replace_control_visible: **false**`, `replace_control: "dblclick"` — identical on
both surfaces. The mechanism is in the legacy editor itself and is not about
Ingress at all:

- `#media-replace` is un-hidden for anything matching
  `img, .fa, .o_image, .media_iframe_video` (`web_editor/static/src/js/wysiwyg/wysiwyg.js:91`,
  `:2337-2346`) — `.o_image` included, and it is the one case the snippets
  sidebar does not steal the button, because that only happens for an `img`
  (`:2349-2351`).
- Twelve lines later the same function hides the **whole toolbar** for a media
  whose `data-mimetype` is not an image (`:2396-2399`), and
  `DocumentSelector.createElements` always stamps `data-mimetype` on a document
  (`document_selector.js:86`). So on a faithful fixture — the anchor spelled
  exactly as the dialog writes one — the toolbar is gone.
- The `dblclick` binding on the same selector (`:630-657` → `:3037-3050`) has no
  mimetype guard and calls `openMediaDialog` with the anchor. That is the way in.

**The current editor stays `NOT-RUN`, and it is now a reading rather than an
absence.** `media-document-todo` builds its own scratch to-do and document, finds
the `a.o_image`, selects it, finds no `Replace` item (it is namespaced to `image`,
`media_plugin.js:44-55`, and the namespace predicate requires an `IMG`,
`image_plugin.js:61-70`), falls back to a double-click, and no dialog opens. The
current editor does not even produce an `a.o_image` any more — its document
selector renders a `span.o_file_box` whose whole subtree suppresses the toolbar
(`file_plugin.js:44-48`) — so this row is unreachable there by construction, and
the fixture is what makes that a measurement instead of "the record held no
document link".

### What found a divergence: #271

`media-document-mailing` listed **30** tiles under Ingress and **1** on the Public
origin, for the same database, the same login and the same one attachment. The
extra tiles are generated asset bundles —
`mass_mailing.assets_wysiwyg.min.js`, `web_editor.wysiwyg_iframe_editor_assets.min.css`
and the rest.

The cause was measured, not guessed. `DocumentSelector.attachmentsDomain`
excludes bundles with `!['url', '=like', '/web/assets/%']`, and that string
literal lives in the same bundle as the URL literals the Ingress asset location
rewrites. The run read the served getter:

| | Ingress | Public |
|---|---|---|
| `served_domain_has_web_assets_literal` | true | true |
| `served_domain_asset_exclusion_prefixed` | **true** | **false** |
| served `attachmentsDomain` length | **383** | 320 |

63 bytes — one prefix insertion. The exclusion then reads
`NOT (url =like '<INGRESS_PREFIX>/web/assets/%')`, which matches no stored `url`,
so it excludes nothing.

**Filed as #271, not against #239, and #239's severity does not move.** The
preselection #239 is about is correct on both surfaces; what differs is which
attachments the dialog *lists*, and the rule responsible is one of #166's generic
literal rules rather than any of #239's three. Nothing is stored — a domain
travels in a request body — and `stored_verdict` is `CLEAN` on both surfaces.
#271 carries the real finding, which is the class: a generic literal rewrite
reaches **ORM domain literals**, not only URLs, and three more such literals in
the image selector are candidates it owes a measurement for.

## The first two attempts

Both are kept, because each is a reading that decided what this run did next.

| # | Check | Reading | What it decided |
|---|---|---|---|
| 1, 2 | `media-document-todo`, before the fixture | `NOT-RUN`: "the description holds no document link (`a.o_image`)" on both surfaces | #243's line-3 finding was **not repeatable**. Its document link and attachment were made by hand and cleaned up, so the next run could only report an absence. The check now builds both. |
| 3, 4 | `media-image-todo`, before the fixture | `ABSENT` on both surfaces: Ingress 3 tiles / 0 selected, Public 0 tiles / 0 selected, element `src` = the static module asset `/project_todo/static/img/todo_access.png` | #243's line-1 **pass** was not repeatable either, for the same reason: it came from an attachment scoped to the onboarding to-do by hand. The onboarding to-do's own picture is a static module asset with no `ir.attachment` behind it, so `isInitialMedia` can match nothing and "none selected" measures nothing. The check now builds a scratch to-do and its image, and line 1 passes again. |

That is why **all four** media checks build what they measure, and not only the
two #266 names. The two the Issue named could not be measured because the host
carries nothing for their branches to execute on; the two it did not could no
longer be measured because the fixtures that made #243's readings were, correctly,
removed. `--cleanup` removes all four, so every row here can be taken again.

## Ambient rows

This run carries its own figure, which #243's could not: #264 has since given this
driver the accounting, and `markup.ambient.json` is the first one this family has
written. One line per surface per invocation — 14 lines beside 14 records.

| Check | Navigations per surface | `website.track` delta | `website.visitor` delta |
|---|---|---|---|
| `media-document-todo` (attempt 1 / 2) | 1 / 2 | 0 | 0 |
| `media-image-todo` (attempt 1 / 2) | 1 / 1 | 0 | 0 |
| `media-document-mailing` (attempt 1 / 2) | 1 / 1 | 0 | 0 |
| `media-image-website` | 5 | 0 | 0 |

Absolute counts on either side of every window: `website.track` **198**,
`website.visitor` **59** — the same figures #243's run read on the host after it
finished, so nothing has written one of those rows on this database since.

**What this does and does not say about the website editor.** #243's README said
"the website-editor check navigates website pages, so ambient rows were certainly
written", and could state no delta. This run's own delta over that check is
**zero** across five navigations per surface. That is a reading about *these*
windows and not a claim that the editor never writes a tracked row: the window
runs from after the login to after the last navigation, and `navigation_basis` is
every document GET the browser context made under the surface's base — an upper
bound on page views, since the editor's preview fetches and redirect hops count
too. The honest statement is the narrow one: over the navigations this run made,
including the website editor's own, the two models did not move.

The guarantee, quoted the way ADR 0012's 2026-10-01 postscript (#227) requires: a
read-only Live run makes **no business writes**. It does not leave **zero rows**,
and never has on a database with `website` installed. This run was not read-only
in any case — see **Writes**.

## Writes

Every one of the four checks writes, and every one cleans up after itself.
`--cleanup` was passed on all four.

| Record | What changed | Why | Put back |
|---|---|---|---|
| `ir.attachment` 1401–1410 | ten public fixture attachments created — one image or document per surface per invocation | the right-hand operand of the comparison each line measures; `public=True` is what lists it whatever record the dialog was opened from, and `order: 'id desc'` with a limit of 30 is what makes it the first tile | yes — all ten unlinked, `fixture_removed.attachment: true` on every record |
| `project.task` 14, 15, 16, 17 | four scratch to-dos created, each holding one fixture element in `description` | lines 1 and 3 on the current editor; a **scratch** record and never the onboarding to-do, because #235's checks read that record's stored `src` | yes — all four unlinked, `fixture_removed.task: true` |
| `website.page` 11, 12 and `ir.ui.view` 3775, 3776 | two fixture pages created, one per surface, through `website.new_page`'s own `sections_arch` | line 2 needs stored arch delivered as an HTML response, and this host ships no website page carrying `data-original-src` | yes — both pages and both views unlinked, `fixture_removed.page: true`, `.view: true` |
| `mailing.mailing` 3 `body_arch`, `body_html` | seeded with the document fixture, twice (two attempts) | line 3's legacy screen is the mail designer, and its body is the field the designer loads | yes — restored both times; read back afterwards at `arch_len 0 / html_len 166`, which is where the four fixture mailings started |

No module, group, setting or add-on option was changed. No mailing was sent. No
payment was made. Nothing was confirmed. Nothing was saved in either editor — the
website editor was discarded and the mail designer's form was discarded when it
showed unsaved changes.

**Verified on the host after the run**, read over `psql` in the add-on's own
container: `ATTACHMENTS_LEFT []`, `SCRATCH_TASKS_LEFT []`, `FIXTURE_PAGES_LEFT []`,
`FIXTURE_VIEWS_LEFT []`, all four mailings at `arch 0 / html 166`, and **0**
`hassio_ingress` occurrences in any `mailing.mailing` body or in
`project.task` 5's description.

**`project.task` 5 was not written by this run, and its length is not this run's.**
It reads 5762 characters against the 5385 #243's run left, and its `write_date` is
`2026-10-02 06:36:32Z` — before this run's first command at 07:47Z. The two
attempts that opened it (`media-document-todo` and `media-image-todo`, before the
fixture) navigated to the form, found no element and left; neither typed and
neither saved, and the record carries 0 Ingress tokens. The 377 extra characters
belong to the run that wrote it last.

## What this run does **not** say

- It does not measure rule 2 on the **mailing** screen, the other candidate #266
  named. It cannot be measured there and this run established why rather than
  skipping it: `mass_mailing_themes` is the only module in the package that ships
  `data-original-src` in stored arch, its seven themed images point at
  `data-original-id` values from the developer's own database and at paths no
  `ir.attachment` here matches — so they can never highlight a tile — and the
  theme arch reaches the designer over `ir.ui.view.render_public_asset`, which is
  `call_kw` and is not rewritten, so the attribute arrives root-relative. The
  website page is the only screen on which both halves hold at once.
- It does not say the current editor will never reach a document tile. It says no
  control in the shipped 0.4.10 bundle does, and names the three places that
  decide it.
- It does not measure the `cssAssetId`-only branch of `HtmlViewer`, which has no
  screen on this host. That remains the Static tier's, as #243 recorded.
- It does not re-measure #237, #238, #240 or #234. Those five rows were run on
  this Release by #243 and #265 and nothing here changes them.
