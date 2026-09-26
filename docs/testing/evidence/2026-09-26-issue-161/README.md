# POS offline on both surfaces (#161)

Run `WOOW-PARITY-20260926T032235Z`, 2026-09-26, against the test host's Released add-on
`1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`** (the 29 modules of #144), POS config
"Furniture Shop". Driver: `odoo18ce/tests/e2e_pos_offline_live.py`, with static tests for its pure
parts in `test_e2e_pos_offline.py`.

- **Public side**: a top-level page on the Public origin.
- **Ingress side**: Odoo in its Ingress iframe inside the Home Assistant frontend, over the
  plain-http LAN entrance. These are the same two sides as #143 and #145.
- The network was cut with the browser's offline emulation (Playwright `set_offline`), for the
  whole browser context. The host's network was not touched.

## Unsticking POS

State before: session `POS/00001` (id 4) was `opened` with **0 orders**, started 2026-09-24
15:05 UTC. `/pos/ui` hung on its splash screen on both surfaces (#144).

1. `pos.session.action_pos_session_closing_control` on `POS/00001` returned `true`, and the
   session is `closed` (stop 2026-09-26 03:09 UTC). It had no orders, so it made no journal entry.
   No SQL was used.
2. `/pos/ui?config_id=1` on the Public origin then loaded straight to the "Open Register" screen
   and created session `Furniture Shop/00002` (id 5) in `opening_control`. Opening Control >
   Open Register opened it, and Odoo renamed it `POS/00002`. The `pos_hr` lock screen ("Unlock
   Register") comes next, then the product grid. The splash-screen hang did not come back on the
   fresh session, on either surface.

The maintainer approved these writes (triage, 2026-09-25, and again in the session on
2026-09-26): closing `POS/00001`, one new session, one offline cash sale per surface, and closing
the session afterwards.

## Checks: `checks.jsonl`

| Check | Public origin | Ingress | Verdict |
|---|---|---|---|
| `U-C27` POS offline sale | the till showed "Connection Lost" and validated the sale. After reconnect, the order was on the server in 3 s | the same, 3 s | `PARITY` |
| `U-C27` POS offline reload | `net::ERR_INTERNET_DISCONNECTED` | `net::ERR_INTERNET_DISCONNECTED` | `PARITY` |

The sale on each side was one "Desk Pad" (NT$ 2) paid in cash. The run takes the order's `uuid`
from the till before it validates offline, then looks for that `uuid` on the server after the
network comes back:

| Surface | `pos.order` | Reference | Session | State after the run | Amount |
|---|---|---|---|---|---|
| Public origin | id 5, `Furniture Shop/0001` | `Order 00005-013-0001` | `POS/00002` | `paid`, then `done` when the session closed | 2.00 |
| Ingress | id 6, `Furniture Shop/0002` | `Order 00005-014-0001` | `POS/00002` | `paid`, then `done` when the session closed | 2.00 |

Signals are counted only while the browser is online, from loading `/pos/ui` to cutting the
network and again after reconnect. None were raised on either side. What failed while offline is in
each record's `offline_window`: on both sides, the same three assets the payment screen asks for
(a Roboto font, `money.png`, `card-bank.png`). They are not signals, because an offline browser is
expected to fail them. The masker also redacts the `session_id` key inside `server_order`. The
session is the one in the table above.

The reload check loads `/pos/ui` again with the network cut: `page.goto` for the Public origin,
and the Ingress iframe's own navigation under Ingress. Odoo 18 CE's POS has no service worker, so
nothing answers offline on either surface.

## After the run

`action_pos_session_closing_control` closed `POS/00002` (stop 03:24 UTC, journal entry
`POSS/2026/09/0003`). The config "Furniture Shop" has no open session now. The next run needs one
opened first: load `/pos/ui?config_id=1` and confirm Opening Control. The run's two orders stay on
`odoo_parity`. Nothing was deleted.

POS loads to a usable till again, so #143's POS items (`U-F5` receipt print, `U-C25` product scan)
are no longer blocked by the hang.

## What changed because of it

- ADR 0011 has a dated postscript: offline POS selling is not a Structural gap. The original text
  is unchanged.
- `DOCS.md`, "What only the Public origin can do": POS offline mode is gone from the service-worker
  row, which keeps PWA install and the offline page. A note under the table says that POS sells
  offline on both entrances.
- Parity plan: the `point_of_sale` rows of 10.1 and 10.4, the POS warning block and the `U-C27`
  row of section 6.
