# Odoo Developer-Mode Delta TDD Campaign

## Status

Approved test scope. This is a required prerequisite for commercial flow E2E.

## Goal

Exhaustively account for every visible, enabled control which appears in Odoo developer mode but not in ordinary mode, on both HA Ingress and public Odoo. Ordinary-mode semantic duplicates are recorded once and are not re-executed as developer-mode controls.

## Mode matrix

For each target (`woowtech`, `elmohome`, `mag-home`, `jzn`) and each available surface (HA Ingress and public):

1. normal (the baseline);
2. `debug=0` normalization check;
3. `debug=1` developer mode;
4. `debug=assets`;
5. `debug=tests`;
6. `debug=assets,tests`;
7. `debug=disable-t-cache`.

The add-on `dev_mode=true` / Odoo `dev_mode=all` is a separate, disposable local-image matrix. It must never substitute for browser/session developer-mode coverage.

## Discovery and identity

The test first inventories ordinary visible/enabled controls, then captures each debug-mode observation. A control identity is independent of ingress prefix, queries, fragments, translations, DOM order, and debug value:

```text
scope(route/action + view/model + record shape)
+ kind(menu | registry-item | view-node | command | widget)
+ origin(module+xmlid | debug registry key | model.field | stable DOM fallback)
+ canonical target(action | RPC | route | field)
+ role
+ untranslated semantic name
```

For each mode, `debug_delta = debug_controls - ordinary_controls`. Matching requires one unique identity on each side; ambiguity is a failure, never resolved by DOM position. Static prediction reconciles installed-module debug registry entries, Technical navigation, and applicable `base.group_no_one` XML nodes. Every observed or predicted item must have one disposition.

```text
visible_enabled = ordinary_duplicate_suppressed
                + debug_only_executed
                + debug_only_blocked
                + debug_only_external_skip
                + explicit_not_applicable
```

Any remainder, ambiguous item, discovery error, unknown classification, or unlinked duplicate fails the campaign.

## Safety classes

- `read_only`: execute and assert route/dialog/semantic outcome.
- `local_diagnostic`: execute only with bounded local output.
- `mutation`: assert affordance in deployed E2E; execute only in a disposable target fixture with explicit rollback and cleanup verification.
- `external`: never execute against deployed targets; use local interception to prove no egress.
- `destructive`: never execute in shared deployed E2E; assert guard, disabled state, or permission behavior.

## TDD gates

1. **Red discovery contracts**: schema, canonicalization, uniqueness, delta, manifest conservation, public policy, and one failing contract for every discovered debug-only control.
2. **Minimal green**: implement a dedicated delta crawler. Reuse existing authentication, ingress frame recovery, sanitization, control isolation, and route policy; do not overload the menu crawler.
3. **Static and local**: fake external controls, identity tests, static prediction reconciliation, manifest-to-test mapping, rollback checks, nginx/gateway tests.
4. **Deployed HA and public**: run each applicable control in isolated contexts, preserve sanitized per-control evidence, and enforce declared public-debug policy.
5. **Cleanup**: verify fixture restoration, no pending jobs, and no external egress. Cleanup failure is a hard failure.

## Four-target scheduling

- `woowtech`: common harness baseline and HA ingress regression.
- `elmohome`: debug Technical navigation and view/action delta.
- `mag-home`: debug registry, assets, tests, profiling, and diagnostic delta.
- `jzn`: disposable mutation classification, rollback, external-egress interception, and public policy checks.

Each target has one mutation owner. All targets may run read-only discovery in parallel. A target must provide a sanitized logical endpoint/build mapping, least-privilege developer principal, public-debug policy, installed-module inventory, disposable fixture/rollback contract, and external-egress policy before its deployed lane begins.

## Evidence and continuity

Each control assertion emits sanitized `odoo-debug-evidence/v1` JSONL: target, surface, mode, build, stable control id, class, disposition, test id, selector digest, assertions, artifact references, cleanup state, and egress proof. No credentials, ingress tokens, raw URLs, query strings, cookies, or live fixture values may be persisted.

The campaign ledger records baseline hash, build, target/surface/mode state, approved exception rationale and expiry, owner, next command, and artifact locations. Commercial fixtures and commercial flows remain blocked until this task reaches `E2EVerified`.
