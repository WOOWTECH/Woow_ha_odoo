# Odoo Dual Ingress + Cloudflare Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run one Odoo 18 backend behind two controlled nginx entrances: HA Ingress for `/odoo` and a full Cloudflare public origin, with no LAN host port exposure.

**Architecture:** Pin Odoo 18.0-20260806, move Odoo to localhost:8070, and enable proxy mode because only local nginx can reach it. nginx listens on internal-public 8069 for Cloudflare and ingress-only 5691 for Supervisor; `/websocket` automatically targets 8070 for workers=0 or gevent 8072 for workers>0.

**Tech Stack:** Home Assistant add-on, Debian/s6-overlay, Odoo 18 CE, PostgreSQL 16, nginx, Cloudflare Tunnel, Playwright.

---

1. Add failing manifest/nginx/version-pin tests.
2. Pin the Odoo Debian package and checksum; install nginx.
3. Generate Odoo and nginx configs from HA options, including internal ports and worker-aware WebSocket routing.
4. Add public gateway rules and block public database management endpoints.
5. Add ingress path rewriting, cookies, redirects, OWL runtime URLs, forms, assets, and WebSocket.
6. Update docs, translations, changelog, and version.
7. Validate and merge canonical repository, then sync Woow_HA_App_Store.
8. Create a cold backup and rotate Odoo/PostgreSQL secrets.
9. Deploy add-on; verify internal DNS before removing host mappings.
10. Update existing Cloudflare tunnel origin to `http://1b7b4ce7-odoo18ce:8069`.
11. Create persistent test user, grant admin during E2E, then downgrade to Internal User.
12. Run Playwright/API/WebSocket/upload/report/security checks and document rollback evidence.
