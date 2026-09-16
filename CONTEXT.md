# Woow Odoo 18 Add-on

The Home Assistant add-on that bundles Odoo 18 Community Edition and PostgreSQL 16 in one container, and the pipeline that tests, publishes and distributes it.

## Language

### Surfaces

**Ingress**:
The Home Assistant sidebar entrance to Odoo, reached through the Supervisor's authenticated iframe.
_Avoid_: sidebar version, panel, 側欄版 (in code and docs)

**Public origin**:
The Odoo entrance reached through the Cloudflare tunnel on the add-on network, restricted to ordinary application features.
_Avoid_: web version, tunnel origin, 網頁版 (in code and docs)

**LAN tier**:
The privilege level granted on the published origin ports to callers whose source address is inside `lan_networks`; it includes the database manager.
_Avoid_: local access, trusted network, direct access

### Ingress mechanics

**Runtime shim**:
The script nginx injects at the top of every Ingress HTML page; it adds the Ingress prefix in the browser at the moment a request, navigation, attribute or worker is created.
_Avoid_: ingress shim, head script, 注入腳本

**Literal rewrite**:
The server-side substitution nginx applies to root-relative string literals inside asset bundles before sending them over Ingress; it covers only what the Runtime shim cannot intercept.
_Avoid_: sub_filter whitelist, 資產改寫, route substitution, 白名單

**Prefix escape**:
A request or navigation made through Ingress that lands on the Home Assistant root instead of under the Ingress prefix.
_Avoid_: 逃逸到 HA 根, root escape, RC-1 (alone)

### Lifecycle

**Release**:
A version bump in `config.yaml` merged to `main`. It is the only event that produces a tag, a GitHub Release and published images.
_Avoid_: publish, bump, ship, version

**Sync**:
The App Store mirror picking up a Release into `Woow_HA_App_Store`.
_Avoid_: mirror, copy, push to store

**Deploy**:
Installing a Release on a real Home Assistant host.
_Avoid_: update, roll out, install

**App Store mirror**:
The `Woow_HA_App_Store` repository, a synchronized copy that users add as a single repository URL; this repository is the canonical source.
_Avoid_: store, aggregate repo, downstream

### Test tiers

**Static tier**:
Lint plus every test that runs without a live Odoo, including the nginx and node contract tests.
_Avoid_: unit tests, offline tests

**Build tier**:
A real Docker build of the add-on image for one or more architectures.
_Avoid_: compile, image test

**Live tier**:
Browser or API tests that need a deployed Odoo and credentials, run against Ingress or the Public origin.
_Avoid_: E2E (alone), integration tests, browser tests

**Perimeter check**:
The read-only Live-tier assertions that database lifecycle routes are closed on the Public origin.
_Avoid_: smoke test, security scan
