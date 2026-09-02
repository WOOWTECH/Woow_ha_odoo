# Odoo Commercial Dual-Surface Predeployment Test Plan

## Contract

Run every scenario against the same database through both gateways:

- `ingress`: actual authenticated Home Assistant sidebar iframe
- `public`: `https://woowtech-odooo.woowtech.io`

The current database is explicitly authorized for destructive testing. Every created record uses run marker `WOOW-E2E-<UTC timestamp>`. External payments, SMS, and email must use test/disabled providers; never invoke a live provider accidentally.

A checkpoint fails for any blank screen, unexpected dialog, `pageerror`, console error, failed request, unexpected HTTP >=400, route escape, duplicate ingress token, missing realtime update, semantic state mismatch, or cleanup failure.

## Phase 0 — Inventory and fixtures

1. Capture installed modules, accessible apps, all first/second/third-level menus and action/view types.
2. Capture Website sitemap/navbar pages, portal tiles, payment providers, warehouses, journals, POS configs and report actions.
3. Create test partner/customer/vendor, portal user, stockable/service products, channel, calendar attendees, price list and deterministic Unicode attachment.
4. Record IDs in a run ledger. Never select pre-existing business records for destructive actions.

## Phase 1 — Authentication and shell

- Invalid login, valid login, logout, relogin, password reset link.
- Cookie Secure/Path/SameSite parity appropriate to each gateway.
- Back, forward, reload, copied deep link and mobile viewport.
- App launcher and every menu action to depth 3.

## Phase 2 — Backend views and buttons

For every installed app/menu:

- Open list, kanban, form, calendar, graph, pivot and activity views when available.
- Search, filter, group, favorite, pagination, sort, column toggle.
- Create, Save, Edit, Discard, Duplicate, Archive, Unarchive, Delete.
- Open every visible action/gear/dropdown button and close every dialog.
- Compare record identity and state through the opposite gateway after each mutation.

## Phase 3 — Discuss and realtime

- Two concurrent contexts: ingress user A and public user B.
- Create channel, invite member, send/reply/edit/delete message, reaction, mark unread/read.
- Upload/preview/download/delete attachment.
- Require worker bundle 200, WebSocket 101 and bidirectional message delivery <=10s without refresh.
- Repeat workers=0 and temporary workers=2, then restore workers=0.

## Phase 4 — Calendar

- Create event, recurring event, invite attendee, edit, reschedule by UI, switch calendar/list views, delete occurrence/series.
- Verify counters and event state on opposite gateway.

## Phase 5 — Website and eCommerce

- Enter Website through app launcher, open editor, create isolated E2E page, add/edit text and image snippet, save, publish/unpublish, verify public render, then delete page.
- Test all navbar/sitemap pages, language switch, search and Contact validation/submission.
- Publish E2E product, product detail, variant, add/update/remove cart, checkout address/delivery, test/manual payment, confirmation and portal order; cancel/cleanup created order.

## Phase 6 — Invoicing

- Create customer invoice from E2E partner/product, edit lines/taxes, save, confirm/post, PDF print/download, register test payment, reverse/cancel where allowed.
- Create vendor bill and credit note.
- Verify journal entries and cleanup/reversal state rather than deleting posted accounting entries illegally.

## Phase 7 — Inventory

- Create stockable E2E product, inventory adjustment, receipt, internal transfer, delivery, validate/backorder, return and scrap where available.
- Verify on-hand/forecast values through both gateways and restore quantity to baseline.

## Phase 8 — Point of Sale

- Use/create E2E POS configuration and test payment method.
- Open session, create order, add/remove product, quantity/discount, payment, receipt, refund, close session and verify backend order/accounting state.

## Phase 9 — Portal, reports and binary

- Portal home/list/detail for every populated tile, pager, breadcrumb, message and download.
- Negative cross-user authorization.
- Every available PDF/report action for created fixture records: HTTP 200, `application/pdf`, `%PDF`, nonzero size and fixture marker.
- Attachment upload/download SHA-256 parity across gateways.

## Phase 10 — Apps and Settings

- Visit every settings section and use Save/Discard on reversible E2E changes.
- Install then uninstall only a dedicated harmless E2E module; never uninstall production modules.
- User/group create/edit/archive and access-right verification.
- Verify Database Manager remains ingress-only and public DB RPC filters remain enforced.

## Phase 11 — Cleanup and release gate

- Remove/archive all E2E records in dependency-safe order; reverse accounting/stock records according to Odoo rules.
- Restore Website, POS, workers and settings baselines.
- Confirm no E2E marker remains except the approved persistent test account and audit ledger.
- Store gateway-specific screenshots, HAR/network summaries, console/page errors, database IDs, state transitions, commands and residual risks.

Release requires zero blockers and zero important findings. Any skipped button requires an explicit reason and approval.
