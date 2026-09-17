---
status: accepted
date: 2026-09-17
---

# Generated rewrites replace the control group gate

ADR 0004 made the Runtime shim the Ingress URL authority and left the
**Literal rewrite** for the whole-page navigations the shim cannot reach,
with a Live-tier gate on the control group deciding when a prefix has to be
added. The gate's first full-application run on 2026-09-17 (25 apps from the
parity plan) found three such prefixes (`/shop/`, `/payment/`, `/contactus`),
each of which needs a template change and a Release before an installed
add-on is fixed. The test host that serves as the control group (ADR 0003)
stops once the short-term goal of confirming Ingress on those 25 apps is
met, so the nightly gate would have nothing to run against.

We decided that **the add-on performs the Rewrite scan itself and applies
the result as Generated rewrites**, and that **the two nightly GitHub
workflows lose their schedule**:

- At start, and every five minutes after, the add-on reads the asset bundles
  every database serves (from `ir.attachment`, no login, no network) and
  rescans when their checksums change. Only prefixes used in a whole-page
  navigation (the gate's `FAIL` level) become Generated rewrites; path
  comparisons (`WARN`) never do, per ADR 0004. The rules go into an nginx
  `include` file that is validated with `nginx -t` before `nginx -s reload`;
  an invalid or failed generation keeps the last good file and Odoo keeps
  running. The exception list shipped in the image still applies.
- The option `literal_rewrite_auto` (default on) turns application off; the
  scan and its report keep running so the operator still learns what would
  have been rewritten. Every applied rule is logged; a Home Assistant
  notification is sent only when a rule is added or generation fails.
- The Perimeter check's outside view is replaced by a self-check at start:
  the container requests its own database-manager route from its add-on
  network address with the public `Host`, the same path the tunnel takes,
  and refuses to start on anything but `404` (public shape) or `503` (no
  `public_url`).
- `perimeter.yml` and `literal-rewrite-gate.yml` keep `workflow_dispatch`
  for whenever a control group exists again; the Literal rewrite gate CLI
  stays as the outside-in version of the same analysis, sharing the pure
  functions that move into the image.

## Considered options

- **Keep the control group and the nightly gate, add rules by hand.**
  Rejected: every new app that navigates with a new prefix costs a Release,
  and the host that would serve as control group is being stopped.
- **Generate rules but require a human to apply them.** Rejected: that is
  the gate with a local report, not a fix; the operator would still wait for
  a Release.
- **Generate rules for every prefix or for path comparisons too.**
  Rejected in ADR 0004 and not reopened: 0.3.10 and 0.3.34 both broke on
  broad rewrites, and `/scoped_app` shows a rewritten comparison is wrong.
- **Move the self-check inside via a test header that forces public
  treatment.** Rejected: it adds a permanent special path to nginx; sourcing
  the request from the add-on network address exercises the real `geo`
  rules instead.

## Consequences

- A Generated rewrite goes live without a human reading it. The scope is
  narrow (navigation-level prefixes only) and the kill switch exists, but
  the two historical breakages were rewrite rules, so the notification and
  the log line are the review.
- Nothing outside the host checks the Public origin any more. A
  misconfigured tunnel or an opened database route is caught only by the
  start-time self-check, which sees the add-on's own nginx, not the
  internet path.
- nginx gains a reload path it did not have; the `include` file must exist
  (empty) before the first start and the static tier must cover the
  rendered template with it.
- The pure analysis functions move from `odoo18ce/tests/` into the image
  under `rootfs/usr/local/lib/`; the static tier imports them from there.
- The Ingress-only install shape is still supported: with no `public_url`
  the self-check expects `503`, and Generated rewrites work the same.
