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

`<track>`, `<embed>`/`<object>`, `poster`, `srcObject` and CSS `url(...)`
media stay uncovered: nothing has been reported escaping through them. Each is
one more wrapper in the same shape if a check ever shows one does.
