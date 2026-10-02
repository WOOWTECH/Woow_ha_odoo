# The collaboration transport delivers, and a Public peer's save stores the Ingress prefix (#265)

**Result: both pairs delivered a peer snapshot, and the two readings that follow
from that are new. `ingress-ingress` is `CLEAN` **after a delivered snapshot** —
the statement #234's row has carried since 2026-10-02 but which no run had
actually made. `ingress-public` stored **`FOREIGN-PREFIX-STORED`**: the Public
peer's save put the add-on's Ingress prefix on both of the to-do's images, which
is #234's hole observed for the first time on a real host. The two-step healing
read then removed it — one Ingress save, both `src` root-relative again,
`healing.verdict: CLEAN`. `report` prints
**`escalate_issue_234_to_blocker: true`**, because #234's criterion is a
*confirmed* stored foreign token and this run confirmed one: the rule reads every
value the run read, not only the last. The heal is reported beside it
(`foreign_prefix_healed`), and `foreign_prefix_still_stored` is empty — the field
is clean now. **Whether #234's severity follows the confirmation or the
persistence is #234's decision, and this run does not take it.**

Why the transport never delivered before is settled rather than guessed, and it
was **this script's defect and not a host or configuration condition**: the
collaboration plugin joins the peer network on the editable's `focus` event and
nowhere else, and the receiving session was never focused. See **Why nothing had
ever been delivered** below. So there is no Approved divergence and no Structural
gap to register **for the non-delivery** — that conditional in #265 does not
apply. What the run did register is the Public peer's write, as `G-08` in §11 of
the parity plan. That row is deliberately **not** badged `STRUCTURAL`: §1.4
requires a Structural gap to name a path the Public surface carries instead, and
here the Public surface is where the write comes from, so there is nothing to
name. By §1.3 a confirmed Ingress token leak is a **Blocker**, and the row says
so with the heal and #234's open decision beside it.

Run on 2026-10-02 against the test host's Released add-on `1b7b4ce7_odoo18ce` at
**0.4.10** — the version #243's run measured, unchanged, and #265 needs no
Release — database **`odoo_parity`** (the 29 modules of #144). No deploy was made
and no add-on was restarted.

Driver:

    odoo18ce/tests/e2e_collab_peer_snapshot_live.py  probe / run / report
    odoo18ce/tests/e2e_parity_shared_layers_live.py  pcheck

| File | What it is |
| --- | --- |
| `peer.jsonl` | the two records this run's verdicts are read from, `woow.peer-snapshot.v1`, run `WOOW-PEER-20261002T064500Z` |
| `peer.ambient.json` | their ambient figure, one line per pair |
| `peer-first-attempt.jsonl` | the first attempt's two records, run `WOOW-PEER-20261002T062800Z`, kept because they are what was read — the `ingress-public` one carries a **void** transport reading, see **The first attempt** |
| `peer-first-attempt.ambient.json` | its figure, same shape |

`conservation.json` and `reconciled.jsonl` are absent for #243's and #235's
reason: this run drove the peer snapshot and not
`e2e_parity_shared_layers_live.py run` / `report`, so there is no planned set to
reconcile against. §10.6 of the parity plan records why the 76-item conservation
figure does not move for it, and §12 why this schema does not feed
`conservation`.

## P-Check

| ID | Result |
| --- | --- |
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` → 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = True |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: same login on both surfaces, db `['odoo_parity', 'odoo_parity']` |

Nothing in this measurement reads a website page, so P-5 does not decide any
verdict here; it is run and recorded because a Live run's readings are measured
against it whatever the run is about.

## Why nothing had ever been delivered

Established from the **deployed image** (`docker exec` on
`app_1b7b4ce7_odoo18ce`, `html_editor/static/src/others/collaboration/
collaboration_odoo_plugin.js`) and independently from the pinned
`.deb` (`ODOO_DEB_VERSION` 18.0.20260930) — the same bytes in both:

- `collaborative_trigger` is **unset** on every view that shows this field, so
  the plugin takes the `undefined` branch and registers a one-shot `focus`
  listener on the editable: `joinPeerToPeer` runs there and nowhere else
  (`:91-99`).
- A session whose `ptpJoined` is false **discards every signalling notification
  it receives**, the other session's `ptp_join` included (`:156-158`). There is
  no log, no console message and nothing in the DOM.
- The driver's sending session focused by accident, because typing needs a
  focused editable. The receiving session only loaded the form and read
  `innerHTML`, and its first focus was the `type_marker` *after* the 30-second
  wait had already expired.

So both of #243's pairs were predicted to time out by the source before the host
was involved. The three readings #265 asked to have established, all measured on
this run and all in the records:

| Question | Reading | Where |
| --- | --- | --- |
| Is `project.task.description` collaborative on this build? | **yes**, on both surfaces: `is_collaborative: true`, `plugin_present: true` | `collaboration.sessions.*` |
| Is the bus reachable under Ingress and on the Public origin? | **yes**, both: `bus_worker_state: "CONNECTED"`, `bus_connection_lost: false` | `collaboration.sessions.*` |
| Do the two sessions share the collaboration channel? | **yes**: both report `editor_collaboration:project.task:description:5`, and `shared_channel: true` | `collaboration.shared_channel` |

The option itself was read on the host over `odoo shell` as well, because "is it
configured" is a question about the database and not about a page:
`project.view_task_form2` (the view `/odoo/project.task/<id>` serves) and
`project_todo.project_task_view_todo_form` both carry
`options="{… 'collaborative': true …}"`, neither sets `collaborative_trigger`,
and `project`, `project_todo`, `html_editor`, `bus`, `mail` and `web` are all
installed. `ir.config_parameter` holds no `rtc` key, so the ICE servers come from
the client's hard-coded fallback; two sessions in one browser connect on host
candidates, which a local two-context WebRTC experiment in this container
confirmed before the host was touched.

## The two pairs

| Pair | Transport | Prefixes | Peer's save | Healing save | Final |
| --- | --- | --- | --- | --- | --- |
| `ingress-ingress` | **delivered** (0.0 s, `marker_pre_existing: false`) | **equal** (`prefixes_equal: true`) | `CLEAN`, `stored_prefixes: []`, both `src` root-relative | not performed, with its reason | **`CLEAN`** |
| `ingress-public` | **delivered** (0.0 s, `marker_pre_existing: false`) | A has one, B `null` | **`FOREIGN-PREFIX-STORED`**, `stored_prefixes: ["A"]`, both `src` under `/api/hassio_ingress/<ingress:A>` | `CLEAN`, `loaded_prefixes: ["A"]`, both `src` root-relative | **`CLEAN`** |

Both sessions on both pairs: `ptp_joined: true`, `ptp_created: true`,
`peers: 1`, `connected_peers: 1`, and four signalling posts to
`/html_editor/bus_broadcast` from each session (three from the Public one on the
second pair). The posts are counted off the wire rather than taken from the
client's own account of itself, which is the point of counting them: a session
that never joins is exactly the session whose claim to have joined is worth
least.

**On exit codes, and one thing that changed after these records were taken.**
`report` over the two records exits non-zero, because the escalation is `true`.
The two `run` invocations that produced them exited **0**: when they ran, the
escalation rule still read only the value each record ends with, and it was
corrected the same day after a review pointed out that a boolean named after
#234's rule was answering "no" to the very write #234 exists for. The records are
untouched by that correction — nothing about what is measured, written or read
back depends on it, only on how a verdict is counted — so they are not re-taken.
A `run --pair ingress-public` on this host now exits non-zero, which is the signal
rather than a fault in it: the command has just measured a Supervisor token
reaching a record. `run --pair ingress-ingress` exits 0.

**`waited_seconds: 0.0` is the legitimate case here, and the baseline is what
says so.** The receiving session joins *after* the sender has typed, so the
snapshot it is handed can carry the marker on its first poll. What made #243's
one false reading false was the baseline, not the clock (§12 of the parity plan,
#263). On this run the marker was not in the loaded document
(`marker_pre_existing: false`) and the marker itself is unique to the run **and
the pair**, which is the fix the first attempt forced.

### `ingress-ingress` — CLEAN after a delivered snapshot

The sentence #234's row has carried since #243's run, now actually measured. The
receiving session held the sending session's whole document, saved it, and the
stored value has no Ingress prefix in it: the strip ran on a value that arrived
over the transport and not merely on a value the same session had loaded. The
prefix equality that makes this pair clean by construction is recorded again
(`prefixes_equal: true`) rather than assumed.

### `ingress-public` — the write #234 is about, measured

The Public origin serves no Runtime shim and no rewrite (ADR 0003 keeps it the
control group), so the snapshot it is handed is stored as it arrives. Both of the
to-do's images were stored as
`src="/api/hassio_ingress/<ingress:A>/project_todo/static/img/…"`, which is the
add-on's `ingress_token` — not a session secret, but a Supervisor token in a
database row all the same. `stored_prefixes: ["A"]`, and the label is the Ingress
session's because both sessions on this host are served the one add-on token; the
write is the Public peer's.

Then the second reading ADR 0004 asked for and #243 could not take: the Ingress
session discarded its own leftover, **reloaded the record** so that its editor
held what the Public peer had stored (`loaded_prefixes: ["A"]`, the reading that
says the healing save had a subject), typed its marker and saved once. Both `src`
came back root-relative. That is the strip of #234 doing the one thing it can do
on this pair — healing the record on the next Ingress save, which ADR 0004 said
in advance it cannot replace with prevention.

**What that leaves, and this run does not decide it.** Between the Public peer's
save and the next Ingress save the token is in the row, and in a record no Ingress
session saves again it stays there. #234's own acceptance criterion says a
*confirmed stored foreign token* makes it `severity: blocker`, so
`escalate_issue_234_to_blocker` is **`true`**: the rule reads every value the run
read, because a prefix the run removed afterwards was still confirmed in the
record, and a rule that only looked at the end of the run would answer "no" to the
measurement that proves the escape exists. What the report puts beside it rather
than inside it: `foreign_prefix_healed` (this one was removed) and
`foreign_prefix_still_stored: []` (nothing is in the field now). Which of the two
#234's severity follows is that issue's decision — the run reports both and takes
neither. Registered as **`G-08`** in §11 of the parity plan so it is not only in
this directory.

*Noted the same day, after this run: **#234 has taken that decision — it stays
`severity: important` and stays closed.** It reads the persistence: the token
entered the row and the next Ingress save removed it, which is the whole of what
that fix was ever claimed to do. What stays open is the shape the fix cannot cover,
which is `G-08`'s and not #234's — a record a Public-origin peer wrote and that no
Ingress session ever saves again. The readings above are unchanged; this run still
reports both and the row carries both.*

## The first attempt

`peer-first-attempt.jsonl`, run `WOOW-PEER-20261002T062800Z`. Its
`ingress-ingress` record reads the same as the final run's. Its `ingress-public`
record carries `"delivered": false` with `"marker_pre_existing": true`, and that
is a **void** reading and not a negative one: a run is one `--run-id` over both
pairs, `run` stores its marker, so the second pair opened a record that already
held the first pair's `<run-id>-A`. `await_marker` refused the match without
waiting — the guard #263 added, working — and the transport was therefore not
measured at all on that record.

The record is kept because it is what was read, and because it carries the same
`FOREIGN-PREFIX-STORED` on the Public peer's save and the same healed `CLEAN`
after it: the snapshot plainly *had* been delivered, since two prefixed `src`
could only have come from the Ingress session's editable. Only the measurement of
delivery was void. Two changes came out of it, both in the final run: the marker
carries the pair as well as the run id, and `transport_diagnosis` has a
`marker-collision` rung — the attempt's own record says `"cause":
"unattributed"`, which was the diagnosis before that rung existed and reads as a
mystery beside two sessions that were plainly connected.

## Ambient rows

| Attempt | Pair | `website.track` | `website.visitor` | Navigations |
| --- | --- | --- | --- | --- |
| final | `ingress-ingress` | 198 → 198, **+0** | 59 → 59, **+0** | 2 |
| final | `ingress-public` | 198 → 198, **+0** | 59 → 59, **+0** | 3 |
| first | `ingress-ingress` | 198 → 198, **+0** | 59 → 59, **+0** | 2 |
| first | `ingress-public` | 198 → 198, **+0** | 59 → 59, **+0** | 3 |

Both `probe` steps printed the same figure on stderr and kept no file, which is
what `probe` does (#264): `website.track +0, website.visitor +0 over 2
navigation(s)`.

Read the `navigation_basis` in the file before comparing these with another
driver's: this one counts every document GET either session's browser context
made under its own base, which is an upper bound on page views. The expected
delta is zero — this driver opens `/odoo/project.task/5` and nothing else, and a
backend route renders no tracked page — and a zero that is read is a reading
while a zero that is assumed is not. The `ingress-public` denominator is 3 rather
than 2 because the healing read navigates the Ingress session back to the record.

Not zero rows, which is not what a read-only Live run promises in the first
place: see ADR 0012's postscript of 2026-10-01 (#227). This run is not read-only
anyway — it writes the field on purpose.

## Writes

Inside the ADR 0012 boundary, on `odoo_parity`, all of them to
`project.task(5).description` — the test user's own onboarding to-do. No record
was created, none was deleted, no setting was changed and the add-on was not
restarted.

| What | Which step |
| --- | --- |
| the receiving session's save, twice per attempt | `run`, both pairs — this is the measurement |
| the Ingress healing save, once per attempt | `run --pair ingress-public` — the second half of the measurement |
| nothing at all, four times | the four `probe` steps: `wrote_nothing: true` on each, and the host read below confirms it from the other side |

**Host state this run leaves**, read back over `odoo shell` after the last write:
`project.task(5).description` is 5762 bytes, holds **zero** Ingress prefixes, and
both `src` are `/project_todo/static/img/…` — the healing save was the last write
and the field is clean. It holds eight markers, every one named after the run
that typed it:

    WOOW-PEER-20261002T062800Z-A                       (first attempt)
    WOOW-PEER-20261002T062800Z-A-heal
    WOOW-PEER-20261002T062800Z-B
    WOOW-PEER-20261002T064500Z-ingress-ingress-A       (final run)
    WOOW-PEER-20261002T064500Z-ingress-ingress-B
    WOOW-PEER-20261002T064500Z-ingress-public-A
    WOOW-PEER-20261002T064500Z-ingress-public-A-heal
    WOOW-PEER-20261002T064500Z-ingress-public-B

They are left where they are, the way #183's fixtures were: a run's data is named
after the run so the host stays readable, and deleting it to make the host look
untouched is what ADR 0012 says not to do. No `WOOW-PEER-PROBE-` marker is in the
field, which is the independent confirmation that the four `probe` steps wrote
nothing — #263's own defect would have left four.

## What this run does **not** say

- It does not say the Public peer's write is **prevented**. It is not, it cannot
  be from the Ingress side, and ADR 0004 said so before the measurement. What is
  measured is that one Ingress save removes it.
- It does not say a record nobody opens under Ingress again is clean. The heal
  needs an Ingress save to happen; until it does the token is in the row. That is
  `G-08`, and the severity question it raises for #234 is left to #234.
- It does not re-measure anything else in the markup family. #243's five rows
  stand as that run recorded them; the only row this run touches is #234's, and
  it annotates #243's evidence rather than rewriting it.
- It says nothing about a third peer, a guest session, or the project sharing
  portal's own form (`project.project_sharing_project_task_view_form`, which also
  sets `collaborative: true`). Two sessions on one record is what the driver
  opens.
