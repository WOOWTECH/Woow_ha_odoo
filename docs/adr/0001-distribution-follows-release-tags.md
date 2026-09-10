---
status: accepted
date: 2026-09-09
---

# Distribution follows Release tags, not `main`

Until 0.3.39 every user's Supervisor built the image from the Dockerfile on
their own device, and the App Store mirror copied whatever was on `main` once a
day, tested or not. We decided that a **Release** is exactly one thing: a
version bump in `config.yaml` merged to `main`. Only that event produces a
`v<version>` tag, a GitHub Release, and prebuilt images at
`ghcr.io/woowtech/woow-ha-odoo-{arch}:<version>`, and the mirror syncs from the
latest Release tag rather than from `main`.

## Considered options

- **Keep on-device builds.** Rejected: every patch release forced a 245 MB
  download and a PostgreSQL apt install on every Raspberry Pi, and the pinned
  Odoo nightly package will eventually disappear from nightly.odoo.com, which
  would break installs of already-released versions.
- **Push images on every merge to `main`.** Rejected: the registry would fill
  with versions that were never released, and the "same version, different
  bytes" failure becomes possible.
- **Let the mirror keep copying `main`.** Rejected: users saw in-between
  commits, and untested content reached the store before its Release.

## Consequences

- A version tag in the registry is immutable. The publish job refuses to
  overwrite an existing tag.
- A version bump PR must prove both architectures build before it can merge,
  because the moment it lands users who added this repository directly will
  try to pull that version.
- `build.yaml` stays in the repository even though Supervisor no longer reads
  it: the publish job reads `build_from` from it.
- Adding `image:` to `config.yaml` was itself a Release (0.4.0) whose images
  had to be pushed by hand before the bump merged.
