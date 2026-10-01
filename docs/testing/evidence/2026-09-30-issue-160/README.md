# Live rerun — #160 visitor URL, on 0.4.6 (2026-09-30)

**Result: the fix does not take effect on the real host. `U-C5` on action 596 is still a `GAP`.**

> **The readings below stand; the cause this run named for them was refuted the
> same day.** The patch *was* applied on the host and the *swap* inside it was
> the no-op. See **Correction** at the end of this file, which is what the fix
> was built on.

| | |
|---|---|
| Add-on | `1b7b4ce7_odoo18ce`, **0.4.6** (the first Release carrying #160 / `woow_visitor_url` and the #154 layer split), `state: started` |
| Database | `odoo_parity` (the 29 modules of #144) |
| Surfaces | Public origin (`<PUBLIC_BASE>` = the Cloudflare tunnel) and HA Ingress |
| Owed by | PR #206 ("the Live rerun … can only be checked after the next Release is deployed"; parity plan §10.4) |
| Scripts | `e2e_parity_shared_layers_live.py pcheck`, `e2e_menu_action_adapter.py open` / `crawl` / `diff` |

## P-Checks — the baseline the verdict rests on

All six PASS, twice (before and after a mid-run restart):

```
P-1 PASS public_url is https
P-2 PASS GET /web/login -> 200
P-3 PASS web.base.url = <PUBLIC_BASE>
P-4 PASS web.base.url.freeze = True
P-5 PASS website.domain = ['<PUBLIC_BASE>']     <- the Canonical URL the fix should store
P-6 PASS same login on both surfaces, db ['odoo_parity', 'odoo_parity']
```

So `website.get_base_url()` — what the fix rebuilds the stored URL on — resolves to `<PUBLIC_BASE>`, not the Home Assistant host. The baseline is correct; the fix still does not use it.

## The decisive reading — a fresh page view through Ingress stores the HA host

The fix's contract (PR #206): a page view opened through Ingress records the **Canonical URL**, not the Home Assistant host; rows stored before the fix are not rewritten. So a *new* row created after 0.4.6 is the test.

Opening the website home (`/`) through Ingress with `open --surface ha_ingress` created these `website.track` rows (`website-track-latest.jsonl`, read over JSON-RPC):

```
id 243  url http://192.168.50.192:8123/   2026-09-30 04:20:19  page "Home"
id 227  url http://192.168.50.192:8123/   2026-09-30 04:11:20  page "Home"   (after a restart)
id 226  url http://192.168.50.192:8123/   2026-09-30 04:06:14  page "Home"   (first)
```

`http://192.168.50.192:8123` is the Home Assistant host's LAN address. Every fresh Ingress page view stores it — including rows created after a full add-on restart, so this is not a stale worker running old code.

**Why the fix is not merely mis-configured but not running at all.** *(Refuted — see Correction.)* `woow_visitor_url.tracked_url` rebuilds the URL on `website.get_base_url()`; even if that base were empty it would store a **path only** (`/`), and with P-5 passing it would store `<PUBLIC_BASE>/`. It stores neither — it stores the **full, unmodified** `request.httprequest.url`. That is the module's own "serve untouched" fallback: `from odoo.addons.website.models import website_visitor` raised at server-wide import time, the `except ImportError` branch logged one line and left the class unpatched (`woow_visitor_url/__init__.py`). The sister module `woow_base_url_guard` — which does **not** import `website` — is applied (P-3/P-4/P-5 pass), and that import is the one thing that differs between them.

The in-image Build-tier probe (`tests/in_image/visitor_url_applied.py`, green on PR #206's CI) starts Odoo in an environment where that import succeeds; the running host does not. This is exactly the Build-tier-vs-host gap the Live tier (ADR 0012) exists to catch.

(The Odoo Python startup log is not visible through `ha apps logs`, which surfaces only nginx — the `info`-level "patched"/"not importable" line could not be read either way; the verdict rests on the stored value, which is unambiguous.)

## Action 596 — `crawl` / `diff`, still a `GAP`

`crawl --apps website` on both surfaces, then `diff` (`crawl-website-*.jsonl`, `crawl-diff.txt`):

```
30 judged = 29 PARITY + 1 GAP; 1 skipped
GAP menu:website.menu_visitor_view_menu|ir.actions.act_window:596:
    ... U-C5 ha_origin: <HA_BASE>/ ; <HA_BASE>/shop/...service-58 ;
        <HA_BASE>/jobs/...job-3 ; <HA_BASE>/contactus   (both surfaces)
SKIPPED menu:website.menu_website_analytics|ir.actions.server:587 (server action may write)
```

Action 596 is the `website.track` list; it now shows the HA-host URLs in the rows above (the fresh 0.4.6 ones plus older ingress views). The violation appears on **both** surfaces because the bad host is now database content, read the same from either origin — the same shape #144 recorded, unchanged by #160. Every other website action is `PARITY`.

## Host state left behind

- `website.track` gained rows `226`, `227`, `239`–`243` (website "Home"), all storing the HA host — created by this rerun's Ingress page views. They are left in place as the evidence of the defect; like every earlier bad row they are not rewritten. They will keep action 596 a `GAP` until #160 is actually fixed and the rows are cleared.
- The add-on was restarted once mid-run (inside the ADR 0012 boundary); the maintenance bootstrap rewrote `web.base.url` / `website.domain`, and P-Checks passed after it.
- No `sale.order`, `res.partner`, module or group was changed.

## What this owes

- **#160 is reopened.** The shipped fix is correct in the Static and Build tiers but inert on the host; the remaining work is to make the module's replacement of the tracked URL take where it runs, with a Live-tier check, not only the in-image probe, as its proof. *(What "where it runs" means was read wrong here; the Correction has it.)*
- The parity plan §10.4 note is updated to record this 0.4.6 result.

---

## Correction (2026-09-30, later the same day) — the root cause above is wrong

The readings above stand: every fresh Ingress page view on 0.4.6 stored
`http://192.168.50.192:8123/`, and action 596 was still a `GAP`. **The cause
named for them does not.** The section above blames the module's
`except ImportError → serve untouched` branch. It was not that. The `info` line
that could not be read through `ha apps logs` is in the add-on's own Odoo log,
inside the container at `/data/odoo/logs/odoo-server.log`, and it is there:

```
2026-09-30 04:05:00,181 439 INFO ? odoo.addons.woow_visitor_url:
    website.visitor._handle_webpage_dispatch patched: a page view records the Canonical URL
    (once per worker, again after the 04:09 restart)
2026-09-30 04:06:15,165 536 WARNING odoo_parity odoo.addons.woow_visitor_url:
    the request's url could not be replaced, so this page view records
    http://192.168.50.192:8123/; werkzeug's Request.url is no longer a cached_property
    (once per Ingress page view of this rerun: 04:06:15, 04:11:21, 04:18:16 … 04:20:19)
```

So the patch **was applied**, and the module's own guard fired on every page
view: what was inert is the swap, not the patch. `request.httprequest` is not
the werkzeug request — it is `odoo.http.HTTPRequest`, which wraps one and
installs a plain `property` per forwarded attribute, `url` among them
(`make_request_wrap_methods`, `HTTPREQUEST_ATTRIBUTES`). A plain `property` is
a data descriptor and never reads the instance `__dict__`, so the value the
module wrote into `vars(httprequest)["url"]` was read back by nobody. Read in
the deployed image (0.4.6, werkzeug 2.2.2), no database:

```
werkzeug 2.2.2
HTTPRequest.url descriptor: builtins.property  fget True  fset True  fdel False
werkzeug Request.url descriptor: werkzeug.utils.cached_property  __set__ True  __delete__ True
arrived                         http://192.168.50.192:8123/
after instance-dict write       http://192.168.50.192:8123/      <- the defect
after attribute assignment      https://example.test/            <- what takes
del r.url                       AttributeError: property of 'HTTPRequest' object has no deleter
```

Two consequences for the fix: the url is replaced by **assigning** to it, and
it is put back by assigning the arrived address again rather than by deleting a
cache entry the wrapper has no deleter for.

The fixed module was driven against that image's own `odoo.http.HTTPRequest`,
again with no database — the decision and the patch exec'd in a throwaway
`python3`, `odoo.http.request` pointed at a request built over the Ingress
environ, and upstream's dispatch stood in by a function that records what it
would have stored:

```
type of httprequest:               odoo.http.HTTPRequest
arrived:                           http://192.168.50.192:8123/contactus
what upstream would have stored:   https://shop.example.test/contactus   <- the Canonical URL
after the dispatch:                http://192.168.50.192:8123/contactus  <- put back
wrapper dict keys:                 _HTTPRequest__environ, _HTTPRequest__wrapped,
                                   _session_id__, environ                <- the four __init__ sets
wrapped request's cached url:      http://192.168.50.192:8123/contactus
dispatch raising:                  url after: http://192.168.50.192:8123/contactus
```

No warning was logged; the wrapper's `__dict__` holds exactly what its
`__init__` put there and no `url` of its own, which is the entry the old version
wrote and nothing read; and the address the browser used came back — including
when the dispatch raised.

What this does **not** replace is the Live rerun: nothing above opens a page
through Ingress on the deployed add-on or re-crawls action 596. That still
needs a Release carrying the fix on the test host, and it is still owed. The
rows this rerun left (`226`, `227`, `239`–`243`) are still there and still keep
action 596 a `GAP` until they are cleared.
