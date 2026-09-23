---
status: accepted
date: 2026-09-22
---

# The Rewrite scan applies its findings

ADR 0005 made the add-on generate its own nginx rewrite rules and apply
them, and ADR 0007 chose how the bundles are read. This ADR records the
four decisions the apply half takes, because it is the half that can break
a running container: both historical breakages (0.3.10 and 0.3.34) were
rewrite rules, and `services.d/nginx/finish` halts the container, so one
bad reload is one container restart.

## The image gets a YAML reader

ADR 0005 keeps the shipped exception list applying to Generated rewrites,
and `generate_include` takes those exceptions as an argument
(`literal_rewrite_gate.py:291`). The list is YAML, and the image had no
YAML reader at all: in the container, `python3 -c "import yaml"` answered
`ModuleNotFoundError`. PyYAML was installed for the tests only
(`release.yml:85`, `tests/requirements-test.txt:4`), so the first code that
imported the analysis module inside the container failed on the import
alone. Issue #92 moved that import into `load_exceptions()` to get its
read-only CLI started, which moved the question here rather than answering
it.

**We decided to add the Debian package `python3-yaml` to the image.**

- **Ship a JSON copy of the exception list beside the YAML.** Rejected:
  the standard library would read it, but two files holding one list
  separate sooner or later, and the test that proves they agree is a test
  of our own bookkeeping rather than of the add-on.
- **Parse the YAML with the standard library.** Rejected: the file is a
  list of mappings today, so a small parser is possible, but it is a new
  thing to maintain and a new thing to get quietly wrong, and the exception
  list is the one input that can turn a failing gate green.

A **Build tier** step proves it, because the **Static tier** cannot see
inside the image: `ci.yml` runs the shipped module in the built image and
reads the shipped exception list with it. That is the check the missing
reader escaped.

## A candidate is validated against a rendered configuration

Issue #77 asked for the candidate to be validated "with `nginx -t` against
the live configuration". That cannot work as written: the include path in
the template is fixed text (`nginx.conf.template`), so `nginx -t`
against the live configuration validates the file already in place and
never the candidate.

**We decided to render a temporary `nginx.conf` whose include line points
at the candidate, and to run `nginx -t -c` against that**, the move the
Static tier already makes (`test_dual_gateway.py:324-325`). Every listener
in the rendered copy becomes a unix socket in a temporary directory,
because `nginx -t` opens listener sockets
(`test_dual_gateway.py:329-337`) and the running nginx holds 8069, 8072 and
5691. Keeping the real listeners would pass in CI, where nothing is
serving, and fail on every host that is.

The listeners are found by pattern rather than by their port numbers, so a
template that gains or moves a listener does not need the apply path
changed with it.

## Three refusals, and the order they are tested in

- **An incomplete scan is never applied.** The include file is the union
  over databases, so a database that could not be read makes the union
  *smaller*. The generated text then genuinely differs from the file in
  place, the byte comparison passes it through, and a Generated rewrite
  that was working is removed: the operator gets a Prefix escape caused by
  a failed read rather than by a changed bundle. `ScanResult.complete` is
  tested before the rescan verdict, never after, because that verdict
  compares the previous state with the same short union and reads a failed
  database as a removal that never happened.
- **A bundle whose bytes cannot be read fails its database.** Issue #92
  reads rows, not bytes, so a row whose filestore file is gone is met here
  first; a row it had to skip because the content is in the database
  (`ir_attachment.location = db`) counts the same, although the read path
  reports that database as `ok` with the skip recorded. Either way it is a
  bundle nobody scanned, which is the same short union by another route.
  The measurement behind ADR 0007 found 0 missing files of 20 and no
  database-stored bundle, so the strict rule costs little.
- **An unchanged generation is not written.** `generate_include` is
  byte-stable, so equal text means equal rules and nginx is not reloaded
  for a file that did not move.

The Generated rewrites are never read back as shipped rules. `nginx.conf`
includes the generated file, but the rules `generate_include` is given come
from the Ingress asset location alone: a generated rule read back as a
shipped one would cover the finding that earned it, the next generation
would drop it, and the rules would flap every other round.

## The state is written only after a pass that was applied

The state (`/data/rewrite-scan-state.json`) says "this is what was served
when the include file was last built", and the next round skips the
expensive pass when nothing moved. That sentence stays true only if the
state is written after a complete scan that was applied, or that needed no
change because the file already held those rules. A state written from a
refused, frozen or invalid round would make the next round skip the pass
that would have fixed it.

While `literal_rewrite_auto` is false the state is not written **and the
skip is not taken**: the option exists so the operator still learns what
would have been rewritten, and a skip there would silence exactly that
report as soon as nothing changed.

## Consequences

- The image carries its first Python library from the distribution beyond
  what Odoo's own package pulls in. `python3-yaml` is small and is a
  Debian package like every other dependency here, but the line has moved.
- Validation costs one `nginx -t` per changed generation, on a host that is
  serving. It opens unix sockets in a temporary directory and reads the
  rendered configuration; it does not touch the running master until
  `nginx -s reload`.
- A reload that fails leaves a valid file in place, so nginx loads the new
  rules at its next start. The round says so rather than reporting the
  rules as live.
- Whether unix sockets are sufficient inside the container, or whether
  something else in the rendered configuration also collides with the
  running nginx, is confirmed on a live container before this ships.

## Postscript (2026-09-23)

Confirmed on the test host (Home Assistant OS 16.1, Supervisor 2026.09.2,
a local build of `main` at 6a8b7e0), running #81's runbook:

- With nginx serving on 8069, 8072 and 5691, a forced round whose
  generation differed from the file validated the candidate, wrote three
  prefixes and reloaded: the add-on log shows `signal 1 (SIGHUP) received
  … reconfiguring` from the master one second after the round's
  `and nginx was reloaded`. The validation collided with nothing.
- At the first round after a start, before nginx was up, the same
  generation was written with `nginx is not running yet, so it was not
  reloaded`, and nginx loaded it at its start. Both branches above hold.
- One shape this ADR did not name: a pass is due on a bundle change or an
  `analysis_version` change, not on a change of the Shipped rewrites. When
  the Shipped rules that a host had generated came back (the shape of a
  Release shipping them), the generated duplicates stayed in the include
  file until a forced round removed them, silently, as removals are. That
  is #135.

## Postscript (#135)

A change of the Shipped rewrites or of the exception list now makes a pass
due, as a bundle change does. The state records a fingerprint of each
(`generation_inputs`: `shipped_rules`, `exceptions`), worked out every round
from the rendered `nginx.conf` and the shipped exception list before the
verdict, and the verdict names which one moved. The fingerprint is taken
from `shipped_rules()` alone and never from the include file, for the reason
given above: a Generated rewrite read back as a Shipped one would make the
rules flap. A state written before this has no fingerprint; it still loads,
and the first round after the upgrade takes the pass once and records it.
One consequence: a rendered `nginx.conf` or an exception list that cannot
be read now fails every round as a failed generation, including rounds
that would have skipped. Before, only a round that took a pass noticed.
