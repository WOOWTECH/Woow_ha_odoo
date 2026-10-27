# Odoo Dual-Gateway Adversarial E2E Matrix

Every release must test both entrances: Cloudflare root and an HTTPS Supervisor-token prefix. A page is a failure if it is blank, escapes its expected origin/prefix, returns 5xx, has a failed request, or emits an unapproved console error.

## Recursive user journeys

1. Anonymous Website: `/`, `/shop`, `/shop/cart`, `/contactus`, search and static assets.
2. Website editor: click the Website app from the backend, load `/website/iframefallback`, `/web/bundle/website.assets_all_wysiwyg_inside`, then assert both generated WYSIWYG CSS/JS assets return 200 without `AssetsLoadingError`.
3. Authentication: login form visible, bad login error, valid login, logout, protected-route redirect, session cookie flags/path.
4. Backend: `/odoo`, Discuss, app menu, browser back/forward, refresh/deep link.
5. Cross-surface: backend → Website → shop/cart/contact → portal `/my/home` → backend.
6. Data operations: JSON-RPC common/object allowed; DB service denied publicly; XML-RPC DB denied; attachment round-trip; PDF report.
7. Realtime: `/websocket` upgrade, worker bundle, no root-prefix escape.
8. Security perimeter: public DB web/RPC routes denied, unexpected Host denied, LAN host port closed, internal DNS expected Host accepted, query/Referer secrets absent from logs.
9. Worker matrix: rendered nginx and startup with workers=0 (8070) and workers>0 (8072).
10. Recovery: cold backup exists, secrets rotate, failed bootstrap remains fail-closed, rollback origin documented.

## Scoring

- Blocker: blank page, authentication failure, origin/prefix escape, DB lifecycle exposure, data loss, 5xx, broken WebSocket.
- Important: one basic route has 4xx/failed asset/console exception, cookie or redirect inconsistency, worker-mode mismatch.
- Minor: cosmetic/layout-only defect with all operations usable.

Release gate: zero blockers, zero important findings on the supported HTTPS HA and Cloudflare paths. Minor findings must be documented.

The `U-A4` item of the gate (`docs/testing/INGRESS_VS_PUBLIC_PARITY.md`) is met without a host (ADR 0005, ADR 0008): the Static tier covers the rewrite rules and the rendered nginx template with the Generated rewrite include, and the add-on's own Rewrite scan turns every `FAIL` (an unlisted prefix in a whole-page navigation) into a Generated rewrite at run time. `WARN` (a path comparison) is never rewritten and `INFO` is only listed (ADR 0004).

The Literal rewrite gate, `odoo18ce/tests/e2e_literal_rewrite_gate.py`, stays as an optional outside-in acceptance check of the same analysis against a Public origin. `--include-file` counts a copy of the host's Generated rewrite file as registered rules, and `--from-dir` re-evaluates saved bundles. It needs a host, so it does not block a Release; `.github/workflows/literal-rewrite-gate.yml` runs it on dispatch only.

## Commands

- Static tier (manifest, gateway, JSON-RPC policy, ingress rewrites): `pytest odoo18ce/tests` with nginx and node installed
- Browser: `ODOO_BASE_URL=... ODOO_TEST_LOGIN=... ODOO_TEST_PASSWORD=... python3 odoo18ce/tests/e2e_adversarial.py`
- Literal rewrite gate (optional): `ODOO_BASE_URL=... ODOO_TEST_LOGIN=... ODOO_TEST_PASSWORD=... python3 odoo18ce/tests/e2e_literal_rewrite_gate.py` (Public origin only; `--from-dir <artifacts>/bundles` re-evaluates a saved collection without a browser)
- Run the browser command once with the Cloudflare base and once with the tokenized ingress base/harness.
