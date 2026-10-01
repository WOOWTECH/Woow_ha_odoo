---
status: accepted
date: 2026-09-28
---

# An unattended Iteration may deploy to the test host and run Live-tier checks that write

[ADR 0003](0003-public-origin-stays-open-test-host-is-the-control-group.md)
settled **where** a Live-tier item that writes data runs: the test host, never
production. It did not settle **who** may run it. Until now the standing
permission for an agent working this repository covered read-only Live runs
only — a crawl, a diff, a perimeter check — and anything that wrote Odoo data,
deployed the add-on or touched the host over SSH waited for the maintainer.

That boundary was drawn when agents worked interactively, with the maintainer
reading each step. Work is now driven by unattended Sweeps
(`docs/agents/issue-tracker.md`), and the boundary has started to cost:

- **#168** decided that a tab Odoo opens from Ingress is a Structural gap, and
  shipped the decision, the verdict helper, the plan rows and the user
  documentation. Its second acceptance box — record `U-C23` under the new rule
  **on a rerun** — needs the P-7 survey fixture and creates a survey answer, so
  the Iteration could not run it. The Issue closed with the box unticked and
  the owed run named only in prose, which is why #183 had to be opened by hand
  afterwards.
- **#157** could not exercise its `docker load` gate at all, for a different
  reason (no Docker in the agent's container), and stopped short of merging.

We decided: **an Iteration of a Sweep may deploy to the test host and run
Live-tier checks that write, without asking first, inside the boundary below.**
A verification only a human can start is a verification that does not happen on
the day the work is built.

## The boundary

- **One host.** The HA OS test host, reached as `ssh ha` from the agent
  container. Its LAN address stays out of this repository (ADR 0003); the alias
  and the key live in the container's own SSH configuration. No other host, and
  no customer or production Odoo — including the instances reachable through
  the `woowtech_odoo` MCP server, which are not a verification surface.
- **Its two add-ons and their databases.** The Released `1b7b4ce7_odoo18ce` and
  the local build `local_odoo18ce`; the databases `odoo_parity`, `odoo_test`,
  and any database a run creates for itself. Restarting, updating, locally
  rebuilding and reconfiguring those add-ons is inside the boundary. Home
  Assistant's own configuration, its other add-ons, the network and the
  Supervisor are not.
- **Data a run creates is named after the run.** The `--run-id` marker the
  parity scripts already carry, so the host's state stays readable to the next
  person. A run does not delete another run's fixtures, and does not drop a
  database it did not create.
- **Credentials are read, never printed and never copied.** They live in the
  git-ignored `.env` of the main checkout and in the host's own environment
  file. Nothing from either is written into the repository, an Issue, a pull
  request or a commit message.
- **Evidence is recorded** under `docs/testing/evidence/<date>-issue-<n>/` in
  the shape the existing runs use, and what the run recorded is what the parity
  plan says afterwards.
- **Money and third parties stay human.** An ECPay stage payment needs a real
  card in a real browser and is out of scope, as it was before.

## Considered options

- **Keep the read-only boundary.** Rejected: it turns every verifying run into
  a human turn, and an Issue whose acceptance criteria need one closes with
  them unticked, or waits. Both happened in one Sweep.
- **Give the agent a second, disposable host.** There is none, and a parity
  control group that is not the control group answers a different question.
- **Widen the permission to any host the agent can reach.** Rejected: what
  makes writes safe here is that this host is the control group and nothing on
  it is anybody's production.

## Consequences

- `docs/agents/live-tier.md` is the operational half: what to run, in which
  spellings, and what to leave behind.
- `.claude/settings.json` pre-approves those spellings, so an unattended
  process does not stall on a permission prompt it has nobody to answer.
- An Issue whose only remaining work is a Live run on the test host can be
  `ready-for-agent` rather than `ready-for-human` — #183 is the first.
- The container's route to the host is a single firewall rule that does not
  survive a reboot, and is held outside this repository. A run that cannot
  reach the host degrades to the Static tier and says so in its record; it does
  not loosen anything itself.
- A Live run is still a Live run: it is slow, it needs the host to be free, and
  two Sweeps must not drive it at once.

## Postscript (2026-10-01, #228)

One constraint on the write accounting above, decided on #225 and built by
#228. "Data a run creates is named after the run" bounds **where** a Live
write may land; it says nothing about whether the second surface still has
something to judge after the first surface's write. The dual-surface `open`
run reaches Odoo routes that write while rendering a plain GET
(`GET_WRITING_ROUTES` in `odoo18ce/tests/e2e_menu_action_adapter.py`), and
one of them — `/shop/payment/validate` — confirms the draft order into a
sale and resets the cart, so whichever surface opens it first leaves the
other nothing to compare.

A targets file may therefore name such a route only when its write
**converges**: a second visit re-derives the same state and renders the same
screen — a recompute or a re-store, never an accumulation and never a
consumption. A route that consumes the fixture, and any route nobody has read
against that rule, is a configuration error refused **on every database,
`odoo_parity` included**, before a browser launches. Convergent routes keep
the `odoo_parity` bound this ADR's boundary already gives them, unchanged.

Nothing above is withdrawn: the boundary still permits the write, and the
refusal is narrower than the boundary rather than an exception to it. What it
adds is that a run inside the boundary can still be a run whose evidence
means nothing, and that the guard — not the reviewer of the evidence — is
where that is caught. The rule, each route's class and the reason for it live
beside the list in the adapter; `ensure_cart` leaving a non-empty cart alone
is the precedent it was read off.

## Postscript (2026-10-01, #227)

What "read-only" bounds, written down because this record uses the phrase
twice and every Issue that quotes the boundary inherits it. A read-only Live
run makes **no business writes**. It does not leave **zero rows**, and never
has on a database with `website` installed.

The target-seam guard #212 built — `GET_WRITING_ROUTES` in
`odoo18ce/tests/e2e_menu_action_adapter.py`, under the convergence rule of the
postscript above — bounds **navigations to routes that write by design**: a
route a targets file names, whose write was read out of the pinned `.deb` and
classified. Two writes sit outside that seam, were read during the same audit,
and cannot be bounded by any list keyed on a route:

1. **Visitor tracking fires on any tracked page's GET.**
   `website/models/ir_http.py:203` calls
   `website.visitor._handle_webpage_dispatch` with the `website.page` the
   response rendered, whichever module served the route; that upserts a
   `website.visitor` row and inserts a `website.track` row in one statement
   (`website/models/website_visitor.py:288-300` and `:239-251`). The gate is
   `:202`, and what it tests is the `track` flag of the template in the
   response's `qcontext` rather than the route — the page record itself is often
   `False` — so the same route writes on one website and not on another. The
   gate's other half, `not request.env.cr.readonly`, bounds nothing on this
   add-on: cont-init configures no `db_replica_host`, so
   `Registry.cursor(readonly=True)` hands back a read/write cursor and the write
   lands anyway; the full reading of that is beside `GET_WRITING_ROUTES`.
   Bounding this write would mean bounding every website page a target can name
   (`/`, `/contactus`, `/shop`), which is a decision about whether `open` may
   judge a website page off `WRITE_DATABASE` at all, and that is the read-only
   guarantee as a whole rather than one seam in it. Any run that opens a website
   page makes this write: the adapter's `open` with a website target, and the
   hand-check driver's `visit` (`odoo18ce/tests/e2e_ingress_hand_checks.py`),
   which exists to make it — `U-C5` for #160 is judged from the row, not from
   the page. `crawl` is the exception: it navigates only `/odoo/action-<id>`,
   whose response is the web client bootstrap and not a tracked page, so a crawl
   never makes it.
2. **A page writes through its own markup and its own JavaScript.** The
   `website_sale` header renders the cart link from `website.sale_get_order()`
   (`website_sale/views/templates.xml:13`, on any request whose session carries
   no `website_sale_cart_quantity`), and that moves the draft order onto the
   logged-in partner when the two disagree, exactly as `/shop/checkout` does
   (`website_sale/models/website.py:457`) — so a page whose controller writes
   nothing can still write. And the target's GET is not the whole navigation: a
   product page's own JavaScript calls `/shop/products/recently_viewed_update`
   (`website_sale/static/src/js/website_sale_recently_viewed.js:44`, whose route
   is `website_sale/controllers/main.py:2288`), which creates a
   `website.visitor` and records a viewed product — once per product per half
   hour, since a cookie guards the call. What a loaded page requests on its own
   account is not a target, and no pre-flight over a targets file sees it.

Both are harmless **by content**, which is why the guarantee is restated rather
than withdrawn: they carry page-view telemetry and no business state — no
order, invoice, journal entry or setting, nothing a parity verdict reads and
nothing another run's fixtures stand on. They are also not new. The
2026-10-01 #235 run counted them in its own record: 19 new `website.track`
rows written by its page views
(`docs/testing/evidence/2026-10-01-issue-235/README.md`), and check 5 of that
run — #160's visitor-URL check, a `U-C5` reading — *reads* one of those rows
back as its measurement. For that check the ambient write is the instrument,
not only a side effect.

So the guarantee is quoted as **no business writes**, not as zero rows, and the
boundary above is unchanged: nothing here widens what a run may touch. Making
a run *name* these ambient writes in its own evidence — a `website.track` count
delta per run — is a feature with an Issue of its own (#256), not part of this
statement. `GET_WRITING_ROUTES`' comment points here rather than carrying the
only copy, and the citations are read from the Odoo the add-on pins
(`ODOO_DEB_VERSION`, `odoo18ce/Dockerfile`) the way that list's are.
