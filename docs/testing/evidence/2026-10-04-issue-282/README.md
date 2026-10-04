# What #263-#292 left unverified, measured (#282)

**Result: the eight driver fixes of the 2026-10-02/04 block hold on a real host,
and the two readings that were only ever asserted are now taken.** `mailing-editable`
records `mailing_source: created` on the first surface and `reclaimed` on the
second, with `body_html_marker_before: true` **and** `body_html_inlined: true` on
the reclaimed row — the two-way reading #279 alone could not give and #286's clear
is what makes possible — and both its stored fields read `reading: write-bounding`.
`media-document-mailing` records `discarded: true` on the mail designer on both
surfaces, so #280's three-valued reading and #288's `root_now` seam are exercised
where the confirmation pays the whole `commitChanges` inlining pipeline. #277's
two-run sequence strands an attachment and then reclaims it: `reclaimed_attachment_ids:
[362]`, `reclaimed_attachments_removed: true`, and the host read afterwards finds
attachment 362 **gone**. All 18 read-back records carry a per-field
`reading` kind (#289), including `media-document-mailing`'s derived one. The hand
checks wrote their **first** `.ambient.json` (`visit`: `website.track` **+1** over 1
navigation — the figure that is the measurement), and the peer snapshot's
`discard_form` reports `dirty: true` with `discarded: true` on the session that
typed (#292), with no `WOOW-PEER-PROBE-` marker on the host afterwards.

**Two findings this run turned up, neither of them in the eight fixes**: a
`readonly-plain` picture **`ESCAPED`** on the Public origin, because two of
`project.task(5)`'s 17 html-field history revisions carry an Ingress prefix —
registered as **`G-10`**, and the mechanism is the one #296's triage established
rather than the one this README first stated: a revision's patch is a *reverse*
patch, so the entry carrying the prefix is written by the Ingress save that
**healed** the field (§`G-10`); and `codeview`'s success-path restore is gated on
`--cleanup`, so this run's first invocation left a real `ir.actions.act_window.help`
replaced until it was put back by hand (§"Host state", and follow-up filed).

Run on 2026-10-04 (UTC) against the test host, **no Release and no add-on build**:
every fix measured here is in a driver, which runs locally against the add-ons
already installed.

| Surface set | Add-on | Version | Database | Run id |
|---|---|---|---|---|
| Ingress **and** Public | `1b7b4ce7_odoo18ce` (the Release) | `0.4.10` | `odoo_parity` | `WOOW-MARKUP-20261004T104350Z` |
| Ingress only (no `public_url`) | `local_odoo18ce` (local build) | `0.4.10-202610031232` | `catchup164b` | `WOOW-MARKUP-20261004T111302Z` |
| Ingress (hand checks) | the Release | `0.4.10` | `odoo_parity` | `WOOW-PARITY-20261004T111809Z`, `…T111826Z` (each minted) |
| Ingress ×2 / Ingress+Public (peer) | the Release | `0.4.10` | `odoo_parity` | `WOOW-PEER-PROBE-20261004T112015Z`, `…T112126Z`, `WOOW-PEER-20261004T112233Z` |

Both containers run the same pinned Odoo package, `18.0.20260930`, which is the
`.deb` every Static-tier fixture in this block was derived from.

**This run mutates and was taken with explicit approval**, outside the pre-approved
read-only boundary of [ADR 0012](../../../adr/0012-sweeps-verify-on-the-test-host.md).

## P-Check (the Release add-on, `odoo_parity`)

| ID | Reading |
|---|---|
| P-1 | PASS `public_url` is https |
| P-2 | PASS GET `/web/login` → 200 |
| P-3 | PASS `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS `web.base.url.freeze` = True |
| P-5 | PASS `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS same login on both surfaces, db `['odoo_parity', 'odoo_parity']` |

There is no P-Check for the local build, for #271's reason: `pcheck` reads
`ODOO_PUBLIC_URL`, which is the **Release** add-on's origin and a different
database. What stands in its place is the version table above plus the local
build's own `operand` readings quoted under item 3.

| File | What it is |
|---|---|
| `markup.jsonl` | 21 records, `woow.ingress-markup/v1` — the full check set on `odoo_parity`, both surfaces |
| `markup.ambient.json` | 21 lines, one per record |
| `markup-local.jsonl` | 3 records — the `created` branch and #277's reclaim, on `catchup164b` |
| `markup-local.ambient.json` | 3 lines |
| `hand-checks.jsonl` | 2 records — `visit` and `editbtn` |
| `hand-checks.ambient.json` | **2 lines — this driver's first ambient figure ever** (#264, item 2) |
| `peer.jsonl` | 1 record, `woow.peer-snapshot.v1` — `run --pair ingress-ingress` |
| `peer.ambient.json` | 1 line |
| `peer-probe-ingress-ingress.json`, `peer-probe-ingress-public.json` | the two `probe` outputs; `probe` keeps no records file |
| `peer-probe-*.ambient.txt` | each probe's figure, which it prints on stderr rather than writing (#264) |

`conservation.json` and `reconciled.jsonl` are absent for #243's, #265's, #266's
and #271's reason: this run drove the markup, hand-check and peer drivers and not
`e2e_parity_shared_layers_live.py run` / `report`, so there is no planned set to
reconcile against. §12 of the parity plan records why these schemas do not feed
`conservation`, and §10.6 why the 76-item figure does not move.

## Item 1 — the markup driver, per issue

### #276, #274 — a check that builds what it measures

| Reading | Where |
|---|---|
| `mailing_source: created`, `mailing_reclaimed: false`, subject `WOOW scratch (delete me) WOOW-MARKUP-20261004T104350Z` | `mailing-editable` / `ha_ingress`, `odoo_parity` |
| `mailing_source: created` on a database with **no mailing at all** (`mailings 0` before the run) | `mailing-editable` and `media-document-mailing`, `catchup164b` |
| `mailing_source: found`, mailing 3, `body_restored: true` | `media-document-mailing`, `odoo_parity` — the borrow branch, still reachable |
| `typed: true`, `save_visible: true`, `saved: true`, `unsaved_after_save: false` | every `mailing-editable` record |

`created` and `found` in one run is what shows the `borrow` flag deciding anything:
`mailing-editable` passes `borrow=False` and created its own row on **both**
databases, while `media-document-mailing` on `odoo_parity` borrowed draft mailing 3
and wrote its body back. #274's `email_from` `NOT NULL` trap is exercised where it
bites — on `catchup164b`, where there was no mailing to find, both checks created
one and saved.

### #277 — a reclaim takes the attachments its body links with it

The deliberate two-run sequence, on `catchup164b`, both runs under one run id:

1. `media-document-mailing --surface ingress` (**no** `--cleanup`) → `mailing_source:
   created`, mailing 2, `fixture.attachment_id: 362`, body linking `/web/content/362`.
   Left on the host on purpose.
2. the same command **with** `--cleanup` → `mailing_source: reclaimed`,
   `mailing_reclaimed: true`, `reclaimed_attachment_ids: [362]`,
   `reclaimed_attachments_removed: true`, its own new attachment 363, and
   `fixture_removed: {"attachment": true, "mailing": true}`.
3. the host read afterwards: `attachment 362 exists: False`, `363: False`,
   `woow-%` attachments left **0**, mailings on `catchup164b` back to **0**.

The stranded attachment is the one no fixture dict of the reclaiming run holds, and
it is gone, named by the record that removed it.

### #279, #286 — the recorded and the judged half of a reclaimed row's `body_html`

`mailing-editable --surface both` on `odoo_parity`, **without** `--cleanup` between
the surfaces, so the second surface's `scratch_mailing_id` reclaims the first's row:

| | surface 1 (`ha_ingress`) | surface 2 (`public`) |
|---|---|---|
| `mailing_source` | `created` | **`reclaimed`** |
| `body_html_marker_before` | `false` | **`true`** |
| `body_html_inlined` | `true` | **`true`** |
| `stored["mailing.mailing.body_html"].reading` | `write-bounding` | **`write-bounding`** |
| `stored_verdict` | `CLEAN` | `CLEAN` |

Read the second column with #279's and #286's mechanisms side by side. The marker
*was* in `body_html` before the second save — `body_html_marker_before: true`, the
key #279's review added where the reading is taken — so the question "did rule 8
run" cannot be answered from the field's contents alone. #279 made the judgement
"**newly** present"; on a reclaimed row that made it one-way, `false` whichever way
the save went. #286's clear is what makes it two-way: the seed writes
`body_html = False` in the same `write` that seeds `body_arch`, gated on the fixture
carrying a scratch row, so the baseline is empty and `body_html_inlined: true` means
*this* save inlined. And the judged half moves with it: `reading: write-bounding` on
a reclaimed row is only honest because the value read back is this save's own output
(#289's gate derives the same answer from `fixture["seeded"]`).

A third invocation, `--surface ingress --cleanup` under the same run id, reclaimed
the leftover row and removed it: `mailing_source: reclaimed`,
`fixture_removed: {"mailing": true}`, and the host shows `scratch []` with
`mailings [3, 4, 2, 1]` — the four `odoo_parity` had before this run.

### #280, #288 — the discard seam, on the mail designer

| Reading | Where |
|---|---|
| `discarded: true` | `media-document-mailing`, **both** surfaces on `odoo_parity` and both invocations on `catchup164b` (4 records) |
| no `discarded` key | all four `codeview` records, and every `mailing-editable` record — the form was clean by then, which is #280's third reading ("nothing to discard") and not a failure |
| `stored_verdict: CLEAN` on the read-back that follows the discard, with `body_restored: true` | `media-document-mailing`, both surfaces |

`discarded: true` means the form came clean, confirmed by waiting for `UNSAVED` to go
hidden — and on the mail designer that wait pays the whole `commitChanges` pipeline
(`record.js:183` → `html_field.js:78` → `mass_mailing_html_field.js:147-186`). So
**`DISCARD_CLEAN_TIMEOUT` (15 s) was enough on a loaded host**, which is the half the
Static-tier test cannot say: it pins the *relation* to the save path's own
`settle(6000)` budget, not the sufficiency of the number. Had it been short, the
record would have read `discarded: false` with the body changed, and none of the four
did.

#288's seam is exercised in the same records: the discard resolves `side.root_now`
once and no longer settles before the read-back. The read-back is `CLEAN` on all four,
and the host read afterwards shows every mailing back to its own body with **0**
`hassio_ingress` occurrences in any mailing body — which is the argument #288 made
(the confirmation has already drained `_askChanges`, so any save through the model's
mutex had landed) measured rather than reasoned.

### #289 — a Stored reading says which kind it is

All 18 read-back records carry a per-field `reading`. The declarations
as a host read them:

| Check / surface | Field | `reading` | Why that is the right one |
|---|---|---|---|
| `readonly-plain` both | `project.task.description` | `state-bounding` | the check's register row says `writes: False`; it is the witness |
| `mailing-readonly` both | `body_arch`, `body_html` | `state-bounding` ×2 | same, and the only run that has ever exercised **this** site (see below) |
| `readonly-iframe` both | `mail.template.body_html` | `write-bounding` | no `--task-id`, so the scratch template is its own |
| `codeview` ×4 | `ir.actions.act_window.help` | `write-bounding` | seeded and saved by the check |
| `media-document-mailing` ×4 | `body_arch` / `body_html` | `write-bounding` / **`state-bounding`** | one check, one field of each kind — the register's flag cannot express it |
| `mailing-editable` ×4 | `body_arch` / `body_html` | `write-bounding` / `write-bounding` | the gate: a row this check owns, so #286's clear applies |

`media-document-mailing`'s is the **derived** one, and it derived correctly: the
discard held on all four records (`discarded: true`, `after == before`), so the field
it never writes reads `state-bounding`. Had the discard not held, the save that got
through is exactly what inlines `body_html`, and the same code would have said
`write-bounding`.

The guard also held: `evidence_record` raises for an undeclared field, a declaration
naming a field never read back, an unknown kind, or a `write-bounding` claim from a
`writes: False` check — and every surface of every check wrote a record, so no
handler was refused.

**`mailing-readonly` ran, which #282's own text did not expect.** The issue put this
check out of scope as `NOT-RUN` "without a sent mailing"; `odoo_parity` carries two
mailings in state `done`, so `sent_mailing_id` found mailing 2 and the check ran on
both surfaces. That is what exercised #289's second declaration site. Its screen
verdict is `ABSENT` on both surfaces, and the cause is the fixture rather than the
prefix: those two mailings are `e2e_parity_outbound_live.py`'s, their `body_html` is
166 bytes of one paragraph and two links, and `<img` appears **0** times in either.
#243's run read a `res.company` logo there because its own attempt had seeded a body
with one; that body was restored afterwards. So `ABSENT` is "this record has no
picture to judge", recorded rather than hidden.

### #243 / #266 reproduced, and the one that changed

| Check | #243 / #266 (0.4.10) | this run | Reading |
|---|---|---|---|
| `readonly-iframe` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced |
| `codeview` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced, with `help_restored: true` |
| `media-image-todo` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced |
| `media-image-website` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced |
| `media-document-todo` | NOT-RUN (unreachable by construction) | NOT-RUN | reproduced |
| `media-document-mailing` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced |
| `mailing-editable` | UNDER-PREFIX / AT-ORIGIN-ROOT | UNDER-PREFIX / AT-ORIGIN-ROOT | reproduced on a built mailing |
| `mailing-readonly` | UNDER-PREFIX / AT-ORIGIN-ROOT (#243, on a seeded body) | ABSENT / ABSENT | **changed** — the fixture has no picture (above) |
| `readonly-plain` | UNDER-PREFIX / AT-ORIGIN-ROOT (#243, on task 11) | UNDER-PREFIX / **ESCAPED** | **changed** — `G-10` (below) |

`report` on `markup.jsonl`: **13 passed, 3 failed** from 21 attempts
(`mailing-readonly` ×2 `ABSENT`, `readonly-plain/public` `ESCAPED`),
`stored_prefix_found=no`. On `markup-local.jsonl`: **2 passed, 0 failed** from 3
attempts, with the other seven checks `not run` — deliberate, the brief put only the
two mailing checks on the local build.

## `G-10` — the html-field history keeps a prefix no save can heal

`readonly-plain`'s screen is the html field's **history dialog**, and on the Public
origin both of its pictures read:

    attribute: /api/hassio_ingress/<redacted>/project_todo/static/img/todo_access.png
    resolved:  <PUBLIC_BASE>/api/hassio_ingress/<redacted>/…
    loaded:    false        verdict: ESCAPED

while the stored `description` the same record judges is `CLEAN` with **0** prefixes
and `reading: state-bounding`. The Public origin has no mechanism that could add an
Ingress prefix, so the only source is the stored revision — and the host read
confirms it:

    project.task(5).html_field_history: 17 revisions for `description`
      2 of them carry `hassio_ingress` (2 hits each — the two images)
      revision 13, 2026-10-02T06:29:43, Administrator
      revision 16, 2026-10-02T06:36:32, Administrator

Those two timestamps are #265's run window.

**Which write deposited them was read wrong here first, and #296's triage corrected
it against the pinned package.** `html.field.history.mixin.write` stores
`generate_patch(new_content, old_content)`, and `_patch_generator` embeds
`old_content_lines`: the patch is a **reverse** patch, the one
`html_field_history_get_content_at_revision` applies to walk the current value
*backwards*. So a revision carries the value as it was **before** that write. Run
against the pinned `.deb`'s own `diff_utils`:

    generate_patch(clean, prefixed)  -> patch contains the prefix   (the heal)
    generate_patch(prefixed, clean)  -> patch does not              (the peer's store)

So the sequence is: the Public-origin peer stores the prefix in the **field**
(`G-08`), and that write records a *clean* revision; the next Ingress save strips the
field (#234) and **that** write is what deposits the prefixed revision. The heal is
the author of this residue, not a bystander to it — which also means it recurs once
per `G-08` store-and-heal cycle rather than being a historical accident, and that
this run's clean revision 17 proves nothing about the current code: it came from the
`ingress-ingress` pair, which had no prefix to heal.

It is not permanent either: `_html_field_history_size_limit = 300` caps the list per
field, so the residue is evicted after 300 further revisions of
`project.task.description` — which is the **only** versioned field in the pinned
package (`project.task._get_versioned_fields` returns `[description]`, and no other
model inherits the mixin).

Registered as `G-10` in §11 of the parity plan with the measurement above. What it
bounds in `G-08` is narrower than "the next Ingress save heals it is false": the heal
is real and the field is clean, and what the heal also does is leave one prefixed
entry behind it. #296's triage keeps `G-10` at `important` and recommends **no**
re-grade for `G-08`, because this is `G-08`'s one write seen in a second store and
must not be counted twice.

This is also the clearest thing #289 bought: `readonly-plain` is declared
`writes: False`, and the record says `state-bounding`, so the run reports a prefix it
witnessed rather than one it is the author of.

## Item 2 — the hand checks' ambient figure exists

`e2e_ingress_hand_checks.py` had never written an `.ambient.json`; it has now.

| Invocation | `website.track` | `website.visitor` | navigations | What it says |
|---|---|---|---|---|
| `visit` | **+1** (200 → 201) | +0 (61 → 61) | 1 | the figure **is** the measurement: `visit` exists to make the tracking write, and one page view wrote exactly one row |
| `editbtn` | +2 (201 → 203) | +0 | 6 | the contrast: a subcommand documented as writing **nothing** still serves two tracked pages, which is precisely the distinction ADR 0012's postscript draws |

`website.visitor` is +0 on both because the visitor row for this session's user
already existed; `navigation_basis` in the file says why 6 navigations can produce 2
rows (redirect hops and the editor's own preview fetches are counted and render no
tracked page). `todosave` was not run: #282 asks for `visit`, and `todosave` would
write a real record's `description` for a figure the other two already demonstrate.

## Item 4 — the peer snapshot's discard seam (#292, #288)

Two probes and one `run`, on `odoo_parity`:

| Invocation | Reading |
|---|---|
| `probe --pair ingress-ingress` | exit **0**; `transport.delivered: true`, `waited_seconds: 0.0`, `marker_pre_existing: false`; `discarded: {"A": {"dirty": true, "discarded": true}, "B": {"dirty": false, "discarded": false}}`; `wrote_nothing: true`, `forms_left_dirty: []` |
| `probe --pair ingress-public` | exit **0**; the same four readings, `prefixes_equal: null` (one prefix per surface) |
| `run --pair ingress-ingress` | `verdict: CLEAN`, `final_verdict: CLEAN`, `stored_prefixes: []`, `transport.delivered: true`, `healing.performed: false` with the `ingress-ingress` reason; `report` exit **0** |

`A` is the session that typed, and `dirty: true` with `discarded: true` beside it is
the pair #292's fix protects: before it, `discard_form` reached for `side.root` three
times, and a re-mounted Ingress iframe made the entry read answer from a clean
replacement frame — `dirty: false`, "the form was never dirty", for a form that went
with its frame at the moment `beforeunload` fires. No record carries an `error` key,
which is `discard_quietly`'s fail-closed path and not the reading of a working run.
`B` is `dirty: false` because a received peer snapshot does not dirty the form, so it
has nothing to discard — #280's no-key reading in the sibling seam's vocabulary.

The independent confirmation is on the host: `project.task(5).description` holds **0**
`WOOW-PEER-PROBE-` markers after both probes, which is the shape #263's reading took
and the only external proof that the entry read came from the right frame. The field
holds 10 markers, every one named after the run that typed it, two of them this run's
(`WOOW-PEER-20261004T112233Z-ingress-ingress-A` and `-B`), and **0** Ingress prefixes.

`run --pair ingress-public` was **not** repeated. #265 measured it on this same
Release and that is the pair whose exit code is non-zero by design (`G-08`); what
#282 owes here is the discard reading, which `ingress-ingress` takes without storing
a foreign prefix to heal. Said plainly so nobody reads the absence as a pass.

## Item 3 — still deferred, and this run says what it would cost

#271's fix is in `main` and in **no Release**, and the two surfaces still read
differently on the same database because they are served by two add-ons:

| Reading | Release 0.4.10, Ingress | Release 0.4.10, Public | local build, Ingress |
|---|---|---|---|
| `operand.served_domain_asset_exclusion_prefixed` | `true` | `false` | **`false`** |
| `operand.served_domain_length` | 383 | 320 | **320** |

So the equality #271's issue body asked for — one run, one database, two surfaces,
equal — is still spread over two add-ons, exactly as the plan records. This run
reproduces both halves on the same day, which is new, and changes nothing about the
decision: **do not cut a Release for it**; fold `media-document-mailing --surface
both` into whatever owed-rerun set the next Release carries. Recorded as deferred
with #282's number beside it.

## Host state this run leaves

Read back over `odoo shell` on both containers after the last write.

| Reading | `odoo_parity` | `catchup164b` |
|---|---|---|
| scratch mailings (`WOOW scratch%`) | none | none |
| mailings | `[3, 4, 2, 1]` — the four it had | `[]` — none, as before |
| mailing bodies carrying `WOOW-MARKUP` | 0 | 0 |
| this run's fixture attachments | none (`woow-%` → 0) | none (`woow-%` → 0) |
| this run's scratch tasks / pages / views | none / none / 0 | — |
| `ir.actions.act_window(1).help` | `''` — its pre-run value | — |
| scratch `mail.template` | none | — |
| `project.task(5).description` | 5852 bytes, **0** `hassio_ingress`, 0 `WOOW-PEER-PROBE-`, 10 run-named markers | — |

**One repair, named rather than hidden.** `codeview`'s success path restores the
borrowed `help` **only under `--cleanup`** (`do_codeview`: `if cleanup:
write_field(…, before or False)`), while its error and interrupt paths restore
unconditionally. The first invocation of this run was taken without `--cleanup`, so
`ir.actions.act_window(1).help` — a real record, "Load demo data" — was left holding
this run's marker and logo. It was read, written back to `''` over `odoo shell`
(its pre-run value, which `help_before: ""` in the same record independently
attests), and the check was then re-run **with** `--cleanup`, which recorded
`help_restored: true` on both surfaces and left the field `''`. The asymmetry is a
defect in the driver rather than in this run, and is filed as a follow-up; both the
unrestored and the restored records are kept in `markup.jsonl`, because they are what
was really read.

Pre-existing litter left alone, the way #183's and #265's evidence left theirs: 32
`WOOW-PARITY-…` attachments, 6 `WOOW-PARITY-…` tasks and 4 `/woow-parity-…` website
pages from the 2026-09-25/28/29 adapter runs, and the 8 older peer markers in task 5.
A run's data is named after the run so the host stays readable; deleting it to make
the host look untouched is what ADR 0012 says not to do.

## Ambient rows, counted by the runs themselves

| Records | Lines | `website.track` | `website.visitor` | navigations |
|---|---|---|---|---|
| `markup.jsonl` (21) | 21 | **0** | 0 | 35 |
| `markup-local.jsonl` (3) | 3 | **0** | 0 | 3 |
| `hand-checks.jsonl` (2) | 2 | **+3** | 0 | 7 |
| `peer.jsonl` (1) | 1 | **0** | 0 | 2 |
| `probe` ×2 | printed, not written | 0 | 0 | 2 each |

One line per record in every case, which is the invariant #264 asked for. The
`website.track` absolute count runs 200 → 200 (markup) → 203 (hand checks) → 203
(peer), so the three drivers' windows chain without a gap. It is accounting and not a
verdict: `diff` never reads it and the conservation tally does not move for it.

## What this run does **not** say

- **#289's `report` sentence is unexercised.** `stored_prefix_found=no` on both
  record files: no field carried a prefix anywhere, so the line that names the kind
  (`PREFIX STORED by <check>/<surface> in <field> (state-bounding)`) never printed.
  What this run proves is the **declarations** and the guard, not the print path; the
  print path stays on the Static tier's twenty-seven tests, and manufacturing a
  prefixed stored value to see it would mean writing one into the database on
  purpose.
- **The interrupt path is unmeasured, deliberately.** #280's half 2 and #288's window
  are about a second Ctrl+C landing between the first and the restore, over a real
  `ir.actions.act_window.help`. Proving it in anger means arranging for exactly the
  outcome that leaves a marker on that record with nothing to put it back. The window
  is now a 2 s click bound and a 15 s confirmation with no `settle` and no waiting
  frame search in it, so what stays unmeasured is a timing claim, not a reading any
  verdict rests on.
- **`G-10`'s own fix is not attempted here.** The two prefixed revisions are left
  exactly as they are: they are #265's data, and rewriting a history store to make a
  screen pass is the opposite of what this family measures — #296's triage reaches
  the same conclusion from ADR 0014, and adds that the only ways into that field are
  a `super()` call past the mixin or SQL, neither auditable from the record.
- **The first version of this README had `G-10`'s mechanism backwards**, and said so
  in its headline: it read the Public peer's store as the writer of the prefixed
  revision. The readings are unchanged — the host numbers above are what was read —
  but the attribution is the heal's, and the correction is kept visible rather than
  quietly edited in, because the wrong version is what #296's body was filed on.
- **The 76-item conservation tally does not move.** `woow.ingress-markup/v1` and
  `woow.peer-snapshot.v1` do not feed `conservation`, and `G-10` is a §11 gap
  registration rather than a plan item. The figure stays **60 `PARITY` + 0 `GAP` +
  2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 8 `NOT-RUN`**.
- **No Release, no store Sync, no `ha apps update`, no local rebuild.** The local
  add-on was used exactly as #271 built it on 2026-10-03.
