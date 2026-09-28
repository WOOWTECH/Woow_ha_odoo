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
