---
status: accepted
date: 2026-09-22
---

# The PR gate proves the Canonical URL guard is applied

`woow_base_url_guard` is a server-wide module that patches
`res.users.authenticate` at import so Odoo never writes a request's origin
into the `web.base.url` parameter (the G-01 residue, issue #67, verified on
the test host in #90). It finds its seam by name, and when a nightly moves
the seam it raises `ImportError`. Issue #88 established what that raise
buys: nothing. Odoo's server-wide loader logs `Couldn't load module` and
`Failed to load server-wide module`, then starts, serves and exits 0 without
the guard. Measured on the test host on 2026-09-22.

None of the gates in place could see it. The Static tier tests the guard
against a stand-in Odoo that never moves. The Build tier built the image
and, by the day this shipped, ran one Python import check in it (ADR 0008),
but never started Odoo. The weekly nightly bump PR said the gate "proves the
image still builds", which was exactly and only true. Any nightly that
changed `res.users.authenticate` would have merged green, leaving one unread
ERROR line in users' container logs.

## The gate starts the built image and asks Odoo whether the patch is on

**We decided that the Build tier's unconditional job starts `odoo shell` in
the image that PR just built, with the server-wide modules the add-on
renders, and fails when `res.users.authenticate` does not carry the guard's
flag.** A second run leaves the guard out of `--load` and must come back
"not applied", so the check is shown able to go red on the same image
(issue #88, PR #115; the step is "In-image contract (Canonical URL guard)"
in `.github/workflows/ci.yml`). This was direction B of the three weighed on
#88.

The invariant proved is the patch, not the file. The probe never imports
the guard itself, because that would apply the patch and pass by itself.
The run needs no database, no Supervisor, no Home Assistant and no
credential, so it is a Build-tier check, not a Live one. Because the
nightly bump edits the Dockerfile's Odoo pin, the check runs on the image
built after that edit and on the job that runs for every pull request, so a
bump cannot skip it.

The two other directions:

- **A — stop the container when the guard does not load.** Every serving
  service in this image halts the container from its `finish`, and the
  guard could have followed that convention. Rejected on cost: the guard is
  a protective module, and "protection missing, so no Odoo at all" trades
  one login's wrong Canonical URL for an outage, on every host, for as long
  as the seam stays moved.
- **C — check on the control-group host.** Rejected: that host is being
  retired (ADR 0003 Postscript, ADR 0005), and a check that depends on it
  would retire with it.

## Consequences

- A nightly that moves the seam now fails its bump PR with a message naming
  the guard, instead of merging and being found in a user's log.
- The guard itself is unchanged. It still raises `ImportError` on a moved
  seam; the raise is a log line for the operator, and the gate is what
  keeps the seam from moving unnoticed. `DOCS.md` and the CHANGELOG gained
  text stating that loader behaviour (PR #115), and PR #84's description,
  which had called the raise "fail loud", was edited on 2026-09-23.
- `.github/workflows/odoo-bump.yml` and the pull request body it generates
  still say the gate "builds the image"; the human who merges a nightly
  (ADR 0002) is told less than the gate now checks. Updating that wording
  is a follow-up, not part of this decision.
- The check answers one question. Whether cont-init, s6 or the nginx
  render work in the built image is not its concern; a start-up acceptance
  in the gate would be its own decision.

## Amendment (2026-09-23)

Issue #121 tightened what the probe proves (PR #129). The flag alone did
not show that the class carrying it is the one the registry runs, nor that
the wrapper still fits upstream:

- the probe now checks the flag on the last class in Odoo's `res_users`
  module that declares `authenticate`, which is the one the registry runs;
  a later declaration the guard never saw carries the guess back, flag or
  no flag;
- it compares the wrapper's forwarded parameters with upstream's
  signature, since a changed arity lets the guard install and then raises
  `TypeError` on every login;
- starting Odoo is what made a timeout necessary: the job now has a
  30-minute cap and each `docker run` a 300-second bound, so a nightly
  that makes `odoo shell` wait on something ends the job in minutes, not
  hours. The earlier import check ran without one because it could not
  block.
