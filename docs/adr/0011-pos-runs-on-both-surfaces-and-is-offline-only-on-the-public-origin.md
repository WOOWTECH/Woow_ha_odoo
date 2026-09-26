---
status: accepted
date: 2026-09-24
---

# Point of Sale runs on both surfaces, and only the Public origin can work offline

Odoo's Point of Sale keeps selling while the network is down by caching
itself in a service worker. The Runtime shim disables service workers under
**Ingress** and has done so since 0.3.6: Odoo registers its worker with the
root scope, which crosses the Supervisor token boundary, and a worker left
over from an earlier version kept serving stale rewritten assets after
updates (0.3.21). An HTTPS Home Assistant does not change this: the shim
disables the worker whatever the scheme, and over plain http the browser
offers no `navigator.serviceWorker` at all (issue #60). The parity plan
therefore expected POS offline mode to fail under Ingress (`U-C27`, section
10.1), and the 2026-09-08 handoff asked for a decision before POS is
installed.

We decided that **POS is installed and usable on both surfaces, and offline
selling is a Structural gap of Ingress.** A till that must keep selling
through an outage opens the Public origin. Ingress stays useful for the POS
back office — configuring sessions, products and payment methods, reviewing
orders — and for a till that can stop when the network stops.

## Considered options

- **POS only on the Public origin.** Rejected: it would hide a back office
  that works under Ingress, only to protect one capability that a person
  choosing a till can route around.
- **Let the POS scope keep its service worker under Ingress.** Rejected: it
  reopens both reasons the shim disables workers, for every POS user, and the
  shim's service-worker rule stops being one rule.

## Consequences

- The POS parity run marks offline mode under Ingress as `STRUCTURAL`, with
  the Public origin as the path that carries it, and verifies that the
  Public origin really works offline. It is not filed as a `GAP`.
- `DOCS.md` lists POS offline mode among the things only the Public origin
  can do.
- A future change to the shim's service-worker handling reopens this ADR.

## Postscript (2026-09-26, #161)

The premise above is wrong for Odoo 18 CE. Its Point of Sale has no service
worker. The only worker is the web client's `/web/service-worker.js`, with
scope `/odoo`, and it only shows an offline page when a navigation fails.
POS keeps selling through an outage inside the page it has already loaded.

The #161 run (`docs/testing/evidence/2026-09-26-issue-161/`) did the same
steps on the Public origin and under Ingress over the plain-http LAN
entrance. It loaded `/pos/ui`, cut the network with the browser's offline
emulation and sold one product for cash:

- **In-page offline sale: the same on both surfaces.** The till showed
  "Connection Lost" and validated the sale. About 3 seconds after the
  network came back, the order was on the server as a paid `pos.order` in
  the open session. `PARITY`.
- **Reloading `/pos/ui` offline: fails on both surfaces** with
  `net::ERR_INTERNET_DISCONNECTED`. `PARITY`.

So offline POS selling is **not** a Structural gap of Ingress, and a till
that must keep selling through an outage does not need the Public origin.
The decision stands that POS is installed and usable on both surfaces. The
consequences change: the parity run records POS offline as `PARITY`, and
`DOCS.md` no longer lists POS offline mode among the things only the Public
origin can do. What the shim's service-worker rule still costs Ingress is
installing Odoo as an app (PWA) and the web client's offline page.

The title no longer holds: offline selling works on both surfaces, not
only on the Public origin. The file name is kept so that links to this ADR
still work.
