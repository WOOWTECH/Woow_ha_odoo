---
status: accepted
date: 2026-10-04
---

# A stored prefix is never suppressed: mis-attribution is fixed at the write, or by attribution

A **Stored reading** is the half of a Live-tier check's verdict that answers
whether an Ingress prefix reached a write (`CONTEXT.md`). `stored_verdict`
judges every field a check hands it, and a `PREFIX-STORED` is promoted to that
check's whole verdict ahead of every other branch — ahead even of an unreadable
screen, which is #237 check 4's own rule: a prefix that reached a write is the
worst thing a run can find, so a run that could not read its screen but did
read the database must still report it.

#286 found the other edge of that rule. The markup driver's `mailing-editable`
check means its `body_html` reading to be **write-bounding** — a prefix there is
*this save* leaking. On a **Reclaimed row** whose second save stores only
`body_arch`, the field it reads back is the previous surface's leftover, so the
reading has quietly become **state-bounding** while its verdict still reads as
the first kind. The record then attributes to one surface a prefix the other
surface's save wrote, and on the Public origin — where a stored prefix means a
`sub_filter` leaked out of the Ingress asset location — it attributes it to the
surface where that verdict means something else entirely.

The obvious repair is to teach the verdict not to judge a field it knows to be
stale. **We rejected it.** Suppression is indistinguishable, in the code and in
the evidence, from erasing a stored prefix — and a prefix in that row genuinely
is in the database, put there by this run's earlier surface. A per-field
"do not judge" valve in the shared verdict core is a general mechanism for
losing the finding this module exists to surface, bought to fix one check's
accounting.

We decided: **a Stored reading is never suppressed. Mis-attribution is corrected
either at the write, so that what a check reads back is only ever what it wrote,
or by attribution, so that a record says which of the two kinds of reading it
carries — never by withholding a verdict from a value that has one.**

## Considered options

- **Correct the write** (chosen for #286). The check clears the field it is
  about alongside its seed, gated so that it only ever touches its own scratch
  litter, which makes a Reclaimed row behave exactly like a created one — the
  baseline every other reading already assumes. Local, and it leaves the verdict
  core untouched.
- **Correct by attribution** (the admissible general fix). A record says whether
  a prefixed value was this flow's write or the row's state, and both are
  reported. This is the shape the peer snapshot driver already uses for the
  neighbouring question of *whose* prefix a value carries — `classify`, whose
  rule is that "a prefix in a record is the harm whoever put it there" — and it
  is what the driver's three state-bounding readings want.
- **Suppress the judgement.** Rejected, above.
- **Stop reclaiming within a run.** Giving each surface its own scratch row
  removes the staleness at source, but it contradicts the reclaim's reason for
  existing: a row no later run recognises as its own becomes permanent litter.

## Consequences

A check whose Stored reading is write-bounding owes the discipline that makes it
so. It may not assume the field it reads back was untouched when it arrived —
a reclaimed fixture, a re-run under one `--run-id`, and `--surface both` against
one database all hand it a field that already holds this run's marker.

## Postscript (2026-10-04, #289): five read-back sites, not three

The decision above is unchanged. Its count of affected readings was wrong, and
the correction is worth recording because the number is what says how much of
this family #286's fix could reach.

The admissible option — **correct by attribution** — now exists. A flow declares,
per field, which kind of Stored reading it took; `evidence_record` pairs the
declaration with the value and refuses a value with no kind beside it. Five of
the markup driver's read-back sites take a **State-bounding** reading, not three:

| Site | Why the check did not write it |
|---|---|
| `readonly-plain` / `project.task.description` | It *requires* `has_description_history` and then reads that description back, so any prefix in it predates the run. |
| `mailing-readonly` / `body_arch`, `body_html` | `writes: False`; the body is readonly in the two states this check needs. |
| `media-document-mailing` / `body_html` | It discards the form on purpose and the read-back proves the discard worked. **Derived**, not declared: if the discard did *not* hold, the save that got through is what inlines this field, and a prefix in what it wrote is then the check's own. |
| `readonly-iframe` / `mail.template.body_html` under `--task-id` | The default branch creates the scratch template and seeds the value; the flag branch seeds nothing. |
| `mailing-editable` / `body_html` under `--mailing-id` | The clear this ADR chose for #286 is gated on the fixture carrying a scratch row, and the `given` branch has none — an ungated clear would blank a real campaign's body. |

The last row is where the two options meet: #286's write-side correction closes
this family on every row the driver owns, and attribution closes the one row it
does not. Neither subsumes the other.

Two things the postscript settles that the decision left open, both consistent
with it:

- **A State-bounding prefix still fails the run.** It is reported, counted, and
  still exits non-zero. A per-check "judge but do not fail" policy would be the
  suppression this ADR refuses, one layer out: the finding would still vanish
  from the exit code, the tally and the sweep gate. Attribution changes the
  *claim*, never the verdict — a check whose register row says `writes: False`
  was being printed as the author of a write, which on the Public origin is the
  leaked-`sub_filter` finding and a more serious statement than "this row has
  held a prefix since before the run".
- **Two kinds, not three.** `--task-id` and `--mailing-id` reach the second kind
  by a different road rather than making a third. Which road is a *reading*, and
  each of those sites already records it.
