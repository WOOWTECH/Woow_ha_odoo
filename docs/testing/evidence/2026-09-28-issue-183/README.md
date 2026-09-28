# `U-C23` rerun under the Structural rule (#183)

Run `WOOW-PARITY-20260928T070408Z` on 2026-09-28 against the test host's
Released add-on `1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`**
(the 29 modules of #144). Driver:
`odoo18ce/tests/e2e_parity_shared_layers_live.py run --only U-C23`
(the decision itself is the pure `new_tab_verdict()` in
`e2e_parity_shared_layers.py`, with static tests in
`test_e2e_parity_shared_layers.py`). Unlike #172's rerun this one **writes**:
it needs the P-7 survey fixture, and pressing the survey's **Test** button
creates a survey answer on each surface. ADR 0012 is what authorises that.

This is the one acceptance box #168 could not tick by itself. #168 decided
(and shipped, `cedd13e`) that a tab Odoo opens from Ingress carries the
Supervisor session token in its address **by construction** — section 1.4's
`STRUCTURAL`, RC-15, `G-07` — carried by the Public origin's address of the
same page. The decision was already Static-tier tested; what was missing was
a Live round recording `U-C23` under it. This run is that round: it confirms
the address shapes on the host, not the decision.

## P-Check

`pcheck --db odoo_parity`, 2026-09-28, all PASS. **P-5** matters most here:
`website.domain` is the Canonical URL the Public tab's address is compared
against, so a run on a failing P-5 would judge the Public half against
nothing.

| ID | Result |
|---|---|
| P-1 | PASS: `public_url` is https |
| P-2 | PASS: `GET /web/login` -> 200 |
| P-3 | PASS: `web.base.url` = `<PUBLIC_BASE>` |
| P-4 | PASS: `web.base.url.freeze` = `True` |
| P-5 | PASS: `website.domain` = `['<PUBLIC_BASE>']` |
| P-6 | PASS: the same login on both surfaces, both serving `odoo_parity` |

## Checks — `checks.jsonl`

| Control identity | Verdict | Public tab | Ingress tab |
|---|---|---|---|
| `check:U-C23\|shared\|generic` | **`STRUCTURAL`** (severity `none`, `RC-15`) | `<PUBLIC_BASE>/survey/<token>` | `<HA_BASE><INGRESS_PREFIX>/survey/<token>` |

`public_path` on the record is `<PUBLIC_BASE>/survey/<token>` — the address
to share, and the whole reason the Ingress shape is not a defect. Both tabs
opened, both rendered the same page (`This is a Test Survey Entry. / Go to
Survey / WOOW-PARITY-20260…`), the route on each side of its own base is the
same (`/survey/<token>`), and no signal fired on the page that opened the tab
(`console_error`, `pageerror`, `failed_requests`, `http_4xx_5xx`,
`route_escape` all 0). Those are exactly the statements `new_tab_verdict()`
requires for `STRUCTURAL`; the directions that would make it a `GAP` (`G-07`)
instead — a tab that does not open, one off the Ingress prefix or off the
Canonical URL, a different page in it, a route escape — and the Blocker ones
(a blank tab, the Ingress prefix inside the **Public** address, a leaked
token) are covered in the static tier, not by this run.

The record's `details.shape` is the masked address of each tab and is the
readable half of the evidence. `details.ingress_token` reads `<redacted>` on
**both** sides: the evidence sanitiser redacts any key whose name matches
`token`, so the flag's value does not survive into the file even though it is
a boolean. The verdict is computed from the in-process value before masking,
so the judgement is unaffected — but read the file's `shape` and `result`,
not `ingress_token`, for which tab carried the prefix. Filed as #187.

## Conservation (parity plan section 12) — `reconciled.jsonl`

`reconciled.jsonl` is #172's reconciled set (#143's `checks.jsonl` with its
two `U-D8` records) with **this run's `U-C23` record substituted** for the one
#143 wrote, so 76 records against 76 planned checks. `conservation.json` is
`report` over it:

    76 observed = 54 PARITY + 7 GAP + 2 APPROVED-DIVERGENCE + 6 STRUCTURAL + 7 NOT-RUN

which is the tally section 10.6 named in advance. No check is missing,
unplanned, duplicated or unclassified; every `GAP` has an issue — now
**#159, #165–#167, #169, #170**, with **#168 gone from that list**, since the
record that cited it is `STRUCTURAL`; and every `STRUCTURAL` names its Public
origin path, `U-C23` included.

`report` still exits 1, and for the same reason #143 and #172 did: the same
seven `NOT-RUN` checks, each blocked outside the add-on. Nothing in this run
changes that. As with #172, this file only shows the report reconciles —
#143's own evidence and counts are left as that run recorded them, and the
parity plan's section 10.6 carries the numbers above.

## What the run left on the host

This run writes, so it left records behind — all named with the run marker
`WOOW-PARITY-20260928T070408Z`, the #143 convention, so the host stays
readable:

- **P-7 fixtures** created by the `fixtures` step: `res.partner` 64,
  `product.template` 56, `sale.order` 23 and 24, `survey.survey` **3**,
  `event.event` 3, `hr.job` 2, `discuss.channel` 12, `mrp.workcenter` 2,
  `project.task` 7, `ir.attachment` 1359. Only the survey is what `U-C23`
  uses; the step creates the whole P-7 set.
- **Two survey answers** on survey 3, `survey_user_input` 27 and 28 — one per
  surface, both `test_entry = true`, both left in state `new`. These are what
  the Test button creates.
- **One write to a record that already existed**: `im_livechat.channel` 1
  gained the admin in `user_ids` (the `fixtures` step does this for `U-C26`;
  it is not marker-named and was not created here).
- No add-on, host or database **setting** was changed, and no earlier run's
  fixtures were touched or removed.

Off the host: the `fixtures` step's id map landed in `./parity-artifacts/` in
the checkout rather than in `E2E_ARTIFACT_DIR`, because that name is bound at
import and `--env-file` is parsed after. Filed as #188; the ids are listed
above, so nothing is lost by the file not being kept here.
