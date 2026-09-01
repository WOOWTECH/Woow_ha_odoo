# Odoo Dual-Gateway Adversarial E2E Matrix

Every release must test both entrances: Cloudflare root and an HTTPS Supervisor-token prefix. A page is a failure if it is blank, escapes its expected origin/prefix, returns 5xx, has a failed request, or emits an unapproved console error.

## Recursive user journeys

1. Anonymous Website: `/`, `/shop`, `/shop/cart`, `/contactus`, search and static assets.
2. Authentication: login form visible, bad login error, valid login, logout, protected-route redirect, session cookie flags/path.
3. Backend: `/odoo`, Discuss, app menu, browser back/forward, refresh/deep link.
4. Cross-surface: backend → Website → shop/cart/contact → portal `/my/home` → backend.
5. Data operations: JSON-RPC common/object allowed; DB service denied publicly; XML-RPC DB denied; attachment round-trip; PDF report.
6. Realtime: `/websocket` upgrade, worker bundle, no root-prefix escape.
7. Security perimeter: public DB web/RPC routes denied, unexpected Host denied, LAN host port closed, internal DNS expected Host accepted, query/Referer secrets absent from logs.
8. Worker matrix: rendered nginx and startup with workers=0 (8070) and workers>0 (8072).
9. Recovery: cold backup exists, secrets rotate, failed bootstrap remains fail-closed, rollback origin documented.

## Scoring

- Blocker: blank page, authentication failure, origin/prefix escape, DB lifecycle exposure, data loss, 5xx, broken WebSocket.
- Important: one basic route has 4xx/failed asset/console exception, cookie or redirect inconsistency, worker-mode mismatch.
- Minor: cosmetic/layout-only defect with all operations usable.

Release gate: zero blockers, zero important findings on the supported HTTPS HA and Cloudflare paths. Minor findings must be documented.

## Commands

- Static: `bash odoo18ce/tests/test-dual-gateway.sh`
- JSON-RPC policy: `python3 odoo18ce/tests/test-jsonrpc-filter.py`
- Browser: `ODOO_BASE_URL=... ODOO_TEST_LOGIN=... ODOO_TEST_PASSWORD=... python3 odoo18ce/tests/e2e_adversarial.py`
- Run the browser command once with the Cloudflare base and once with the tokenized ingress base/harness.
