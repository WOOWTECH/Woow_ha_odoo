---
status: accepted
date: 2026-09-22
---

# Links the browser builds use the Canonical URL, published by the Runtime shim

ADR 0004 made the **Runtime shim** the Ingress URL authority: it adds the
Ingress prefix at the moment the browser creates a request, navigation,
attribute or worker, and the **Literal rewrite** covers only what the shim
cannot intercept. Both mechanisms produce *root-relative* paths for the
add-on's own surfaces. Neither has anything to say about a link that the
browser builds as an *absolute* address for somebody outside to open.

Odoo 18 builds several such links in the browser. The Discuss invitation link
joins `window.location.origin` to `/chat/<id>/<uuid>`. The general
`@web/core/utils/urls` helper reads `session.origin`, and Odoo 18 session info
carries no `origin` field, so it falls back to the browser's protocol and
host. Under Ingress both are the Home Assistant host, and the path carries no
Ingress prefix, so the link is a Home Assistant 404 for the person it was sent
to. Measured on the control group on 2026-09-17 (issue #70, and the
reproduction in issue #60), from both Home Assistant entrances: the link was
`<the HA LAN address>:8123/chat/2/…` over plain http and
`https://woowtech-ha-test-6.woowtech.io/chat/2/…` over the tunnel, where it
should have been `https://woowtech-odoo-test-6.woowtech.io/chat/2/…`. The
host's LAN address is deliberately not recorded here (ADR 0003).

The **Canonical URL** lock that the maintenance bootstrap applies to
`web.base.url` (issues #57 and #67) cannot reach any of this. That lock
governs what the *server* puts in a page, an email or a report. These values
never pass through the server.

We decided that **the Runtime shim publishes the Canonical URL to the Ingress
page as a read-only global, and each browser-built outbound link is moved onto
that base by its own exact-expression Literal rewrite**.

- The shim defines `window.__WOOW_CANONICAL_URL__`, with no trailing slash,
  before any bundle runs. It is non-writable and non-configurable, so a bundle
  cannot move the base of a link that has already been rewritten. When there
  is no Canonical URL the global is the empty string and every rewrite keeps
  the browser origin, which is the behaviour we have today.
- Each link gets one `sub_filter` matching one exact expression, in the
  Ingress asset location, in the shape ADR 0004 already allows for the router
  and bus worker patches. Nothing is matched by prefix.
- A link whose expression is not stable enough to match, or whose expression
  is shared with an in-Ingress address, is registered `STRUCTURAL` in the
  parity plan and is served by the Public origin instead.
- Ingress-only, with no `public_url`: the links use the Canonical URL as it is
  then defined -- the Home Assistant host's LAN address with the published
  Odoo port -- which is the same address the server-side links already carry.
  Share controls are not hidden.
- The value is now needed at two points of a start, and the rule that chooses
  it stays in one place: `canonical_url()` in the maintenance library. The
  config rendering calls it at cont-init through
  `/usr/local/bin/odoo-canonical-url`; the maintenance bootstrap calls it at
  services.d for `web.base.url`. Neither point derives the value on its own.

This ADR covers the mechanism and the global. The inventory of affected links,
and each rewrite, follow in issue #70.

## Considered options

**Rewrite `session.origin` to the Canonical URL in the shim.** One change
would cover every caller of `url()` at once. Rejected: `url()` also builds
`/web/image`, `/web/content` and other in-Ingress addresses, and the shim's
`path()` only prefixes same-origin URLs. With `session.origin` set to the
Public origin those addresses would become absolute public URLs and leave
Ingress, breaking image, attachment and RPC loads on the very surface this
work is meant to protect. The measurement behind this is recorded in issue
#70; ADR 0005 did not change it.

**Leave every one of these links to the Public origin (`STRUCTURAL` for all
of them).** Honest, and it needs no code. Rejected as the default because the
add-on supports deployments with no Public origin at all, where it would leave
the operator with no working share link anywhere; it stays the answer for the
individual links whose expression cannot be matched safely.

**Have Odoo serve the right value instead (extend `woow_base_url_guard` to
put the Canonical URL into session info).** It would remove the string-matching
problem entirely. Rejected for now: that module is deliberately a server-wide
module that ships no models, data or views and installs in no database, and
the change would alter the Public origin's pages as well as Ingress's. It is
worth revisiting if the exact-expression rewrites prove unstable across Odoo
point releases.

## Consequences

- An unmatched `sub_filter` is a silent no-op: nginx does not complain, no
  test turns red, the page renders, and only the link is wrong. Every rewrite
  added under this ADR therefore needs a fixture taken from a real served
  bundle, not a hand-written guess.
- The Canonical URL is now needed at two points of a start: cont-init, which
  renders the nginx config, and services.d, where the maintenance bootstrap
  writes `web.base.url`. The rule stays in one place -- `canonical_url()` in
  the maintenance library -- and both points call it, cont-init through
  `/usr/local/bin/odoo-canonical-url`. Deriving the value separately in either
  place would let the address the browser is told drift from the address Odoo
  stores.
- The Rewrite scan does not count an exact-expression patch as coverage for
  the prefix inside it (`rewrite_rules()` collects prefix rules only). Today
  nothing collides, because Generated rewrites are created for `FAIL`-level
  findings and these links are not whole-page navigations. If one of these
  prefixes ever appears in a navigation, the generated prefix rule and the
  patch here would compete for the same literal in the same location; the
  prefix then has to be registered in the exception list.
- The Public origin is untouched: the Runtime shim is injected by the Ingress
  listener alone.

## Amendment (2026-09-23): one rewrite does not keep today's behaviour

The decision above says that with no Canonical URL every rewrite keeps the
browser origin, "which is the behaviour we have today". For the website share
block that sentence was wrong to apply, and it is now an explicit exception:
**the Ingress prefix is dropped whether or not a Canonical URL exists.**

Today's behaviour there is to hand `location.href` to Facebook, X or WhatsApp,
and under Ingress that string contains the Supervisor token. "Keep today's
behaviour" was written to mean "change nothing we have not measured"; applied
here it meant "keep publishing a credential to a third party", which was never
the intent. The other two rewrites are unaffected: a wrong host is a broken
link, not a disclosure, and they still keep the browser origin exactly.

What made this worth revisiting rather than leaving registered as a gap is
that the shape is reachable. `bashio::network.ipv4_address` returns nothing on
a host whose uplink is a bridge, bond, WWAN or tun device (Supervisor
enumerates only ethernet, wireless and VLAN), on an interface NetworkManager
does not manage, and on IPv6-only or IPv4-disabled networking. A DHCP lease
that has not arrived when the add-on starts produces the same empty value, and
bashio caches it in a file for the lifetime of the container, so a boot-time
race presents as a permanent condition (issue #108).

Without a Canonical URL the share link still points at the Home Assistant host
and still does not work. It simply no longer carries the token.
