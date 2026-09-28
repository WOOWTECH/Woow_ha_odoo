# CLAUDE.md

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `WOOWTECH/Woow_ha_odoo`, driven via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Live tier and the test host

An Iteration may deploy to the test host and run Live-tier checks that write, inside the boundary of [ADR 0012](docs/adr/0012-sweeps-verify-on-the-test-host.md). How to run one — credentials, the approved command spellings, evidence, and what to do when the host is unreachable — is in `docs/agents/live-tier.md`.

### Domain docs

Single-context — `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
