---
status: proposed
date: 2026-09-22
---

# The Rewrite scan service never stops the container

ADR 0005 made the add-on run the Rewrite scan itself, ADR 0007 chose how
the bundles are read and ADR 0008 recorded how the findings are applied.
What was left was the thing that runs it: an s6 service that scans at start
and every five minutes thereafter, and reports each round in the add-on
log.

Every service in this image so far has carried the same `finish`: log an
error, then `exec /run/s6/basedir/bin/halt`. `postgres`, `odoo`, `nginx`
and `jsonrpc-filter` **are** the container — without any one of them the
add-on is not serving — so stopping and letting the Supervisor restart is
the honest answer to an unexpected exit. The Rewrite scan is the first
service that is not the container, and issue #77 says so directly: Odoo
starts and keeps running whatever the scan does.

## `finish` reports and returns; it does not halt

**We decided that `services.d/rewrite-scan/finish` logs the exit code with
`bashio::log.error` and then does nothing else, so s6 restarts the service
and the container keeps running.**

Copying the other four would mean that a Rewrite scan that could not read
one database, or a `psql` that hung until its timeout, stops a serving
Odoo. The two failures the scan actually has — an incomplete read and a
candidate nginx refuses — both already end with the last good include file
in place and every rule still live (ADR 0008). Restarting the container
over either of them would replace a cosmetic problem with an outage, and
it would do it in a loop, because whatever made the round fail is usually
still true a minute later.

- **No `finish` at all.** Rejected: s6 would restart the service silently,
  and an add-on that stopped updating its rules would look exactly like
  one with nothing to update. The error line is the only difference
  between the two from outside.
- **Halt after N consecutive failures.** Rejected: it needs state across
  restarts to count, and the thing it would eventually do — take Odoo down
  — is the thing #77 forbids. A round that keeps failing is a rule set
  that stops improving, not an add-on that stops working.

`finish` ends with `exec sleep 3`, which is the restart throttle. No round
can end the run script, so there are exactly two routes to `finish`:
PostgreSQL did not become ready inside the 30-second wait, which paces its
own restarts at about half a minute already; or the script itself could not
run, which has no pace of its own and without a pause would restart as fast
as the shell can fail. Three seconds is under s6's default `timeout-finish`
of five, so the pause is taken rather than cut off half way; if a future s6
shortens that, the only cost is a faster restart.

## A failed round is a warning, and the loop is the retry

**We decided that a round that exits non-zero is logged as a warning and
the loop simply runs the next round five minutes later.** There is no
retry of its own, no back-off and no attempt counter: the five-minute
interval already is the retry interval, and a second attempt straight away
would be a second attempt against the same database that was down a
second ago.

After repeated failure the service therefore keeps running, keeps writing
one warning every five minutes, and Odoo keeps serving with the Generated
rewrites it already had. That is deliberate. The add-on's rules are stale;
its Odoo is not affected. The operator sees a warning every five minutes
until the cause is fixed, which is louder than a single error at start and
quieter than a container that restarts in a loop.

The run script therefore has **no `set -e`**, unlike `services.d/nginx/run`
and every CLI in `usr/local/bin`. Under `set -e` the first round that
exited 1 would end the service, and the add-on would stop scanning for as
long as the container ran. This is the one place in this image where the
absence of `set -e` is the behaviour rather than an oversight, which is
why a Static-tier test asserts it.

## The service waits for PostgreSQL and for nothing else

**We decided to reuse the `pg_isready` loop from `services.d/odoo/run:7-19`
— 30 attempts, one a second — and to wait for nothing else.** A round
reads `ir_attachment` through `psql` (ADR 0007), so postgres is all it
needs. Waiting for Odoo's HTTP port, the way the nginx service does, would
put a scan between Odoo and its gateway, which is the opposite of what #77
asks for.

Where the Odoo service halts the container after 30 seconds without
PostgreSQL, this one exits and is restarted, and waits another 30 seconds.
Whether Odoo ever starts is that service's answer to give.

nginx is quite likely **not** running when the first round finishes: the
nginx service waits for Odoo's HTTP port first, and the scan does not wait
for either. The apply path already covers that — it writes and validates
the include file and skips the reload, and nginx loads the file when it
starts (ADR 0008, `nginx_master`).

## Every round says what it found, and what it could not read

**We decided that each round prints, in the add-on log: its status, the
status of every database (`ok`, `failed`, `no bundles`) by name, whether
the scan was complete, and — when bundles were actually read — a per-bundle
summary of the findings at each level with the exception hits and the
prefixes now in the include file.**

The per-database line and the explicit "incomplete" sentence are there for
one failure in particular. ADR 0008 refuses to apply an incomplete scan,
because the include file is the union over databases and a failed read
makes that union smaller. From outside, that refusal is indistinguishable
from an add-on that quietly stopped updating its rules. Naming the
database that failed and saying that nothing was added or removed is what
tells the two apart.

Coverage in the summary is measured against the Shipped rewrites alone,
the same way `generate_include` selects, so a `FAIL` row is exactly what
earns a Generated rewrite. Merging the generated rules in first would make
every rule the add-on wrote cover the finding that earned it, and the log
would read as though nothing was ever found.

**A round takes one pass over the bundles, not two.** The summary and the
include file want the same findings, and the obvious shape — generate from
the texts, then evaluate the texts again for the log — scans every bundle
twice and costs twice the four seconds ADR 0007 measured, on the rounds
that are already the expensive ones. `scan_bundles` therefore takes the
pass once and both halves are built from it, which is why
`literal_rewrite_gate.evaluate` was split into `evaluate_findings` plus a
wrapper. The selection is still `generate_include`'s own and is not read
off the summary: the summary drops what `is_covered` answers for one
literal in the quote it is written in, generation asks the coarser
`_shipped_covers` about the prefix, and the two differ for a CSS `url(/x)`
literal.

Every line goes through `mask()` (`literal_rewrite_gate.py:109`). A bundle
can hold an Ingress token, the `FAIL` and `WARN` rows carry the snippet
their finding was cut from, and a `psql` error comes back verbatim; the
add-on log is what gets pasted into an issue or a screenshot.

## Consequences

- The five services no longer share one `finish` convention. Which ones
  halt is now a question with an answer per service, and the Static tier
  pins both sides of it.
- Splitting `evaluate` changes `literal_rewrite_gate.py`, which is one of
  `rewrite_scan.ANALYSIS_MODULES`, so every host rescans once on the
  Release that ships this even though the classification is unchanged.
  That is `analysis_version` working as designed — it cannot tell a
  refactor from an improvement, and one extra four-second pass is the
  right price for never missing a real one.
- A round that reads bundles prints a block per bundle. On a host serving
  twenty bundles that is a long entry in the add-on log — but only on the
  rounds that actually scanned: with the state agreeing, a round is four
  lines and no pass at all (ADR 0007).
- The first round runs against the databases as they stand at start, before
  Odoo has served anything. Bundle attachments live in `ir_attachment` and
  survive a restart, so a restarted host scans the same bundles it had; a
  fresh install has no bundles and no rules, and neither is lost.
- Whether s6 honours a three-second `finish` in this base image, and what
  the log looks like over a full five-minute cycle on a real host, is
  confirmed on a live container before this ships (#81).
