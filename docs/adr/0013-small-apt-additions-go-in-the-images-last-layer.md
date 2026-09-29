---
status: accepted
date: 2026-09-29
---

# Small apt additions go in the image's last layer, and the big layers change only on a named event

Through 0.4.5 one `RUN` installed PostgreSQL 16, the pinned Odoo nightly
`.deb`, the fonts, `wkhtmltopdf`, `jq`, `git`, `nginx` and whatever small
Python package the add-on had most recently come to need. It produced one
compressed layer of about 690 MiB — 693.3 MiB on amd64 in 0.4.4, 689.1 MiB
on aarch64 — inside a 759 MiB image of which 724 MiB was new.

A layer is the unit the Supervisor downloads, and Docker cannot resume a
partial one: a pull that drops at 80 % starts that layer again from zero.
Adding `python3-yaml` in 0.4.3 and `python3-pycryptodome` in 0.4.4 changed
that one layer, so both Releases re-sent all 690 MiB to every host. On the
WOOWTECH site's link, measured at 120–200 KiB/s, that layer needs about 75
unbroken minutes, and the update failed twice with `unexpected EOF` (#153).

The packages do not change at the same rate. Measured on amd64 against
`bookworm-2026.08.0` plus the pgdg repository, as `.deb` download sizes:

| | packages | download |
|---|---|---|
| the stable packages (PostgreSQL 16, fonts, tools) | 147 | 207 MiB |
| the Odoo `.deb` itself | 1 | 235 MiB |
| the `.deb`'s further dependencies | 110 | 271 MiB |

The 235 MiB in the middle is the only part a weekly Odoo bump touches. The
478 MiB around it moves when Debian or PostgreSQL moves, which is a
quarterly event, and the small additions are a few MiB each.

We decided that **the image is built as three layers — (a) the stable
packages including the Odoo `.deb`'s own `Depends`, (b) the `.deb` alone,
(c) small apt additions — and a small apt addition goes in (c).** The two
big layers change only for a named event:

- an Odoo bump — only (b) changes
- a base-image bump
- a PostgreSQL major version change
- a change to the pgdg repository setup
- a `LAYER_A_REFRESH` security rebuild
- a lost build cache

**What "small" means:** a Release whose download-size line — the one the
cache/size issue adds to the Release notes — is under about 20 MiB.
Anything bigger is not a small addition and is decided on its own.

**Consolidation:** (c) is folded into (a) or (b) only together with an event
from the list above, which rebuilds those layers anyway. Tidying (c) on its
own costs every user a full download and buys nothing.

**Refresh:** after a PostgreSQL or OpenSSL security notice, a person changes
the `LAYER_A_REFRESH` date in a pull request. That is the one deliberate way
to rebuild (a), and the CHANGELOG entry says that the next update is a full
download.

The Dockerfile's order is frozen by a Static-tier guard test,
`odoo18ce/tests/test_dockerfile_layers.py`, which compares the normalized
instruction sequence from `FROM` through (b) against a literal list and
keeps layer (a)'s package list equal to `odoo18ce/odoo-deb-depends.txt`.
The guard is what makes this ADR hold a year from now, when the next small
package is needed and the obvious place to put it is wherever apt already
runs.

## Considered options

- **Leave the single layer and ask users to retry.** Rejected: it is what
  0.4.3 and 0.4.4 did, and the retry is 75 minutes that fails on a dropped
  connection at any point. The resume script in `docs/runbooks/` (#157)
  makes the failure survivable; it does not make it rare.
- **One layer per package.** Rejected: the Supervisor pulls layers with
  limited concurrency and the registry charges a round trip each, so a long
  tail of tiny layers is slower on the same link and harder to read in a
  `docker history`. Three layers split the one axis that actually matters —
  how often a thing changes.
- **Put the `.deb`'s dependencies in (b), beside the `.deb`.** Rejected:
  that is the layout we have. An Odoo bump would keep re-sending 506 MiB
  instead of 235 MiB, which is most of the problem left in place.
- **Install the dependencies from a list that the build reads with `COPY`
  instead of writing them into the `RUN`.** Rejected, narrowly: it removes
  the duplication, but then a package added to the list changes no line of
  the Dockerfile, and the guard test's frozen instruction sequence — the
  thing that makes an addition to (a) visible in review — would no longer
  see it. The list is written into the `RUN`, and the test holds the file
  and the `RUN` equal.

## Consequences

- **The layers stay identical only through the build cache.** Two builds of
  the same source on different machines do not produce the same layer
  digest; `apt-get update` alone sees a different archive. What keeps (a)
  unchanged across an Odoo bump is the registry build cache in CI, not
  determinism. A lost cache is a full download for every user, and is on the
  event list above for that reason.
- **Security fixes for the packages in (a) now arrive only with a base-image
  bump, a `LAYER_A_REFRESH` or a lost cache.** Before, any Release that
  touched the big `RUN` happened to pick them up. This is accepted: the
  refresh rule is the deliberate replacement, and an unplanned pickup that
  costs every user 690 MiB was never a security policy.
- **Base-image bumps are split from Odoo bumps.** The weekly `odoo-bump`
  opens one pull request that can carry both (ADR 0002); a base bump is
  merged quarterly or when a security notice needs it, and an Odoo bump on
  its own week merges without it.
- **The Release notes report the download size** so that a person on a slow
  link knows before starting whether this is a 5 MiB update or a 700 MiB
  one. The line itself is added by the sibling issue of #153.
- **The pinned `.deb`'s `Depends` becomes a tracked file.**
  `odoo18ce/odoo-deb-depends.txt` is regenerated whenever the `.deb` is
  pinned; its format is a contract with the bump workflow. A dependency the
  file misses is not a broken build — apt installs it in (b), where it makes
  (b) bigger and nothing else.
- **The exact compressed size of each layer** is measured by this pull
  request's CI build, for amd64, and recorded in the pull request
  description. The agent container that wrote this ADR has no Docker and
  could not measure it; the numbers above are `.deb` download sizes, which
  are what the split was decided on.

## When to revisit

- The Supervisor or Docker learns to resume a partial layer, or the site's
  link stops being the constraint. Then the split buys much less and (c)
  can be folded back.
- (c) stops being small — it collects enough packages that a "small
  addition" is no longer under 20 MiB. Fold it into (a) at the next
  base-image bump and start a new (c).
- Odoo's `.deb` stops carrying its dependencies as Debian packages. The
  split of (a) from (b) rests on apt resolving `Depends` the same way twice.

## References

- [ADR 0001](0001-distribution-follows-release-tags.md) — what a user
  downloads is a Release tag, so the layer layout is settled before a
  Release and not after one.
- [ADR 0002](0002-odoo-nightly-bumps-are-human-merged.md) — the weekly bump
  is a human decision; this ADR decides what that bump costs to download.
