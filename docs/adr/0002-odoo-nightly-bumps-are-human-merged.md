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
