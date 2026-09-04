# Execution Continuity Protocol

**Status:** approved operating policy  
**Applies to:** all remaining Odoo implementation, deployment, and E2E work

## Purpose

Prevent a failed test, review finding, deployment problem, or missing permission from becoming an unowned pause. A status update is evidence, not a substitute for continuing the work.

## Required state model

Every planned test or implementation item has exactly one state:

- **Queued** — bounded acceptance criteria and next command are defined.
- **Running** — an owner and active command/run exist.
- **Blocked** — the specific dependency, evidence, owner, and next escalation are recorded.
- **Verified** — acceptance criteria have passed with preserved command output or deployed E2E evidence.

`Done` may only be reported for a verified item. A failed command leaves the item Running or Blocked; it never becomes implicitly deferred.

## Failure-to-next-action gate

For every failed test or review blocker:

1. Capture sanitized evidence: failing assertion, relevant route/log segment, changed files, and reproduction command. Never include passwords, ingress tokens, OAuth parameters, or credential-file contents.
2. Classify it as one of: product defect, test-harness defect, deployment/environment defect, authentication/permission dependency, flaky timing, or unknown.
3. Within **15 minutes**, create or start exactly one bounded follow-up:
   - a minimal red regression test and repair task for a product defect;
   - a harness repair/retry task for test defects;
   - a deployment diagnostic/remediation task for environment defects; or
   - an explicit request for the external decision/permission needed.
4. Define the next verification command before reporting the failure.
5. If a repair needs more than 30 minutes without new evidence, split it into a diagnosis task and independent tasks that do not require the blocked component.

A report that says only "blocked", "no progress", or "needs investigation" does not satisfy this gate.

## Parallel work and ownership

- One writer owns a repository/worktree at a time. Independent read-only reviews or independent worktrees may run in parallel.
- Shared production actions (database mutations, merge, deployment, configuration changes) remain serialized.
- When one lane is blocked, immediately schedule eligible independent lanes rather than wait idly. Do not begin destructive commercial flows until their prerequisites are verified.
- Every active lane declares: scope, acceptance test, expected duration, dependency, and artifact path.

## Test hierarchy

Use the smallest reliable level first, then promote only with evidence:

1. unit/source contract;
2. rendered configuration or service harness;
3. isolated browser flow;
4. deployed HA Ingress and public-browser E2E;
5. cross-surface parity and regression suite.

A browser failure must first determine whether the application, HA parent authentication, iframe lifecycle, browser harness, or network is responsible. A detached frame must trigger an independently recoverable test design, not invalidate subsequent controls.

## Status cadence and escalation

Provide an update at least every **60 minutes** while active work remains. Each update contains only current evidence:

- verified completions since the last update;
- active runs and their next gates;
- blockers with the already-started follow-up;
- changed overall completion percentage and remaining wall-clock estimate;
- risks that could change that estimate.

If no new evidence exists, state that plainly and explain which live run is expected to produce it. Do not re-label old evidence as new progress.

Escalate immediately to the user only for a required product decision, access/credential issue, unsafe/destructive action not previously authorized, or a material scope/estimate change. Otherwise continue automatically.

## Completion gates

A workstream is closed only when:

- all planned acceptance tests pass at the appropriate hierarchy level;
- deployed HA Ingress and public evidence exists where the feature is user-facing;
- review findings are resolved or explicitly accepted by the user;
- artifacts are sanitized and retained;
- no follow-up task is orphaned.

For Settings specifically, closure requires dynamic tab traversal, icon/network checks, administrator controls, dialogs, reversible Save/Discard behavior, HA/public parity where applicable, and a deployed run without iframe/auth-harness false positives.

## Immediate adoption

1. The active Settings-controls E2E task is the first protocol item. Its iframe-detach failure is classified as a harness/HA-parent lifecycle issue, with an independently recoverable browser design as its next gate.
2. After Settings closure, commercial test lanes are queued with explicit prerequisites and acceptance tests.
3. Each future failure is appended to the active test report with its classification, follow-up run, and verification command before the next status update.
