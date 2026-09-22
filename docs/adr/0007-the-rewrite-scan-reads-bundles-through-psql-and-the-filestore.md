---
status: accepted
date: 2026-09-22
---

# The Rewrite scan reads bundles through psql and the filestore

ADR 0005 made the add-on run the **Rewrite scan** itself: at start and every
five minutes after, it reads the asset bundles every database serves "from
`ir.attachment`, no login, no network" and rescans when their checksums
change. It did not say how those bytes are reached. Issue #77 later named
the `odoo shell` path the maintenance bootstrap uses
(`odoo-maintenance-bootstrap:113`), which is a stricter requirement than
ADR 0005 states, and a standing cost rather than a one-off one: it is paid
once per database, every five minutes, beside the live workers.

Two read paths were measured against a populated database before the code
was written:

- **A — `odoo shell`, one database at a time.** A full Odoo registry starts,
  the rows are read through the ORM, the process exits.
- **B — `psql` plus the filestore.** `ir_attachment` carries `checksum` and
  `store_fname`; the filestore is in the same container under
  `/data/odoo/filestore/<database>/` (`10-odoo-config.sh:12`, plus the
  per-database subdirectory). No Odoo process starts at all.

## The measurement

Taken 2026-09-22 on the control group host (ADR 0003), add-on
`1b7b4ce7_odoo18ce`, one database with 21 bundle attachment rows over 20
distinct checksums, 45.9 MB of `file_size` and 39.2 MB of distinct bytes.
One file is served under two URLs, so reading by checksum saves 6.7 MB.
Read-only apart from one temporary file, since removed; the `odoo shell`
runs used a no-op script.

| Per scan round | Option A | Option B |
| --- | --- | --- |
| Read | 4.71 s (two runs: 4.71, 4.72) | 0.08 s (query 0.059 s, 20 files 0.02 s) |
| Analysis | 4.17 s | 4.17 s |
| **Round** | **≈ 8.9 s** | **≈ 4.25 s** |
| Peak RSS | ≈ 182 MiB | ≈ 129 MiB |

The analysis figure is the same bytes through `scan_bundle` in
`literal_rewrite_gate.py`: 39.2 M characters, 7,863 findings, 4.17 s, peak
114 MiB with each bundle's findings freed and 129 MiB with the union held
for `generate_include`. 4.71 s and 182 MiB is the floor for starting a
registry and doing nothing; the bootstrap's own pass in the add-on log took
8 s, which is that load plus its write, freeze and commit.

Option B's read was page-cache warm. A cold read of 39 MB from local
storage does not approach 4.7 s, so the conclusion does not turn on it.

## We decided

**The Rewrite scan reads bundle rows with `psql` and the bundle bytes from
the filestore.** Option A is option B plus 4.7 s and 65 MiB, per database,
every five minutes, for no extra information.

The measurement changed the shape of the argument rather than only settling
it. The analysis costs as much as a whole registry load, and **both options
pay it**, so the decision is only about the read — where B is about 60×
cheaper. Two consequences follow from the part neither option avoids:

- The five-minute interval must not be shortened. A round costs about four
  seconds of CPU on that host whichever path is taken.
- `scan_state` is not an optimisation. It is what keeps those four seconds
  from being paid when nothing changed, and the reason the previous state
  is kept on disk rather than in memory: a restart would otherwise re-read
  and re-analyse everything.

The scan runs as root and drops to `postgres` through `s6-setuidgid` for
the query, the shape `odoo-maintenance-bootstrap:75` already uses. No
single user can do both halves: `psql` peer-authenticates as `postgres`,
and the filestore is `odoo:odoo` under `umask 077`
(`10-odoo-config.sh:7,16`). No password is handled and no permission is
widened.

This does not conflict with ADR 0005, which says only "from
`ir.attachment`, no login, no network". It does replace the `odoo shell`
sentence in issue #74's Implementation Decisions.

## Considered options

- **A, `odoo shell`, for consistency with the maintenance bootstrap.**
  Rejected on the numbers above. The bootstrap pays that cost once per
  start because it writes through the ORM and needs the registry's
  invariants; the scan only reads rows it could read directly.
- **Read the bundle bytes through Odoo's `ir.attachment` API instead of the
  filestore.** Rejected with A: it is the same registry load.
- **Keep the previous state in memory only.** Rejected: every restart would
  pay the full read and analysis again, and the state has to be comparable
  with the include file that outlives the process.
- **Read only `*.min.js` and `*.min.css`, as issue #74 wrote.** Rejected:
  the **Literal rewrite** location is `^~ /web/assets/`, so a `dev_mode`
  install's unminified bundles are served through it too and must be
  scanned. The query filters on the mimetype allow-list instead, which also
  drops source maps (`application/json`), whose unminified source would
  otherwise produce false `FAIL` findings.

## Consequences

- The image gains no dependency, but it did gain a constraint: the scan is
  the first code to import `literal_rewrite_gate.py` inside the container,
  and `python3 -c "import yaml"` fails there. PyYAML is a test requirement
  only (`release.yml:85`, `tests/requirements-test.txt:4`), so the `yaml`
  import moved into `load_exceptions()`, the one function that needs it.
  That defers rather than answers the question: ADR 0005 keeps the shipped
  exception list applying to Generated rewrites, so whichever ticket builds
  the include file inside the container has to put PyYAML in the image or
  read the list another way. The scan and its CLI no longer fail on the
  import alone, which is what this ticket needed. ADR 0008 answered the
  question this bullet left open: the image gains the Debian package
  `python3-yaml`.
- A row whose `store_fname` is NULL (`ir_attachment.location = db`, which
  the add-on never sets but an operator can) has no filestore bytes. It is
  reported as an unsupported-storage skip rather than read through
  `db_datas`: the case is rare, and a second read path would have to be
  measured and maintained for it.
- The module and the CLI join the image's `chmod` list. The state file does
  not, and cannot: it lives on the `/data` volume and does not exist when
  the image is built. `save_state` gives it 0644 as it writes it, the way
  `10-odoo-config.sh:257-267` does for the include file beside it, because
  cont-init's `umask 077` would otherwise leave both readable to root alone.
- The state carries `analysis_version`, the sha256 of
  `literal_rewrite_gate.py` and `rewrite_scan.py`. A Release that improves
  the classification re-runs the scan even though no bundle changed, and
  nothing has to be bumped by hand for that.
- Reading with `psql` means the scan sees rows, not an ORM. A bundle row
  that does not parse fails its database rather than being dropped,
  because a dropped bundle reappears as a missing rule and a **Prefix
  escape**.
- The scan sees only what is on this host's disk. Nothing verifies that the
  bytes behind a checksum are what Odoo would serve; the checksum is
  `ir_attachment`'s own, and the filestore is content-addressed by it.
