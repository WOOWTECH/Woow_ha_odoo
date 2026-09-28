---
status: accepted
date: 2026-09-16
---

# The Runtime shim is the Ingress URL authority; the Literal rewrite covers only what it cannot intercept

Odoo asset bundles are full of root-relative string literals (`/discuss/…`,
`/html_editor/…`), and under Ingress every one of them is a potential
**Prefix escape**. Two mechanisms add the prefix: the **Runtime shim** that
nginx injects into every Ingress HTML page, which prefixes a URL at the moment
the browser uses it (fetch, XHR, history, `href`/`src`/`action`, workers,
WebSocket), and the **Literal rewrite**, the nginx `sub_filter` rules that
substitute a fixed list of prefixes inside `/web/assets/` bundles. Issue #58
asked whether that list, eight prefixes long and hand-maintained, should grow
to cover every prefix a new app can introduce. A measurement on the test host
on 2026-09-16 found 22 prefixes in the backend bundle outside the list, every
one consumed through an API the shim intercepts, and no unlisted prefix in a
whole-page navigation.

We decided that **the Runtime shim is the single authority** for Ingress URLs,
and the Literal rewrite exists only for the cases the shim cannot reach: whole-
page navigations (`location.href =`, `location.assign()`, Odoo's `redirect()`)
and path comparisons that gate behaviour (`pathname.startsWith("/odoo")`), plus
the handful of exact-expression patches (router, bus worker) already in the
template. A prefix is added to the Literal rewrite when a bundle uses it in one
of those contexts, not merely because a bundle contains it. The gate that
enforces this is a Live-tier check that extracts every root-relative literal
from the bundles the control group serves, classifies each by how it is
consumed, and fails only on unlisted prefixes in navigation contexts.

## Considered options

- **List every prefix.** Rejected: the list would grow with every app, and
  each broad rewrite has already broken the add-on twice. 0.3.10 removed the
  broad JavaScript route substitution because it double-prefixed OWL
  navigation next to the shim, and 0.3.34 had to restrict the shim to
  `text/html` after rewriting JSON produced a blank Document Layout preview.
- **Remove the Literal rewrite entirely.** Rejected for now: `location`
  writes cannot be intercepted from a script, and the router and bus patches
  have no runtime equivalent. Revisit once the gate has run against the full
  application list.
- **Generate the list from installed modules.** Rejected: module names are
  not route prefixes (`website` serves `/shop`, `mass_mailing` serves `/r/`),
  and generating a broad list reintroduces the first option's risk.

## Consequences

- The prefix list in `location ^~ /web/assets/` stays short and hand-written.
  The gate, not the list, is what makes a new app safe to install.
- A gate failure means one of two things: add a Literal rewrite rule for that
  prefix in the three quote variants, or record an approved exception with its
  reason. Exceptions live in a checked-in file reviewed like code.
- Path-comparison hits are reported as warnings, never as failures, because
  rewriting a comparison can be wrong (the router compares the stripped path).

## Postscript (2026-09-17)

The gate's first full-application run found `/shop/`, `/payment/` and
`/contactus` (PR #72). ADR 0005 keeps every rule above (shim authority,
navigation-only rewrites, warnings never fail, exceptions reviewed like
code) and changes only who adds a rule: the add-on's Rewrite scan now
derives Generated rewrites at run time instead of a person editing the
template after a nightly gate failure.

## Postscript (2026-09-28)

The `U-A6` audit of the #143 parity run tried seven ways a root-relative URL
can reach the browser without going through an API the shim wraps, and every
one of them escaped to the Home Assistant root (#169). The rule above --
the shim is the authority for anything it can intercept -- decides them in
two groups, and the shim now has the first group:

- **Covered.** `navigator.sendBeacon`, the `EventSource` constructor, and the
  SVG `<use>` reference, set through `setAttribute("xlink:href", ...)`,
  `setAttribute("href", ...)` or `setAttributeNS(...)`. Each is one wrapper
  in the shim's existing pattern, using the same `path()` helper, so each is
  added now rather than when a screen is found to need it.
- **Uncovered by decision.** HTML inserted as markup (`innerHTML`,
  `insertAdjacentHTML`, `outerHTML`), the `style` attribute, and the text of
  a dynamic `<style>` element (CSS `@import` included). The HTML editor and
  the website editor load and save record content through exactly these
  paths, so a shim hook would write the Ingress prefix -- which carries the
  Ingress token -- into the database: the Public origin would then serve
  URLs under someone's expired Supervisor token, and the token would be in
  the record. That is worse than the escape it would fix, and it is the same
  reason #158 recorded.

A screen that hits an uncovered way is therefore not a shim change. It gets a
route-scoped **Literal rewrite** of its own, filed as its own issue with its
own severity: #158 for the action help, #170 for the website editor's snippet
thumbnails. `<meta http-equiv=refresh>` stays untested -- Odoo 18 redirects
server-side -- and media sources (`new Audio`, `HTMLMediaElement.src`) are
#159.

`U-A6` carries the two groups, so it fails only on a covered way escaping
under Ingress, or on any way escaping on the Public origin. An escape in the
uncovered group is recorded as what it is: the decision, with the screens
filed against it. Adding a hook for one of those ways means reopening this
postscript first; a Static-tier test asserts the shim has none of them.

## Postscript (2026-09-28, media sources)

The media sources the postscript above left open are now covered by the
Runtime shim. `U-C25` and the #144 crawler found the Event Registration Desk
(`ir.actions.client` 609) loading its barcode error sound from the Home
Assistant root and getting 404 (#159): the desk builds it with
`new Audio(url("/barcodes/static/src/audio/error.ogg"))`, an absolute
same-origin URL, and the shim wrapped nothing for media. The `/mail/` sound
on the next line survived only because `/mail/` is a Shipped rewrite.

The rule above decides it: `new Audio(...)` is a call the shim can intercept,
so this is a shim change and not a Rewrite scan change. The shim now wraps the
`Audio` constructor -- keeping `prototype` the way the `Worker` wrapper does,
and leaving `new Audio()` with no argument alone -- and the `src` setter of
`HTMLMediaElement.prototype` (`<audio>` and `<video>`) and of
`HTMLSourceElement.prototype`, all through the existing `path()` and property-
setter helpers. One shim change covers every media prefix at once -- POS
sounds, `/barcodes/`, and any future app -- where a Generated rewrite would
cover one prefix at a time.

The **Rewrite scan is unchanged**. Its `INFO` level means "the shim intercepts
this use", and for a media consumer that is now true, so `/barcodes/` staying
`INFO` is the correct classification rather than the missed `FAIL` #159 first
read it as. No Generated rewrite and no Shipped rewrite is added for
`/barcodes/`.

`<track>`, `<embed>`/`<object>`, `poster`, `srcObject`,
`HTMLSourceElement.srcset` (the responsive `<picture>` candidate list rather
than a media source) and CSS `url(...)` media stay uncovered: nothing has been
reported escaping through them. Each is one more wrapper in the same shape if a
check ever shows one does.

What guards the media wrappers is the Static-tier shim contract, which executes
the rendered shim against a DOM stand-in, plus the Registration Desk's own
crawler record (`ir.actions.client` 609) returning to `PARITY`. `U-A6`'s probe
list is *not* extended: its covered group still holds only the #169 ways, so a
media escape would be caught by the desk's screen rather than by the audit.
Adding a media probe to `U-A6` is a change of its own.

## Postscript (2026-09-28, action help)

The first of the screens the postscript above filed against the uncovered
group has its Literal rewrite. The #144 parity run found the Surveys screen of
an empty survey list (`ir.actions.act_window` 930, both survey menus) asking
the Home Assistant root for the four sample-survey pictures and getting 404 --
eight **Prefix escapes**, eight 4xx and eight console errors per screen, with
the Public origin clean (#158). The pictures are `<img src="/survey/static/…">`
in the action's `help` field: HTML that lives in the database, reaches the
browser inside the `/web/action/load` JSON-RPC response, and is inserted as
markup (`markup(action.help)` → `innerHTML`). The **Rewrite scan** cannot see
it either -- it reads asset bundles, and this literal is in a record.

The rule above decides it the way the postscript said it would. Markup
insertion is in the uncovered group, so this is **not** a shim change: the HTML
editor loads and saves record content through the same property, and a hook
there would write the Ingress prefix -- token and all -- into the database.
Action help is only ever read through the action-load response and never saved
through it, so a **Literal rewrite scoped to that route** reaches the escape
without going anywhere near the editors.

What that means in the template, and what it deliberately is not:

- **Its own `location`, matched against three routes and nothing else.** The
  three are the ones whose answer the web client runs `markup(action.help)`
  over: `/web/action/load`, which a menu click and a direct `/odoo/action-<id>`
  both reach through `_loadAction`; `/web/action/run`, which returns whatever
  a server action returned; and `/web/dataset/call_button/<model>/<method>`,
  which returns whatever a button method returned. (The fourth `markup(` site
  in `action_service.js` restores `lastAction` from session storage and
  crosses no wire.) `/web/action/load_breadcrumbs` answers with display names
  only and is left alone. Rewriting escaped attributes on *all* JSON is the
  option this ADR already rejected once: 0.3.34 had to stop doing it after the
  Document Layout preview came back blank.
- **`/web/dataset/call_kw` is excluded, and that is the line.** It is
  `call_button`'s sibling, and the temptation is to treat them together --
  but it carries record content in *both* directions: it is how the HTML
  editor loads a field and how it saves one. Prefixing its response is
  therefore the database-poisoning this whole decision exists to avoid, one
  step removed. `call_button` answers only with `clean_action(...)` or
  `false`, never with a record the client will write back, which is what makes
  it safe and `call_kw` not. A route is covered when its answer is an action
  dict the client only reads, never when it is content the client may return.
- **Escaped-quote patterns.** Inside JSON the attribute quote is escaped
  (`src=\"/survey/…`), which is why the generic location's raw-quote HTML rules
  never matched a byte of the help; the only escaped-quote rules there cover
  `/web/assets/`, for that same preview. The new rules cover the five
  attributes the raw-quote rules already do: `href`, `src`, `action`,
  `data-src`, `srcset`.
- **No double prefix, by rule order.** `sub_filter` settles two patterns that
  match at the same byte by the order they are written -- the earlier one wins
  even where a later one is longer -- so each attribute gets an identity rule
  (`src=\"$safe_ingress_path/` → itself) written *ahead* of its general rule.
  A URL that already carries the prefix is consumed by the identity rule and
  left as it was. The template's older claim that "no later rule can undo it"
  stays true and is the reason these are written first; its other claim, that
  overlapping patterns are settled "not by the order the rules are written
  in", was wrong and has been corrected where it stood. Two limits survive,
  because the pattern is a string and not a parser: a protocol-relative
  reference is prefixed and breaks, and `srcset` is a list whose candidates
  after the first are not behind the attribute opener. Both are pinned by the
  Static-tier test and belong to #166, which fixes them for every such rule at
  once or not at all.
- **A copy of `location /`, not a subset of it.** The location keeps the proxy
  headers, cookie path and flags, `X-Frame-Options` removal, buffering and
  timeouts of the generic Ingress location, and every rule it carries; it
  differs only by the added rules. A Static-tier test compares the two bodies
  directive by directive, so drift in either fails rather than quietly changing
  the routes. One regex location rather than four exact ones for the same
  reason: `call_button` needs its path form covered anyway, and a body written
  out four times is a body that drifts.
- **The Public origin is untouched,** and so is the Rewrite scan: this is a
  **Shipped rewrite**, because action help comes from the database and not from
  a bundle, so no Generated rewrite could ever derive it.

`U-A6`'s probe list is not extended. Its `accepted` group still records the
`innerHTML` escape as the decision it is; what proves this fix is the Surveys
screen's own crawler record, plus the Static-tier contract. The Live half is in
`docs/testing/evidence/2026-09-28-issue-158/`: two Ingress crawls a minute
apart on the test host's local build of this branch, one with the new
`location` blocks cut out of the rendered config and one with them in, taking
the survey menus from `route_escape`/`http_4xx_5xx`/`console_error` = 8 each to
zero, with the four pictures answered 200. The crawler's two-surface `PARITY`
verdict is still owed: the local add-on has no `public_url`, so that one waits
for a Release. The other screen filed against the uncovered group, the
website editor's snippet thumbnails (#170), is still open and gets a rewrite of
its own in the same shape.
