# CLAUDE.md

## Branch and release rules

Read `AGENTS.md` first: the default branch only changes through a PR that passes the required checks, and a version bump is a release.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `WOOWTECH/Woow_ha_odoo`, driven via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Live tier and the test host

No test host exists right now (2026-10-27, #314), so every Live-tier item falls back to the Static tier as `docs/agents/live-tier.md` describes. Only once a new test host is provisioned may an Iteration again deploy to it and run Live-tier checks that write, inside the boundary of [ADR 0012](docs/adr/0012-sweeps-verify-on-the-test-host.md); how to run one is in `docs/agents/live-tier.md`.

### Domain docs

Single-context — `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
