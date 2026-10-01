---
status: accepted
date: 2026-09-09
---

# Odoo nightly bumps are proposed by a bot and merged by a human

The Dockerfile pins one Odoo 18.0 nightly package by version and SHA256. A
weekly job finds the newest nightly, computes its checksum, and opens a pull
request that CI must build; the same job proposes Debian base-image updates.
We decided that these pull requests are **never auto-merged**, and that each
one records itself under `## Unreleased` in the CHANGELOG so the next Release
cannot carry an Odoo change silently.

## Why not auto-merge

An Odoo nightly can carry a database schema change. Odoo migrates the database
on first start after an upgrade, and that migration is irreversible short of a
cold-backup restore. CI proves only that the image builds; it cannot prove that
a migration succeeds on a user's real database. Deciding to accept that risk is
a human call, ideally after a Deploy to the woowtech host first.

## Why not leave it manual

The pin sat on the August 6 nightly for a month because finding, downloading
and hashing a 245 MB package is the kind of chore that always slips. The bot
does the chore; the human keeps the decision.

## When to revisit

Auto-merge becomes reasonable only after CI gains a boot test that starts the
image, initialises a database, and confirms the login page answers, and after
the Release flow writes the Odoo version into the Release notes automatically.

## Postscript (2026-10-01, #215)

The decision above stands: nothing the bot opens is auto-merged, and every
bump records itself under `## Unreleased`. What changed is that the bot no
longer proposes both bumps in **one** pull request.

The base image sits below every layer of the image, so moving its tag rebuilds
all of them — layer (a) included, which an Odoo bump leaves alone. The Release
that carries a base bump is therefore a full download of the whole image,
about 700 MiB, for every host on both architectures. On the WOOWTECH site's
link that is the download that failed twice in #153. Bundling it with the
routine weekly Odoo pin made the routine bump cost the same, which is what
[ADR 0013](0013-small-apt-additions-go-in-the-last-apt-layer.md) rules out:
"Base-image bumps are split from Odoo bumps."

So `odoo-bump` now runs two independent paths in the one job. The Odoo path
rewrites only the two `ODOO_DEB_*` lines and opens `chore/odoo-nightly-bump`,
labelled `dependencies`, as before. The base-image path starts from a clean
tree, rewrites only `BASE_IMAGE_TAG`, and opens `chore/base-image-bump`,
labelled `base-image`; its body says what merging it costs every user. Both
write their bullet through one CHANGELOG writer
(`.github/scripts/changelog_unreleased.py`) that merges into whatever
`## Unreleased` → `### Changed` already holds, because the other path's pull
request may have written there first.

The cadence is the point of the split: the Odoo pull request is merged weekly
when a human accepts the migration risk, and **the base-image pull request is
merged quarterly, or sooner when the new base carries a security fix.** It
stays open in between and is rewritten in place as newer tags appear, so there
is never more than one of it. `odoo18ce/tests/test_bump_pull_requests.py`
holds both paths to this by running the workflow's own steps against a
throwaway tree.
