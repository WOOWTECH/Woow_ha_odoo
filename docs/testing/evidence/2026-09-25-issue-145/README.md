# Parity run: every outbound artefact from both surfaces (#145)

Run `WOOW-PARITY-20260925T142416Z`, started 2026-09-25 and finished 2026-09-26, against the test
host's Released add-on `1b7b4ce7_odoo18ce` at **0.4.4**, database **`odoo_parity`** (the 29
modules of #144, with the Canonical URL catch-up of #164 in place). Driver:
`odoo18ce/tests/e2e_parity_outbound_live.py`. The pure parts are in `e2e_parity_outbound.py`, with
static tests in `test_e2e_parity_outbound.py`. The mail sink is `smtp_capture_sink.py`.

- **Public side**: a top-level page on the Public origin.
- **Ingress side**: Odoo in its Ingress iframe inside the Home Assistant frontend, over the
  plain-http LAN entrance. These are the same two sides as #143.
- Each artefact was produced through the UI of each surface: a click in a dialog, a menu, a button
  or the chatter composer. The fixtures that need one copy per surface have one per surface, named
  after it.

## The rule

Group E is built on the server, so the verdict does not only compare the two surfaces. A record is
`PARITY` only when all of these hold:

- both results match;
- neither side raised a signal;
- neither artefact holds a URL on Home Assistant, a relative URL or an Ingress token;
- every anonymous link shows its record.

An artefact with nothing to judge (no link, or a PDF with no QR code) cannot pass. It is `NOT-RUN`
and names what blocks it.

The same leak in both copies of a mail would still be a `GAP`. External links (odoo.com, the
Outlook help page in the mailing template) and XML namespaces (w3.org, schema.org) are listed but
are not problems. The rule is in `outbound_record`.

**Reachability** is judged only where the object allows anonymous access (the `U-E3` note, section
6). Each such link was opened twice:

- on the LAN, from a browser context with no session, during the run;
- off the LAN, from a browserless.io cloud Chrome whose egress address is not the office's
  (`off-lan.json`).

Some links are recorded but not opened: links that need a login (the approval mails' `/mail/view`
for internal users), and links that are not pages (the live chat widget's script and loader).

## Checks: `checks.jsonl`

**Conservation**: 25 planned, 25 observed = **22 `PARITY` + 2 `GAP` + 1 `NOT-RUN`**. Nothing is
missing, duplicated or unclassified, and every `GAP` has an issue. The run does **not qualify** as
complete, because one check is `NOT-RUN` (`conservation.json`).
`python odoo18ce/tests/e2e_parity_outbound_live.py report checks.jsonl` recomputes it.

### GAP

| Check | What | Issue |
|---|---|---|
| `U-E4` invoice PDF | Action menu > Download > PDF works on the Public origin. Under Ingress the iframe requests `<HA_BASE>/account/download_invoice_documents/<id>/pdf` (404, `route_escape`) and no file lands. Odoo returns an `ir.actions.act_url` with `target: 'download'`. Why the Runtime shim misses it is still open | **#174** (new) |
| `U-D8` generic | Under Ingress, `sitemap.xml` lists `<HA_BASE>` URLs. The head (canonical, `og:`, `twitter:`) and `robots.txt` are on `<PUBLIC_BASE>` on both surfaces, now that #164 fills `website.domain` | #172 |

### NOT-RUN

| Check | Blocked by |
|---|---|
| `U-E4` invoice PDF without Payment | The company has no QR payment method in Odoo CE (Taiwan), so the invoice has no QR code, and the PDF has no link either. The ECPay e-invoice print (`列印電子發票`) has QR codes but needs an issued e-invoice (#146). The QR decoding itself ran on the event ticket |

`U-E4` invoice PDF (Download > PDF) is a `GAP`, not `NOT-RUN`: the Public origin gave a PDF with
no QR code, but Ingress gave no file at all (#174).

### What each artefact holds

| Item | Screens | Literal on both surfaces | Anonymous, LAN and off-LAN |
|---|---|---|---|
| `U-E2` mail | portal invitation, password reset, chatter notification, mass mailing, time off approval, expense approval | Every link on `<PUBLIC_BASE>`: signup/reset `/web/signup`, `/mail/view`, `/r/<code>`, `/mailing/<id>/confirm_unsubscribe`, the `/mail/track/…/blank.gif` pixel | Signup, reset, the tracked link (lands on Contact us), unsubscribe, the pixel and the notification's access-token link all open |
| `U-E3` share | quotation, invoice, RFQ and task (portal.share); project (project.share.wizard); survey (survey.invite); dashboard (spreadsheet share); Discuss invitation; live chat widget and direct page; calendar meeting URL | Every link on `<PUBLIC_BASE>` | Each opens its record |
| `U-E4` PDF and QR | invoice via Download > PDF, invoice via PDF without Payment, event Full Page Ticket | No link in any PDF. The ticket's one QR code holds the registration barcode, not a URL. The invoices have no QR code | not applicable |
| `U-E5` attachments | a file sent from the chatter becomes a download link | `<PUBLIC_BASE>/web/content/<id>?download=1&access_token=…` | Downloads the file (its content checked) |
| `U-E7` exports | link trackers and calendar meetings, as xlsx and as csv | Tracked URL and Meeting URL columns on `<PUBLIC_BASE>` | not applicable |
| `U-D8` SEO | sitemap, robots, home page head | see GAP | not applicable |

**Every share dialog.** The dialogs came from the share wizards installed on `odoo_parity` and the
actions bound to them: `portal.share` on sale, invoice, purchase and task, `project.share.wizard`,
`survey.invite` and `spreadsheet.dashboard.share`. Three other link fields made to be handed out
were added: the Discuss invitation, the live chat links and the meeting URL. `mail.wizard.invite`
adds followers and shares no link. `event` has no share dialog without `website_event`.

## How mail was captured

- **The sink.** `smtp_capture_sink.py` ran inside the add-on container on `127.0.0.1:2525`. It
  stores each message and never relays one.
- **The server.** An `ir.mail_server` named with the run marker pointed at the sink, with a tiny
  size limit. That limit makes Odoo turn every record attachment into an absolute download link,
  the `U-E5` path in `mail_mail._prepare_outgoing_list`.
- **The recipients.** Every recipient is `e2-<what>-<surface>@example.invalid`, which is how a mail
  is tied to the surface that triggered it.
- **The queue.** Mail queued by the actions was sent at once: the mass mailing cron was triggered,
  then `mail.mail.process_email_queue` ran.
- **Afterwards.** `teardown` archived the mail server and the sink was stopped. The 40 mails that
  sat in `exception` before the run are in `exception` and were not retried.

The sink also caught mail nobody asked for, all to the salesperson or the fixture attendee: six
"quotation viewed" notices when the share links were opened, and the event registration's
confirmation. None reached anyone.

## Results worth knowing

- **Password reset.** The marker users never logged in, so Odoo's button is "Send an Invitation
  Email". It sends the same `/web/signup?…token=` link as a reset. The user form opened by
  `/odoo/res.users/<id>` alone has no header buttons; the Settings > Users action does.
- **Meeting URL.** It is built by the frontend (`set_discuss_videocall_location` is a stub on the
  server) and exists for Odoo only after the event is saved. Before saving, the link is a 404.
- **Mass mailing.** The body's `/unsubscribe_from_list` placeholder stays in the mail as
  `<PUBLIC_BASE>/unsubscribe_from_list`, next to the real `/mailing/<id>/confirm_unsubscribe` link
  that Odoo adds. Both are on the Canonical URL.
- **Password reset: what was not tested.** The marker users never logged in, so Odoo offers only
  "Send an Invitation Email" and not "Send Password Reset Instructions". Both send a
  `/web/signup?…token=` link built the same way, but the reset mail itself was not sent.
- **`U-E5`: what was not tested.** Only the mail path was tested, where Odoo turns attachments into
  links. Odoo 18 CE shows no other absolute attachment URL: chatter download links are relative and
  stay inside the page's own prefix. The `og:image` URLs are covered by `U-D8`.
- **Reachability is text matching.** A link "shows its record" when the page contains the record's
  name, or a word such as "password" (signup and reset) or "contact" (the tracked link lands on
  Contact us). The dashboard, meeting link and pixel have no text to match: they pass on HTTP 200
  without landing on `/web/login`.
- **The off-LAN pass.** Every page was opened by navigation, as a person does. The four attachment
  downloads and tracking pixels are not pages, so they were fetched with no credentials. All 34 links
  showed their record, from two cloud addresses, neither of them the office's. A first pass fetched
  every link; the survey start link then failed, because its redirect needs a cookie that such a
  fetch does not keep. That is why pages are now navigated.
- **Two record sets.** After review (commit `fc5faaf`), `U-E3`, `U-E4` and `U-D8` were run again and
  the captured mail was judged again, so these records follow the final rules. The four `U-E7`
  records come from the first final run; their code path did not change. An earlier attempt at the
  final run lost its shell to a memory shortage while its Python process kept writing, so two runs
  wrote records. All 18 duplicated identities agreed, and none of them is in this file.
- **Not repeated.** `U-C20` (print report) is a group C item, so #143 ran it; the section 10.4 rows
  that point `U-C20` at #145 are covered there.

## Masking

- **URLs** are base codes (`<PUBLIC_BASE>`, `<HA_BASE>`, `<INGRESS_PREFIX>`).
- **Paths** are shapes (`url_shape`): ids become `<id>`; access tokens, short-link codes and
  invitation tokens become `<token>`; query strings are dropped.
- **Nothing else identifying.** The login, password, HA token, the hosts and both egress addresses
  are absent. A scan of these files for them, for IP addresses, UUIDs and long tokens found none.
  The unmasked links (`<run>-reach.json`) and the captured messages stayed outside the repository.
