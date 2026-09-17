---
status: accepted
date: 2026-09-16
---

# The Public origin stays open, and the Live tier's control group is the test host

The add-on serves two entrances: **Ingress** through the Supervisor's
authenticated iframe, and the **Public origin** through the Cloudflare
tunnel on port 8069. The Public origin fails closed: until an HTTPS
`public_url` is set, nginx answers every off-LAN request with `503`, and
with it set, any other `Host` gets `444`. Issue #59 asked whether to open
the Public origin at all, because the Ingress / Public parity plan
(`docs/testing/INGRESS_VS_PUBLIC_PARITY.md`) treats the Public origin as
the control group that Ingress is measured against, and a survey of the
production host on 2026-09-08 found it closed.

We decided:

- **The Public origin stays open.** A Deploy that must be reachable from
  the internet sets `public_url` (HTTPS) together with `default_db`. The
  maintenance bootstrap then writes `web.base.url` to that origin and sets
  `web.base.url.freeze` on every start, so an admin login through Ingress
  can never write the Supervisor token into `web.base.url`.
- **The control group is the test host's Public origin,**
  `https://woowtech-odoo-test-6.woowtech.io` (host 192.168.2.6, database
  `odoo_test`), not production. Every Live-tier item that writes data
  (archive, delete, import, large upload) runs only there.
- **The Odoo on the production host 192.168.2.189 was retired on
  2026-09-16** (commit 835ab58, issues #59 and #61). Its origin
  `https://woowtech-odooo.woowtech.io` was removed from the Cloudflare
  tunnel routing and from DNS, and from the `ODOO_PUBLIC_URLS` repository
  variable; the add-on is stopped with its data kept and a backup taken.

## Considered options

- **Keep the Public origin closed.** Rejected: everything the parity plan
  files under `RC-10` (external inbound traffic: payment callbacks, public
  survey answers, embedded live chat, job applications, anonymous website)
  would have no path at all, and the plan's rule that a capability with no
  Ingress implementation and no Public origin fallback is a Blocker would
  mark the whole commercial module list as unusable.
- **Use the production origin as the control group.** Rejected: the
  destructive Live-tier items would run against real data, the host was
  already slated for retirement, and on 2026-09-14 all Deploy work moved to
  the test host.
- **Give the test host no Public origin and compare Ingress only.**
  Rejected: without a control group none of the parity plan's `U-xx`
  items can be judged.

## Consequences

- The test host carries its own Cloudflare hostname, `public_url` and
  `default_db`. It is the only entry in `ODOO_PUBLIC_URLS`, so the daily
  Perimeter check verifies that its database lifecycle routes stay closed.
- The parity plan's P-Check is rerun before each execution rather than
  recorded in the plan; the values measured on 2026-09-16 (P-1 to P-4,
  P-6, P-8 green) live in issue #59.
- The E2E account on the test host is created through the add-on's
  `bootstrap-user.json` hook, which the add-on deletes after use; changing
  the account means writing the file again and restarting.
- `website.domain` is not set by the add-on today, so P-5 stays open until
  the bootstrap gap tracked in #57 is closed.
- A bare Odoo login page shows only "Powered by Odoo" until its stylesheet
  loads; the Perimeter check therefore polls for rendered text instead of
  sampling once (PR #63).

## Postscript (2026-09-17)

The test host stops once Ingress is confirmed on the parity plan's 25
applications. ADR 0005 moves the checks it served into the add-on: the
Perimeter check's schedule is removed in favour of a start-time self-check,
and the Literal rewrite gate becomes the in-container Rewrite scan. The
Public origin decision above is unchanged.
