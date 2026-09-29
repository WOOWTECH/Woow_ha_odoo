# U-C25 rerun on 0.4.5: the #159 barcode-sound escape is gone (#203)

Run `WOOW-PARITY-20260929T045315Z` on 2026-09-29 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.5**, database **`odoo_parity`**.
Driver:

    e2e_parity_shared_layers_live.py run --only U-C25

`U-C25` needs a secure context for `getUserMedia`, so it runs over the **https**
Home Assistant entrance (`HA_HTTPS_BASE_URL`, set in `.env` for this run) with
Chromium's fake camera; the plain-http LAN entrance is not a secure context
(`U-F1`).

## Why this run

The last full reconciled set (#201) still carried one `GAP`:

    check:U-C25|event|event registration desk  ->  GAP (blocker, issue #159)

from #143's run `WOOW-PARITY-20260925T043539Z`, where the Event Registration
Desk's barcode **error sound** — built with `new Audio(url("/barcodes/.../error.ogg"))`
— resolved against the browser origin and escaped the Ingress prefix. #159
(PR #193) wrapped the media-source setters so it stays inside the prefix. That
fix had only Static-tier coverage until now.

## P-Check

`pcheck --db odoo_parity`, 2026-09-29, all PASS (P-1…P-6).

## Result — `checks.jsonl`

| Control identity | Verdict | Note |
|---|---|---|
| `check:U-C25\|shared\|generic` | **`PARITY`** | `getUserMedia` granted on both surfaces |
| `check:U-C25\|hr_attendance\|attendance kiosk badge scan` | **`PARITY`** | |
| `check:U-C25\|point_of_sale\|POS product scan` | **`PARITY`** | |
| `check:U-C25\|mrp\|MRP work order scan` | `NOT-RUN` | no camera control on the screen (both surfaces) |
| `check:U-C25\|event\|event registration desk` | `NOT-RUN` | no camera control on the screen (both surfaces) — see below |

**The `#159` escape signal is gone.** The Event Registration Desk row records
`NOT-RUN` because the screen presents no camera control for `U-C25`'s probe to
press — the same on **both** surfaces, so it is not an Ingress-specific
difference. But the five-signal comparison that made this row a `GAP` in #143 is
now clean:

| | #143 (`WOOW-PARITY-20260925T043539Z`) | this run (0.4.5) |
|---|---|---|
| Public | `route_escape=0`, `console_error=0` | `route_escape=0`, `console_error=0` |
| **Ingress** | **`route_escape=1`, `console_error=1`** (the escaping `error.ogg`) | **`route_escape=0`, `console_error=0`** |

The escape and the console error that flagged the barcode sound on desk load are
gone under Ingress on 0.4.5 — #159's media-source wrapping is confirmed live.

## Conservation (parity plan §12) — `reconciled.jsonl`

`reconciled.jsonl` is #201's reconciled set (76 records) with this run's five
`U-C25` records substituted. `conservation.json` is `report` over it:

    76 observed = 60 PARITY + 0 GAP + 2 APPROVED-DIVERGENCE + 6 STRUCTURAL + 8 NOT-RUN

Balanced; **no `GAP` remains** — the one that cited #159 is resolved. `report`
exits 1 for the same reason as #143/#172/#183/#201: the `NOT-RUN` set (now eight,
the U-C25 event/mrp screens added), each blocked outside the add-on's control.

## Still owed (#203, part 2)

This run confirms the sound no longer escapes on desk load, but `U-C25`'s
camera-driven scan path could not be exercised (no camera control on this
screen). The fuller guard — a **media-way probe in `U-A6`** that actively
triggers a failed-scan `new Audio` request and asserts it carries the prefix —
is the `RC-12` note's owed code change and remains open on #203.

## What the run left on the host

`fixtures` wrote the P-7 set, all named with the run marker
`WOOW-PARITY-20260929T045315Z`: `res.partner` 73, `product.template` 58,
`sale.order` 28, `survey.survey` 6, `event.event` 6, `hr.job` 4,
`discuss.channel` 15, `mrp.workcenter` 4, `project.task` 10, `ir.attachment`
1373, plus the admin's own quotation (29). `U-C25` itself writes nothing beyond
opening screens.
