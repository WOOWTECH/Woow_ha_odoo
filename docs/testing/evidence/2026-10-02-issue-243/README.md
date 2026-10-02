# The Ingress markup family's owed Live checks, run on Release 0.4.10 (#243)

**Result: the register's five rows are run. #237 all four checks `PARITY` on both
surfaces, #238 both halves `PARITY`, #240 both halves `PARITY`, #234 `CLEAN` on
both pairs and **not** escalated to `severity: blocker`. #239's image line
`PARITY`; its document line is recorded **unreachable** on the current editor with
its reason and its premise measured another way; its website line is recorded
**not exercised**, with the reason and the two screens that would reach it.**

Run on 2026-10-02 against the test host's Released add-on `1b7b4ce7_odoo18ce` at
**0.4.10**, database **`odoo_parity`** (the 29 modules of #144). Two run ids, both
minted at 01:53:18Z: `WOOW-PEER-20261002T015318Z` for #234 and
`WOOW-MARKUP-20261002T015318Z` for the other four rows.

Drivers:

    odoo18ce/tests/e2e_collab_peer_snapshot_live.py  probe / run / report   (#234)
    odoo18ce/tests/e2e_ingress_markup_live.py        8 checks / report      (#237 #238 #239 #240)
    odoo18ce/tests/e2e_parity_shared_layers_live.py  pcheck

| File | What it is |
| --- | --- |
| `peer.jsonl` | #234's two records, `woow.peer-snapshot.v1`, run `WOOW-PEER-20261002T015318Z` |
| `markup.jsonl` | the other four rows, `woow.ingress-markup/v1`, 38 records, run `WOOW-MARKUP-20261002T015318Z` |
| `task5-description-after-probes.html` | the onboarding to-do's stored description as the `probe` steps left it, exported before it was cleaned (see **Writes**) |

`conservation.json` and `reconciled.jsonl` are absent, and for the same reason as
#235's run: this run drove hand checks and the peer snapshot, not
`e2e_parity_shared_layers_live.py run` / `report`, so there is no planned set to
reconcile against. §10.6 of the parity plan records why the 76-item conservation
figure does not move for it.

**`markup.jsonl` holds every attempt, not only the verdicts.** Five of the eight
checks were re-run after a fixture or a selector turned out to be wrong, and a
past reading is what it recorded, so none was deleted. **The last record for a
check and surface is its verdict** — `report` dedupes that way and prints the
attempt count beside the tally.

## Step 0 — the Release and the Deploy

| | |
| --- | --- |
| **Release** | 0.4.9 → **0.4.10**, PR #262, merged 2026-10-02T01:49:06Z. `v0.4.10` tagged, both images built, store dispatch sent; the Release workflow completed `success`. |
| **Why a Release at all** | 0.4.9 already carries #237's and #238's rules. But `nginx.conf.template` gained **205 lines** after 0.4.9 was cut, and three of the five rows live in them: #234's strip (PR #251), #239's three rules (PR #259), #240's two (PR #260). A run on 0.4.9 measures two rows of five. |
| **Pinned Odoo** | `ODOO_DEB_VERSION` **unchanged** at `18.0.20260930` across this Release, so every `sub_filter` is still the exact expression that was measured against the package. That is the #156 condition in the Issue's "This issue runs last", and it is checked rather than assumed. |
| **Sync** | the App Store mirror's `odoo18ce/config.yaml` was polled until it read `0.4.10`. |
| **Supervisor cache** | `ha store reload` **before** `ha apps update`. It mattered: after the reload `info --raw-json` reported `version_latest: 0.4.10`, `update_available: true`. This is the trap #235 hit from the other side. |
| **Deploy** | `ha apps update 1b7b4ce7_odoo18ce` — completed successfully. |
| **After, read before the first check** | `version: 0.4.10`, `version_latest: 0.4.10`, `update_available: false`, `state: started`. |
| **Slow link** | not needed; the pull completed normally. |

## P-Check

`pcheck --db odoo_parity`, 2026-10-02, all PASS. P-5 is what the head links are
built from and P-6 is what makes the two surfaces comparable at all.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |

## #237 — the readonly html field, all four checks

| # | Screen | Ingress | Public | Verdict |
|---|---|---|---|---|
| 1 | the html field's **history dialog** (plain path) | `<INGRESS_BASE>/web/image/1393-…/woow-markup-fixture.png`, loaded | `<PUBLIC_BASE>/…`, loaded | **`PARITY`** |
| 2 | a scratch `mail.template.body_html` (iframe path) | `<INGRESS_BASE>/project_todo/static/img/todo_access.png`, loaded | `<PUBLIC_BASE>/…`, loaded | **`PARITY`** |
| 3 | both of the above on the Public origin | — | root-relative attribute, resolved at the origin root | **`PARITY`** |
| 4 | the record read back | `CLEAN`, 0 prefixes | `CLEAN`, 0 prefixes | **`PARITY`** |

`route_escape=0`, `http_4xx_5xx=0`, `console_error=0`, `pageerror=0` on every one
of those records.

On the iframe path the rendered attribute is exactly
`sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"`, which
is the `hasFullHtml` branch of `t-att-sandbox` and therefore says which branch
rendered.

**Two corrections to the screens the Issue names, both measured.**

- **Check 1 is not on the To-do form.** `ProjectTaskFormController` is the only
  controller that adds the *Version History* cog item; `project_todo`'s
  `TodoFormController.actionMenuItems` whitelists archive, unarchive, duplicate,
  delete and "Convert to Task", so the item is filtered out there. The screen is
  the **project task** form, `/odoo/project.task/<id>` →
  `project.view_task_form2` (`js_class="project_task_form"`). The dialog itself is
  the plain path by construction: `HistoryDialog.getConfig()` passes only `value`
  and `embeddedComponents`, so `showIframe` (`hasFullHtml || cssAssetId`) can
  never be true.
- **Check 2 cannot be taken on `project.task.description`,** which is the field
  the Issue names. That field is `sanitize_tags=True`: the full-HTML seed came
  back as the bare `<img src="/project_todo/static/img/todo_access.png">`,
  `rendered_iframe` was false on both surfaces, and the field rendered the plain
  path — check 1's screen, measured twice. `mail.template.body_html` is
  `sanitize_tags=False` and renders through `html_mail`, a subclass of the same
  `HtmlField`; a scratch template was created and deleted.

**The `cssAssetId`-only branch is not measurable on this host, as the Issue
predicted, and this run adds nothing to that.** The only shipped view that sets
`cssReadonly` is `mass_mailing`'s mailing body, and that field is
`widget="mass_mailing_html"` — the legacy editor of #238, which carries #238's ten
rules and none of #237's two. So no screen in the parity plan's 25 applications
reaches `HtmlViewer` with `cssAssetId` and without `hasFullHtml`. The Static-tier
contract (`test_ingress_readonly_html_viewer.py`, the `cssAssetId` parameter case,
three tests) stays the standing evidence for that branch.

## #238 — the legacy `web_editor`

| Line | Screen | Reading | Verdict |
|---|---|---|---|
| 3 | a **sent** mailing's body, the readonly iframe (rules 3/4/5) | Ingress: the `<img>` **attribute itself** is `<INGRESS_PREFIX>/web/image/res.company/1/logo`, loaded. Public: root-relative attribute, resolved at the origin root, loaded. | **`PARITY`** |
| 1 | the mail designer loads under Ingress | `rendered_iframe: true`, picture prefixed and loaded, no theme chooser (the body was non-empty) | **`PARITY`** |
| 2 | the save stores **both** fields root-relative | `mailing.mailing.body_arch` `CLEAN`; `mailing.mailing.body_html` `CLEAN` | **`PARITY`** |

The save was a real one: `typed: true`, `save_visible: true`, `saved: true`,
`unsaved_after_save: false`. That matters, because the first attempt seeded
`body_arch` over RPC, the form loaded clean, and the save button — present in the
DOM but hidden behind `o_form_status_indicator_buttons.invisible` — could not be
clicked. A read-back of the RPC-seeded value would have scored a pass while
exercising neither rule, since both are the save seam.

`body_html` is the half the row insists on and it is the one that leaves the
installation: `commitChanges` builds it separately from a clone run through
`toInline`, so it never passes `getEditingValue`. It reads back `CLEAN`.

**Rules 9 and 10 stay unreachable, with #238's own reason, not re-derived here.**
They strip the two `record.update` calls in the *legacy* `toggleCodeView`, bounded
by `codeview: Boolean(odoo.debug && options.codeview)`, and no shipped view sets
that option on a legacy-editor field — the `codeview` views are plain `html` or
`html_mail` fields on the current editor. They are two lines and token writes, and
#238 recorded them as covered-anyway rather than as a Live check.

## #240 — the code view round trip

| Half | Reading | Verdict |
|---|---|---|
| a | code view toggled on then **off**: the re-inserted picture is `<INGRESS_BASE>/web/image/res.company/1/logo`, `loaded: true`, all four signals 0. Public: `<PUBLIC_BASE>/…`, loaded, signals 0. | **`PARITY`** |
| b | saved, then `ir.actions.act_window.help` read back: `CLEAN`, 0 prefixes, on both surfaces | **`PARITY`** |

`debug_here: '1'` and `codeview_buttons: 1` on both surfaces, and
`code_view_shown: true` — so the toggle was the real toolbar command and the OFF
click is the one that reaches `html_field.js:236`, the assignment the rules patch.

**Two corrections, both measured.**

- **Not the user signature, which is the screen #240's row names.** That row picks
  the signature *because* `html_mail` was the thing to avoid. On this build the
  signature is served by that widget anyway — the field wrapper reads
  `signature:o_field_widget o_field_html_mail o_field_html` — and its editor comes
  up **empty**, `editable_html` being
  `<div class="o-paragraph o-we-hint" placeholder="Type &quot;/&quot; for commands"><br></div>`
  with a fragment value present in the record. An empty editable has no text to
  select, so the floating toolbar is never raised and the `codeview` group never
  renders. The screen used is `ir.actions.act_window.help`, the other `codeview`
  view (`base/views/ir_actions_views.xml:230`, #158's field): a plain `html` field
  on the current editor, `sanitize_tags=True` so it cannot become a sandboxed
  preview, and the `oe-bordered-editor` class on the wrapper confirms it is that
  view.
- **`?debug=1` is not sticky across a navigation here.** After `/odoo?debug=1` the
  next page reported `odoo.debug === ""`; the `codeview` command was therefore
  never registered and the floating toolbar came up with seven groups —
  `font, decoration, color, font-size, list, link, ai` — and no code view. That
  reads exactly like a missing button. The flag belongs on the form navigation
  itself.

## #234 — the collaborative peer snapshot

| Pair | Prefixes | Transport | Stored | Verdict |
|---|---|---|---|---|
| `ingress-ingress` | **equal** (`prefixes_equal: true`) | **not delivered** (30 s) | `stored_prefixes: []` | **`CLEAN`** |
| `ingress-public` | A has one, B `null` | **not delivered** (30 s) | `stored_prefixes: []`, 2 root-relative `src` intact | **`CLEAN`** |

`report` prints `escalate_issue_234_to_blocker: false`. **#234 stays
`severity: important`.** Its own rule escalates only if a run reads a stored
prefix, and neither pair stored one — not the saver's own, not the other
session's, not one nobody claims.

The equality in the first row is the *reason* that pair is clean, and #234's
refinement asked for it to be recorded rather than assumed. It was measured, and
it holds: one add-on, one `ingress_token`, one prefix for both sessions.

**The limitation this run must be read with: the collaboration transport never
delivered, on either pair.** Session A's unsaved marker never reached session B in
30 s, so the two sessions never became collaboration peers. #234's own comment
says that absence is a finding of its own rather than a failed run, and the
records carry it in their `notes`. So these two `CLEAN` verdicts say **the save
path stores no prefix**; they do **not** say that a *delivered* peer snapshot
stores none. The capability #243 said was missing is now in the repo and has now
been run; what it has not yet done is observe a delivery.

The two-step the refinement asked for on `ingress-public` — read after the Public
peer saves, then save once under Ingress and read again — was not run as two
steps, because `do_run` saves on the receiving session and reads once. With
nothing delivered there was no foreign prefix to heal, so the healing half had no
subject. Recorded as owed.

**Annotated after the fact: during the `probe` steps one `ingress-public` probe
reported a `delivered: true` that was false, and #263 says why.** The table above
reads the two `run` records in `peer.jsonl`, which stage a marker minted from the
run id (`WOOW-PEER-20261002T015318Z-A`) and both correctly report
`delivered: false`; those are the records this section is written from and they do
not move. The `probe` steps that came before them staged the *constant*
`WOOW-PEER-PROBE`, and once the write recorded under **Writes** had stored that
string the next probe found it in the receiving session's editable on its first
poll — `"transport": {"delivered": true, "waited_seconds": 0.0}`, while the
same-surface pair had just waited the full 30 s and failed. Nothing was delivered:
`wait_for_transport` read the marker out of the *stored* value, not out of a peer
snapshot, which is what a constant marker costs — the step's whole argument is
that nothing has ever stored that marker, so its presence is the transport. Hence
the reading this run leaves behind for later ones: a `delivered` whose
`waited_seconds` is **0.0** is a shape to distrust. Not a shape to refuse — the
receiving session joins *after* the sender typed, so the snapshot it is handed can
legitimately carry the marker on the first poll. What made this one false was the
**baseline**, not the clock: the marker was in the loaded document before anything
was sent. #263 is what tells the two apart, and §12 of the parity plan carries the
convention.

## #239 — the media dialog's preselection

| Line | Screen | Reading | Verdict |
|---|---|---|---|
| 1, image | To-do description, dialog reopened on an image | Ingress: element `<INGRESS_PREFIX>/web/image/1393-…/woow-markup-fixture.png`, **4 tiles, 1 selected**. Public: root-relative element, **1 tile, 1 selected**. | **`PARITY`** |
| 3, document | the same screen, a document link | **unreachable** on the current editor — see below; premise measured instead | `STRUCTURAL` |
| 2, website | the website editor's Replace Media | **not exercised** — see below; both surfaces identical | `NOT-RUN` |

**Line 1 passes, and it carries a bonus measurement.** The run asked the page
whether the rule had reached the browser:
`rule_in_served_method: true` under Ingress and **`false`** on the Public origin,
with `__WOOW_INGRESS_MARKUP_OUT__` published as a function under Ingress. That is
a direct measurement that the rewrite lives **only** in the Ingress asset
location — the same thing check 3 says for #237, read from the other side.

**Getting line 1 to measure anything took three fixtures, and the first two are
worth recording because they are the shape of a false negative.** The onboarding
to-do's picture is `/project_todo/static/img/todo_access.png`, a **static module
asset** with no `ir.attachment` behind it; a `website.library_image_*` URL
attachment is listed by the dialog but was not what the element came from. In both
cases the dialog preselected none *correctly*, on both surfaces. `isInitialMedia`
only ever matches an attachment the dialog listed, so "none selected" is only a
finding when the other surface selected one for the same element. The fixture that
works is an attachment **scoped to the record** (`res_model='project.task'`,
`res_id=<the to-do>`), which is what `fetchAttachments` lists.

**Line 3 is unreachable on the current editor, and this is the row turning out
unreachable rather than failing.** There is no control that reopens the dialog on
a document: Replace is a toolbar item in the `image` namespace
(`media_plugin.js:50`) and a document is an `<a class="o_image">`, not an `<img>`;
double-click maps to `previewImage` for images only. So the dialog never opened
and the tile was never read.

Its premise was measured instead, and it holds on both surfaces. Rule 3 was never
broken because **both** operands arrive prefixed, and that is now a host reading
rather than a static argument:

| | Ingress | Public |
|---|---|---|
| element `href` | `<INGRESS_PREFIX>/web/content/1394` | `/web/content/1394` |
| served `fetchAttachments` literal prefixed | **true** | **false** |
| `.replace(/[?].*/)` present | true | true |
| served method length | 372 | 309 |

Prefixed against prefixed under Ingress, root-relative against root-relative on
the Public origin. The 63-byte difference is the prefix insertion. This is why no
`OUT` was shipped for that read and why a Static-tier test refuses one.

**Line 2 was reached but not exercised.** The `ReplaceMedia` snippet option opened
the dialog on both surfaces, but the only visible image on the home page is
`/web/image/website/1/logo/My%20Website` — a record-field image, not an
attachment — and its `data-original-src` is **`None`**. Rule 2's branch is
`if (this.props.media.dataset.originalSrc)`, so with no such attribute the branch
never executes. Both surfaces preselected 0 of their tiles, so there is **no
divergence** either; this is "nothing measured", not a gap. Two screens would
reach it, and both need a fixture this run did not build: a themed mailing snippet
image (`mass_mailing_themes` ships `data-original-src` in stored arch, delivered as
an HTML response, which is the only path on which it arrives prefixed), or a
website page whose stored arch carries the attribute.

**#239 cannot escalate in severity from any of this,** which its own row says:
nothing it measures is stored. Both halves that were measured agree with the
Public origin, and the unmeasured half is recorded as unmeasured.

## Ambient rows

**This run emits no `.ambient.json`, and that is a gap in the instrument rather
than a silence.** Since #256 the figure is the run's own, written by the adapter's
`crawl` and `open` beside their records. This run drove neither: #234's module and
the markup driver are not the adapter, and neither counts
`website.track` / `website.visitor`. The website-editor check navigates website
pages, so ambient rows were certainly written.

Read on the host after the run, which is the pre-#256 method and is weaker
evidence than the run's own figure: `website.track` **198**, `website.visitor`
**59**. No before-reading was taken on 0.4.10, so no delta can be stated. Follow-up
filed to give this driver the same accounting.

The guarantee, quoted the way ADR 0012's 2026-10-01 postscript (#227) requires: a
read-only Live run makes **no business writes**. It does not leave **zero rows**,
and never has on a database with `website` installed. This run was not read-only in
any case — see **Writes**.

## Writes

| Record | What changed | Why | Put back |
|---|---|---|---|
| `project.task` 5 `description` | the two `probe` steps left `WOOW-PEER-PROBE` twice; the two `run` steps each appended a run-marked `-B` marker | #234's row saves on the receiving session and reads the field back | yes — exported to `task5-description-after-probes.html` first, then both markers and both run markers removed; back to 5385 chars, 0 Ingress tokens |
| `project.task` 11, 12, 13 | created as scratch to-dos | #239's and #237's fixtures | yes — deleted |
| `ir.attachment` 1393, 1394 | created as record-scoped image and document fixtures | #239 lines 1 and 3 | yes — removed with task 11 |
| `mail.template` 42, 43, 44, 45 | created as scratch templates holding the full-HTML value | #237 check 2 | yes — all deleted |
| `mailing.mailing` 2 `body_arch`, `body_html` | seeded with a root-relative picture | #238 line 3 needs a sent mailing whose body has one; all four fixture mailings had empty bodies | yes — `body_arch` back to empty, `body_html` back to its 166 characters |
| `mailing.mailing` 3 `body_arch`, `body_html` | seeded, then saved from the designer | #238 lines 1 and 2 | yes — both restored |
| `ir.actions.act_window` 1 `help` | seeded with a root-relative picture, then saved from the code view | #240 both halves | yes — back to `False` |
| `res.users` 2 `signature` | seeded by the first #240 attempts, and by one diagnostic taken over `odoo shell` | the signature was #240's first screen before it proved unusable | yes — back to Odoo's default `-- <br>Administrator` |

No module, group, setting or add-on option was changed. No mailing was sent. No
payment was made. Nothing was confirmed. Verified after the run:
`FIXTURE_ATTACHMENTS_LEFT []`, `SCRATCH_TASKS_LEFT []`,
`SCRATCH_TEMPLATES_LEFT []`, all four mailings back to `arch_len 0 / html_len 166`
with 0 tokens, `ACTION1_help False`, and task 5 at 5385 characters with 0 Ingress
tokens.

**The `probe` subcommand writes, and its own docstring and
`docs/agents/live-tier.md` both say it does not.** That is a harness defect this
run found and it is filed as #263; the rows above are what it left.

**Annotated after the fact: the first row's two `probe` markers are a driver
defect, not a write this run's steps chose to make.** #263, filed from this run,
establishes the mechanism — `probe` types its marker into
`project.task.description` and then navigates away without saving, and the To-do
form persists the dirty editor's content on that navigation, so the field was
written whether or not the step intended it. The subcommand's own reasoning that
"only a save writes the field" does not hold on this form, and #263 is the fix.
The row above is **not** rewritten, because it is already true: it is what the run
left on the host and what it put back, which is what a Writes row is for. What
#263 changes is the attribution of its first cell — those two copies of
`WOOW-PEER-PROBE`, 32 characters and the 5417-against-5385 length this run
exported before cleaning, are the defect's writes rather than the row's run's.

## What this run does **not** say

- It does not say a **delivered** peer snapshot keeps the field clean. The
  transport never delivered on either pair, so #234's two `CLEAN` verdicts are
  about the save path only.
- It does not measure the `cssAssetId`-only branch of `HtmlViewer`, which has no
  screen on this host. That remains the Static tier's.
- It does not measure #239's rule 2 branch, nor #239's document tile, nor #238's
  rules 9 and 10. Each is recorded above with its reason.
- It does not state an ambient-row delta, only an absolute count read afterwards.
- Every browser step here executed for the first time in this run. Ten defects in
  the drivers were found and fixed during it; the verdicts above are from the
  records taken after those fixes, and every earlier attempt is still in
  `markup.jsonl`.
