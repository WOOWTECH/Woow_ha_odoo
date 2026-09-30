---
status: accepted
date: 2026-09-29
---

# Small apt additions go in the image's last apt layer, and the big layers change only on a named event

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

The 235 MiB in the middle is the only large part a weekly Odoo bump
touches. The
478 MiB around it moves when Debian or PostgreSQL moves, which is a
quarterly event, and the small additions are a few MiB each.

We decided that **the image is built as three layers — (a) the stable
packages including the Odoo `.deb`'s own `Depends`, (b) the `.deb` alone,
(c) small apt additions — and a small apt addition goes in (c).** The two
big layers change only for a named event:

- an Odoo bump — (b), and the layers under it: the two `ODOO_DEB_*` ARGs
  sit above (c), so a bump re-sends (c), the add-ons clone, the rootfs
  overlay and the chmod step as well — about 33 MiB on top of the 235 MiB
  package, almost all of it the clone. Layer (a) is what it does not
  touch.
- a base-image bump
- a PostgreSQL major version change
- a change to the pgdg repository setup
- a `LAYER_A_REFRESH` security rebuild
- a lost build cache

**What "small" means:** a Release whose download-size line — the one the
cache/size issue adds to the Release notes — is under about 20 MiB.
Anything bigger is not a small addition and is decided on its own.

Today's layout does not reach that figure, and the measurement says why:
the add-ons clone below (c) is **30.8 MiB** compressed (a 37.9 MiB tree at
the pinned ref), against 0.15 MiB for the rootfs overlay and about as much
again for the chmod step. So a (c) addition costs about 33 MiB whatever is
in it. The threshold stands as the target; moving the clone above (c) is
what would meet it, and it is under "When to revisit" below.

**Consolidation:** (c) is folded into (a) or (b) only together with an event
from the list above, which rebuilds those layers anyway. Tidying (c) on its
own costs every user a full download and buys nothing.

**Refresh:** after a security notice for something layer (a) installs — pgdg
PostgreSQL, or one of the fifty-odd Debian packages Odoo depends on — a
person changes the `LAYER_A_REFRESH` date in a pull request. That is the one
deliberate way to rebuild (a), and the CHANGELOG entry says that the next
update is a full download.

A refresh reaches only what (a)'s own `RUN` installs. `apt-get install`
leaves a transitive dependency alone while the version already there still
satisfies the constraint, so a fix for the base image, or for `curl`,
`gnupg2`, `ca-certificates` and the libraries they bring in above (a) —
`libssl3` among them — does **not** arrive with a refresh. It arrives with a
base-image bump, which is its own line on the list above. Both are on the
list for that reason; neither substitutes for the other.

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
- **(c) is the last apt layer, not the last layer.** Under it sit the
  add-ons clone, the rootfs overlay and the chmod step, and they are
  rebuilt when (c) changes: a small apt addition re-sends about 33 MiB,
  (c) and those three together, of which 30.8 MiB is the clone. They are
  below everything expensive, which is the point of the order — a
  rootfs-only Release, the common one, re-sends only them and never
  re-runs apt. The rootfs is what changes on nearly every Release;
  `WOOW_ADDONS_REF` has moved once, and the clone is below (c) because
  that is the order #154 settled, not because it moves.
- **The saving is only as durable as the CI build cache.** Both build jobs
  use `type=gha` with a scope per architecture, and GitHub evicts a cache
  entry that has not been read for seven days. `build-aarch64` runs only
  when the version changes (`ci.yml`), so an aarch64 Release more than a
  week after the previous one finds no cache, rebuilds layer (a) and
  re-sends all of it — the #153 failure, in the one place this ADR is
  supposed to prevent it. A cache that does not expire is the sibling
  issue's to choose; this ADR only records that the layout does not help
  without one.
- **Base-image bumps are split from Odoo bumps.** The weekly `odoo-bump`
  opens one pull request that can carry both (ADR 0002); a base bump is
  merged quarterly or when a security notice needs it, and an Odoo bump on
  its own week merges without it.
- **The Release notes report the download size** so that a person on a slow
  link knows before starting whether this is a 5 MiB update or a 700 MiB
  one. The line itself is added by the sibling issue of #153.
- **A nightly that gains a dependency is still only a (b) bump.** Adding
  the new package to layer (a) would re-send 480 MiB on a routine weekly
  bump, which is the event list's first line turned inside out. The
  dependency list records it with a `deferred` note instead: apt installs
  it into (b), where it costs a few MiB, and it is folded into (a) at the
  next event that rebuilds (a) anyway. A dependency the nightly *stops*
  naming is the mirror: a `dropped` note keeps it in (a), unused and paid
  for, until the same event removes it. Both are cheaper than the 480 MiB
  a tidy (a) would cost on a routine bump.
- **The pinned `.deb`'s `Depends` becomes a tracked file.**
  `odoo18ce/odoo-deb-depends.txt` is regenerated whenever the `.deb` is
  pinned; its format is a contract with the bump workflow. A dependency the
  file misses is not a broken build — apt installs it in (b), where it makes
  (b) bigger and nothing else. The list is one list for both
  architectures. Naming the packages instead of letting apt resolve them
  makes an arch-specific name possible where it was not before, so all 59
  were checked against `bookworm` main, updates and security and against
  `bookworm-pgdg` for **arm64** as well as amd64; every one exists on both,
  and `python3-lxml-html-clean` is absent on both, so the alternative
  resolves to `python3-lxml` either way. CI builds aarch64 only when the
  version changes, so a future addition to (a) is worth the same check.
  Regenerating the list is part of pinning a new `.deb`, and the static
  tier does not enforce that: `build-amd64` and `build-aarch64` need the
  static job, so failing it would cost every weekly bump the image build
  that proves the new SHA256 and the new package — the gate
  [ADR 0002](0002-odoo-nightly-bumps-are-human-merged.md) rests on — to
  catch a staleness that costs layer (b) size and nothing else.
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
- Small additions become frequent enough to pay for reordering. Moving the
  add-ons clone and its `ARG WOOW_ADDONS_REF` up between (b) and (c) would
  take a (c) Release from about 33 MiB to about 2 MiB, at the cost of
  re-sending (c) on the rare `WOOW_ADDONS_REF` bump. The clone needs only
  `git`, which layer (a) installs, so nothing else stands in the way. It
  is not done here because #154 settled this order and froze it in the
  guard test; changing it is a decision of its own.
- Odoo's `.deb` stops carrying its dependencies as Debian packages. The
  split of (a) from (b) rests on apt resolving `Depends` the same way twice.

## Postscript (2026-09-30)

The first consequence above needs a condition it did not state: a cache
hit keeps a layer's digest only when every cache the build reads holds
the same blob for that step. Through 0.4.7 the Release build read two --
the registry `:buildcache` and, behind it, the GitHub Actions cache that
CI writes and never publishes from. When 0.4.6 merged, the Release and
main's CI built aarch64 cold in parallel and each compressed its own
blob for layer (a): the Release pushed `sha256:e78d8df7becd…` and wrote
it to `:buildcache`, CI wrote `sha256:b83475a1fd86…` to the Actions
cache. The 0.4.7 Release reported `[3/8] … CACHED`, took CI's blob, and
re-sent layer (a): 720.9 MiB against 0.4.6 on aarch64, where amd64,
whose caches happened to agree, sent 378.5 MiB. So the Release build now
reads the registry cache only; a Release that finds none builds cold and
writes it, and the blob it pushes is then the blob it caches. CI keeps
reading both and writing only the Actions one, because its blobs never
reach an image (#219).

## References

- [ADR 0001](0001-distribution-follows-release-tags.md) — what a user
  downloads is a Release tag, so the layer layout is settled before a
  Release and not after one.
- [ADR 0002](0002-odoo-nightly-bumps-are-human-merged.md) — the weekly bump
  is a human decision; this ADR decides what that bump costs to download.
