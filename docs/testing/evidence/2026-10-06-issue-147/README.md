# Mobile on real devices (#147)

Handoff #12, the last item of Epic #148. A person walked the Ingress
entrance on two real phones on 2026-10-06, against the test host's Released
add-on `1b7b4ce7_odoo18ce` at **0.4.11**, database **`odoo_parity`** (the 29
modules of #144). The viewport-emulation half is the 390x844 crawl in #143;
this round covers what emulation cannot show: the Home Assistant Companion
app and the mobile browsers.

- **Entrances**: `<HA_BASE_HTTP>` is Home Assistant over plain http on the
  LAN; `<HA_BASE_HTTPS>` is the HTTPS HA entrance, reached with the phone's
  Wi-Fi off, so the Companion app used its external URL.
- **Recording**: an interactive checklist; one record per device, app and
  scheme, with a verdict and a note per item. The records are in
  `runs.json`, with the HA addresses, Ingress prefix and survey token
  replaced by placeholders. The one screenshot is `ios-app-http-blank.jpg`.
- **Writes** (ADR 0012): the survey Test button creates a survey answer, and
  the POS scan added a line to the open Furniture Shop order (the steps
  said to delete the line and not pay). Nothing on the host or the add-on
  changed.

## Devices

| Device | OS | Apps |
|---|---|---|
| Xiaomi, HyperOS 2.0.205.0.VBNTWXM | Android 15 (AP3A.240905.015.A2) | Chrome (version not recorded); Home Assistant Companion **2026.6.5-full** |
| iPhone 12 | iOS 18.7.8 | Safari (ships with iOS); Home Assistant Companion **2025.5** |

## Items

| # | Item | What was done |
|---|---|---|
| 1 | Log in | HA login, then Odoo's login inside the panel |
| 2 | Open a record | Quotation `S00030` |
| 3 | Copy | Discuss channel, Invite, the invitation link's copy button, then paste into another app |
| 4 | PDF download | `S00030`, Print, Quotation / Order |
| 5 | Export download | Quotations list, select rows, Export, xlsx |
| 6 | `target=_blank` | Survey `WOOW-PARITY-20260929T045315Z Survey`, **Test** |
| 7 | Barcode scan | POS till, the top bar's barcode button (see "Inventory" below). Over https: camera opened, the Desk Organizer barcode `2300001000008` was added. Over http: the button is absent, as expected on an insecure page |

## Results

Verdict words as in the parity plan: `PARITY` means Ingress does what the
Public origin does, `STRUCTURAL` is a Structural gap with the Public origin
path that carries it.

### Android, Chrome

| Item | http | https |
|---|---|---|
| 1 Log in | PASS | PASS |
| 2 Open a record | PASS | PASS |
| 3 Copy | PASS | PASS |
| 4 PDF download | PASS | PASS |
| 5 Export download | PASS | PASS |
| 6 `target=_blank` | PASS | PASS |
| 7 Barcode scan | PASS (no button) | PASS |

### Android, Companion app 2026.6.5-full

| Item | http | https |
|---|---|---|
| 1 Log in | PASS | PASS |
| 2 Open a record | PASS | PASS |
| 3 Copy | PASS | PASS |
| 4 PDF download | PASS | PASS |
| 5 Export download | PASS | PASS |
| 6 `target=_blank` | `STRUCTURAL` | `STRUCTURAL` |
| 7 Barcode scan | PASS (no button) | PASS |

### iOS, Safari

| Item | http | https |
|---|---|---|
| 1 Log in | PASS | PASS |
| 2 Open a record | PASS | PASS |
| 3 Copy | PASS | PASS |
| 4 PDF download | PASS | PASS |
| 5 Export download | PASS | PASS |
| 6 `target=_blank` | `PARITY` (blocked on both surfaces) | `PARITY` (blocked on both surfaces) |
| 7 Barcode scan | PASS (no button) | PASS |

### iOS, Companion app 2025.5

| Item | http | https |
|---|---|---|
| 1 Log in | PASS | PASS |
| 2 Open a record | PASS | PASS |
| 3 Copy | PASS | PASS |
| 4 PDF download | PASS | PASS |
| 5 Export download | PASS | PASS |
| 6 `target=_blank` | `PARITY` (blocked; see below) | `PARITY` (blocked; see below) |
| 7 Barcode scan | PASS (no button) | PASS |

**56 item runs: 49 PASS, 2 `STRUCTURAL`, 5 `PARITY`; no `GAP`, no new issue.**
On every device and in both apps, copy works over plain http through the
add-on's fallback, and both downloads land.

## Item 6 on the Android Companion app: `STRUCTURAL`

The app does not open a new window inside its WebView: it hands the tab to
the system browser. The tab's address is the Ingress one,
`<HA_BASE><INGRESS_PREFIX>/survey/test/<token>` (the http record; the https
note recorded only the prefix), and the system browser has no Home Assistant
session, so Ingress answers **401: Unauthorized** (the same answer as
`AD-6`/`U-B8`). The same phone in Chrome passes, because there the tab stays
in the browser that holds the session.

Decided by the maintainer on 2026-10-06: a Structural gap under `G-07`
(RC-15). To Home Assistant, the other app is an anonymous caller, and the
add-on cannot carry Home Assistant's session into it. #168 already rejected
the other route, opening such tabs on the Canonical URL. The Public origin
carries it: the same screen opened at `<PUBLIC_BASE>/survey/test/<token>`.
`odoo18ce/DOCS.md` "What only the Public origin can do" and the parity
plan's `G-07` row now say so.

## Item 6 on iOS: `PARITY`

All four iOS runs show Odoo's own warning, "A popup window has been blocked.
You may need to change your browser settings to allow popup windows for this
page." (`ios-app-http-blank.jpg`). This is Odoo's code, not the browser's:
the Test button is a `type="object"` button, so the web client first calls
`action_test_survey` over RPC, receives an `ir.actions.act_url` with
`target: new`, and only then calls `browser.open(url, "_blank")`
(`web/static/src/webclient/actions/action_service.js:1127` in the installed
package). By then the tap's user activation is gone, WebKit refuses the
popup, and Odoo shows the warning when `window.open` returns nothing.

**Control**: the same survey's Test button in iPhone Safari on the **Public
origin** showed the same warning. Ingress and the Runtime shim's
`window.open` wrapper are therefore not the cause; Safari records `PARITY`.
The Companion app on iOS renders in WebKit too and has no Public origin
entrance of its own; its two runs record `PARITY` on the strength of the
Safari control and the identical code path, not on a control of their own.

## Inventory: no camera scan in Community

The issue asked for a barcode scan in Inventory. Odoo 18 Community has no
camera scan there: the Inventory barcode app, `stock_barcode`, is
Enterprise (`uninstallable` on this database), and no Community Inventory
view sets the many2one `can_scan_barcode` option, the only other place the
web client offers a camera button on a phone. POS's barcode button is the
camera scanner Community has, so item 7 was run there; the event
registration desk and the attendance kiosk scanners were covered on desktop
in #143 (`U-C25`).

## Not covered

- The Chrome version on Android was not recorded.
- The iOS Companion app is **2025.5**, older than the Android one; a newer
  build was not tried.
- One phone per platform; no tablet.
