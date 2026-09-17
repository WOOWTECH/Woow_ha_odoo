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

**Canonical URL**:
The value the maintenance bootstrap writes into `web.base.url` and the default website's `domain` on every start, and then locks with `web.base.url.freeze`. It is the Public origin when `public_url` is set, otherwise the Home Assistant host's LAN address with the published Odoo port. A stored value that carries an Ingress token is never kept as the Canonical URL.
_Avoid_: base url, own address, web.base.url (in prose)

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

**Shipped rewrite**:
A Literal rewrite rule written by hand in the nginx template and delivered with a Release.
_Avoid_: hardcoded rule, template rule, 手寫清單

**Generated rewrite**:
A Literal rewrite rule the add-on derives while running, from the asset bundles a database actually serves, and applies without a Release.
_Avoid_: auto rule, dynamic rule, 自動修正 (as a noun)

**Rewrite scan**:
The add-on's own analysis of the served asset bundles that classifies every root-relative literal by how it is consumed and yields the Generated rewrites. The Literal rewrite gate is the same analysis run from outside against a Public origin.
_Avoid_: 守門 (for the in-container run), auto-fix, self-check

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
