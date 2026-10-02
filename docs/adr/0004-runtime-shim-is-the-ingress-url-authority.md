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

- **Its own exact-match `location` for `/web/action/load`, and no other
  route** -- even though three deliver the help. The web client runs
  `markup(action.help)` over the answer of `/web/action/load`, of
  `/web/action/run` and of `/web/dataset/call_button/<model>/<method>` alike.
  (The fourth `markup(` site in `action_service.js` restores `lastAction` from
  session storage and crosses no wire.) Rewriting escaped attributes on *all*
  JSON is the option this ADR already rejected once: 0.3.34 had to stop doing
  it after the Document Layout preview came back blank.
- **What separates the three is not the help; it is the rest of the action
  dict.** `/web/action/load` answers with a **stored**
  `ir.actions.act_window` record: its `help` is database HTML the client only
  displays, and its `context` is the static string a developer wrote into the
  action definition. Nothing in that response is content the client hands
  back. The other two answer with an action **computed at call time**, and a
  computed action carries record content in its `context` as wizard defaults.
  `marketing_card`'s `action_share()` is the shipped proof: the button returns
  an `act_window` whose `context.default_body_arch` is a mail body holding
  `<img src="/web/image/card.campaign/<id>/image_preview">` and
  `<a href="/cards/<id>/preview">`. Prefix those and the mailing opens
  pre-filled with the Ingress prefix; the first save writes the Supervisor
  token into `mailing.mailing.body_arch`. That is this decision's own harm,
  reached by one more step, and a server action's returned dict -- user-
  authored Python -- is at least as open. So the rule this ADR gains is:
  **rewrite a response only when everything in it is something the client
  displays and never returns.** `/web/dataset/call_kw` fails it most plainly
  of all, being how the HTML editor both loads a field and saves it.
- **What that leaves open, said plainly.** Help delivered through
  `/web/action/run` or a button keeps escaping. It is the smaller harm -- a
  404 picture against a token in the database -- and closing it needs a fix
  that can tell one JSON field from another, which a byte-level `sub_filter`
  cannot. `/web/action/load_breadcrumbs` answers with display names only and
  needs nothing.
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
  the route.
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
website editor's snippet thumbnails (#170), gets a rewrite of its own in the
postscript below -- not in this shape, because that URL is written back.

## Postscript (2026-09-28, snippet thumbnails)

The second screen filed against the uncovered group has its Literal rewrite,
and it moves the rule one step further: **a Group B URL that round-trips to the
database is rewritten where it is rendered, not where it is delivered.**

The #143 parity run found the website editor's Blocks panel asking the Home
Assistant root for all 36 snippet thumbnails and getting 404 -- 36 **Prefix
escapes** and 36 console errors per editor open, blank tiles, the Public origin
clean (`U-D2`, #170). Editing itself worked and there was no
`AssetsLoadingError`. The editor loads the snippet catalogue with a JSON-RPC
call to `render_public_asset` on `ir.ui.view`; each tile's picture arrives in
that HTML string as `data-oe-thumbnail=\"/website/static/…\"`, and the OWL
template puts the value into a `style` attribute as `background-image:
url(...)` -- the `style` way of the uncovered group, which no rule reached: the
JSON rules on the Ingress `location /` match `src="/`, not the escaped
`data-oe-thumbnail=\"`, and the asset location's `url(/` rules do not match
`url({{`.

**Why not the response, which is where #158 put its rule.** Because this value
comes back. The editor's "Save block" reads the snippet's `thumbnailSrc` -- the
raw `data-oe-thumbnail` of that same catalogue response -- and passes it to
`ir.ui.view.save_snippet` as `thumbnail_url`, which writes it into the new
snippet view's arch as `t-thumbnail`. A rewrite on the response would therefore
store the Ingress prefix, Supervisor token and all, in the database the first
time somebody saved a custom block under Ingress: broken on the Public origin,
token in a record. That is this decision's own harm, reached the way
`marketing_card`'s wizard defaults reach it in the postscript above. Action
help is safe to rewrite on delivery precisely because nothing writes it back,
and that is the distinction, not the transport:

> Rewrite a URL where it is *delivered* only when nothing writes it back.
> Otherwise rewrite it where it is *rendered*, and leave the delivered value
> alone.

**What this rule puts in question, said rather than left implicit.** The
Ingress generic HTML `location /` rewrites page HTML on delivery -- the five
URL attributes, `data-success-page`, and since #194 the seven `url(` shapes of
an inline `style` background. The website editor loads a page through exactly
that location and saves the edited HTML back through `ir.ui.view.save`, so by
the rule above those rules are on the wrong side of the round trip: a snippet
background that arrived prefixed can be saved prefixed. Nothing here changes
them -- that is #194's and #166's ground, and it needs its own measurement of
what the editor actually writes back, which this issue did not take. It is
recorded so the next person reads a stated tension rather than an oversight.

**The render site is the OWL template**, and Odoo 18 serves it. Templates are
inlined into the `.min.js` bundle as `registerTemplate(...)` template literals,
appended unminified after the JavaScript, so the tile's own markup goes through
the Ingress asset location where the ADR 0006 exact-expression rewrites live.
One rule there replaces `url({{snippet.thumbnailSrc}})` with an interpolation
that puts `$safe_ingress_path` in front of a value beginning `/` and returns
anything else unchanged -- a snippet with no `t-thumbnail` arrives as the
literal `oe-thumbnail` and stays that way.

What that rewrite has to survive is unusual enough to write down: the
expression lives inside an XML attribute delimited by double quotes, inside a
JavaScript template literal. It therefore carries no double quote, no backtick,
no backslash and no `${`, and quotes with `'` -- which is why this rule is
written with a double-quoted parameter, as the generic `url('/` rules above it
already are, and as issue #211's popover guard later had to be on the pattern
side. `thumbnailSrc` keeps its raw value, so `save_snippet` stores exactly
what it stores today and a custom block saved on either surface shows its
thumbnail on both.

No double prefix: `sub_filter` never reads back what it wrote, the `url(/`
rules match a different byte, and the shim's `path()` never sees a `style`
attribute. The protocol-relative limit shared with every other prefix rule is
inherited and belongs to #166. The catalogue response, `save_snippet` and the
Public origin listener are untouched, and a Static-tier test asserts no
directive in the template names `oe-thumbnail`, `render_public_asset` or
`save_snippet`, so changing that means reopening this postscript.

One escape on this screen is *not* closed, and `U-D2`'s row says so: the same
template draws an undroppable snippet with a static
`<img src="/web_editor/static/src/img/snippet_disabled.svg">`, and the template
carries no `/web_editor/` rule (`"/web/` does not match `"/web_editor/`). The
36 escapes measured in #143 did not include it -- that screen had no disabled
snippet -- so it is unmeasured rather than fixed, and it belongs to its own
issue if a Live rerun turns it up, like the root-relative `src` inside a
snippet body this issue also left alone.

`U-A6`'s probe list is not extended: its `style`-attribute probe still records
the escape as the decision it is. What proves this fix is the Static-tier
contract -- the pattern measured against a captured `web_editor.assets_wysiwyg`
excerpt, the rewritten expression executed in node, and the rewritten
`registerTemplate` payload parsed as XML, because an OWL template is not
something node can render -- plus the Live `U-D2` rerun, which is the
maintainer's after Deploy: the Blocks panel at 200 under Ingress, and a custom
block saved under Ingress whose view arch shows a `t-thumbnail` with no prefix
in it.

## Postscript (2026-09-28, location writes)

This decision has always had a hole in it that nothing had yet fallen through:
**the shim cannot intercept a write to `location`.** `location` is an accessor
on `window` that browsers refuse to redefine, so there is no wrapper to hang on
it — the one navigation API the shim cannot own. The Literal rewrite was the
answer for the other cases, but it only reaches URLs that are *in* the bundle,
and a URL that arrives over RPC is not.

The #145 parity run put a Blocker through that hole (`U-E4`, #174). **Action
menu > Download > PDF** on a posted invoice is not an `ir.actions.server`: the
account controllers load it through `account.move.get_extra_print_items`, which
returns a plain dict with `type: ir.actions.act_url`, `target: download` and
`url: /account/download_invoice_documents/<ids>/pdf`.
`ActionMenus.onItemSelected` sees an item with a `url` and no `action` and runs
`browser.location=item.url`. Under Ingress the frame left for
`<HA_BASE>/account/download_invoice_documents/7/pdf`, Home Assistant answered
404, the file never landed and the invoice form was gone with it — a **Prefix
escape**, and one that costs the screen as well as the file. `window.open` was
never called; the issue's first guess (`_executeActURLAction` then
`browser.open`) was the wrong path, and the instrumented rerun said so.

**The rule this adds**, and it is the narrow one:

> A navigation the Runtime shim cannot intercept, whose URL arrives at run time
> and so is nowhere in the bundle, gets an exact-expression Literal rewrite of
> the *expression that navigates* — and that rewrite prefixes by calling the
> shim's own helper, never by copying it.

So the shim now **publishes `path()`** as `window.__WOOW_INGRESS_URL__`: the
same function the `fetch`, XHR, `window.open`, `Worker`, attribute and media
wrappers already call, read-only and non-configurable the way
`__WOOW_CANONICAL_URL__` is, defined only when the Ingress prefix is non-empty
because the prefix script returns before it otherwise. There is no second URL
helper and no second set of rules about `blob:`, `data:`, `#`, cross-origin,
non-string values or a double prefix: a rewritten expression inherits all of
them by construction, and a Static-tier test executes the published global
against every one. The shim stays the single Ingress URL authority; what
changes is that it now says so out loud to code it cannot wrap.

**Two expressions are rewritten, covering three sites.**
`browser.location=item.url` is the print-menu item above.
`browser.location.assign(url)` is the `target==="self"` branch of
`_executeActURLAction` — the generic `ir.actions.act_url` with the same class of
server-supplied URL — and it is also, byte for byte, the last statement of the
`home` client action, which builds `"/"+(browser.location.search||"")`. A
`sub_filter` pattern is a plain string, so one rule rewrites both. **That is
wanted, not tolerated:** `home` navigates the Ingress frame to the Home
Assistant root today for exactly the reason the print item does, and prefixing
it is the fix for it. The test asserts the count in each captured bundle so the
third site can never become a fourth without somebody noticing.

Each rewritten expression falls back to the raw value when the global is
absent — `(window.__WOOW_INGRESS_URL__||function(u){return u})(…)` — so an
Ingress page whose shim did not run still navigates instead of throwing, and
the Public origin, which gets neither the shim nor the rules, is unchanged.

The other `location` writes in the bundle stay where they are, and the reason
is the same one that admits these two. The router's `redirect()`
(`browser.location.assign(_url.href)`, `browser.location.assign(href)`) is
called with literals the shipped prefix rules already cover, and the
session-expiry `window.location.assign(response.url)` is handed an absolute URL
by the server. Neither matches either pattern; both wait for a measurement that
shows an escape.

What proves it is the Static-tier contract — the published global executed
against every rule `path()` has, both patterns counted in bundle excerpts
captured from the control group, and each rewritten expression run in node
with the global present and absent — plus the Live `U-E4` rerun, which is the
maintainer's after Deploy: `Download > PDF` on a posted invoice lands the file
under Ingress with `route_escape=0`. The `target: self` half has no item in the
parity plan, so the rerun checks it by opening
`<ingress>/odoo/action-website.action_website` — `website.action_website` is a
shipped `ir.actions.act_url` with `url: /` and `target: self` — which today
sends the frame to the Home Assistant root and afterwards to the Ingress root.

## Postscript (2026-09-30, the HTML editor's content)

The third screen filed against the uncovered group is the one the decision was
*written about*, and it is the first that cannot be answered by a rewrite in one
direction alone. The rule the snippet-thumbnail postscript states gains its
second half:

> Rewrite a URL where it is *delivered* only when nothing writes it back.
> Otherwise rewrite it where it is *rendered*, and leave the delivered value
> alone -- and where the thing that renders it is also the thing that saves it,
> take the prefix off again on every value it stores.

The #163 `open` run found the To-do form (`project.task` 5, the onboarding
to-do Odoo creates for every user) asking the Home Assistant root for two
pictures and getting 404: `route_escape=2`, `http_4xx_5xx=2`,
`console_error=2`, with the Public origin clean (#210, blocker by parity plan
section 1.3). `project_todo`'s `todo_user_onboarding` template is copied into
`project.task.description` by `_ensure_onboarding_todo()`, and it carries
`<img class="img-fluid d-none d-sm-block" src="/project_todo/static/img/todo_access.png"/>`
and one more like it. So the URLs are **record content in the database**, not a
bundle asset, and the html field inserts them as markup.

**Why neither shape above reaches it.** The Runtime shim wraps APIs, not markup
insertion, so it never sees the URL -- the same as #158. #158's Literal rewrite
is an exact-match `location = /web/action/load`, a stored action's `help`; a
to-do description arrives on `/web/dataset/call_kw/project.task/web_read`, and
`call_kw` is the response this decision named as the one it refuses, *because*
it is how the HTML editor both loads a field and saves it. #170's rewrite goes
to the render site, but there the render site was an OWL template with a
one-way value in it; here the render site hands the value straight back.

**Two helpers, published and not hooked, and both of them string functions.**
`__WOOW_INGRESS_MARKUP_IN__(html)` prefixes URL attributes in a markup string
through the shim's own `path()`, the way #174's `__WOOW_INGRESS_URL__` does, so
there is still one URL helper and one set of rules about `blob:`, `data:`, `#`,
cross-origin, a protocol-relative reference and a value already prefixed.
`__WOOW_INGRESS_MARKUP_OUT__(value)` removes **every** occurrence of the prefix
from a string. Both are read-only, non-configurable and defined only when the
Ingress prefix is non-empty; every rewritten expression falls back to the
untouched value when they are absent, so an Ingress page whose shim did not run
still renders and still saves.

**That they are string functions is a decision and not a convenience.** The
obvious place to strip is the DOM the editor hands over -- `getElContent`
returns a `cloneNode(true)` of the editable -- and it is the wrong place twice
over. That clone is detached from the tree but still owned by the live
document, and a detached `<img>` *loads*: writing the root-relative `src` onto
it re-requests the picture from the Home Assistant root, so the escape would
have been moved to every save rather than fixed. And `HtmlMailField` re-inserts
that very clone into the live document (`editor.editable.after(el)`) to
measure inlined styles, which would have done it again. A string never loads
anything.

**Five sites, and each one is where it is for a reason.**

- **In: `Editor.attachTo`**, the `editable.innerHTML = fixInvalidHTML(...)`
  where the value becomes DOM. The prefix has to be on the *string*, because
  the browser begins fetching an `<img>` the moment the markup is parsed.
- **In again: the collaboration plugin's stale-document reset.** The To-do
  field carries `'collaborative': true`, and
  `resetFromServerAndResyncWithPeers()` reads the field over ORM and assigns
  it straight to `editable.innerHTML`. That is a second render site, reached
  whenever the open document is behind the server's, and the two pictures
  would escape there exactly as they did before this fix. It is the same
  one-line assignment, so it takes the same helper.
- **Out: `HtmlField.updateValue`**, the one place the field writes the record.
  Every save path reaches it -- the editor's content, the urgent
  `getContent()`, and the code view's textarea -- and `lastValue` is computed
  from the same argument. It is also *later* than the editor, which matters:
  the field's `getEditorContent` calls `savePendingImages` **after**
  `getElContent` has returned, and `saveB64Image`/`saveModifiedImage` set
  `src` through the shim's own wrapped setter. A strip inside the editor would
  have let a pasted image write `.../web/image/...` with the prefix, and the
  token with it, into the record. This one does not.
- **Out again: `_commitChanges`'s `comparisonValue`**, which is the other half
  of that. It is read off the clone, so it keeps the prefix, while `lastValue`
  no longer has one -- and the urgent path only writes again when those two
  differ. Leave it and the comparison never matches, so an urgent save writes
  twice under Ingress: redundant rather than wrong, but it makes a
  perfectly good comparison Odoo wrote into a no-op. Both sides go through
  the strip instead. Nothing else reads `comparisonValue`.
- **And the comparison a prefixed `src` breaks.**
  `/html_editor/get_image_info` is the route the image tools ask for the
  attachment behind an `<img>`, and the controller only looks a record up when
  the `src` it is given starts `/web/image`; anything else falls through to a
  URL search, and `image_crop` then reports "This image is an external image"
  and closes. The client builds that argument as `srcUrl.pathname`, which under
  Ingress carries the prefix -- for an image the media dialog inserted it
  already did before this change, because the shim's `setAttribute` wrapper
  prefixes `src`. Handing it through the same strip restores the path the route
  expects, and the one pattern covers both `loadImageInfo` variants Odoo 18
  ships (`html_editor`'s and the legacy `web_editor`'s), so the frontend editor
  gets it too. It is a no-op on a value with no prefix.

**Why `IN` looks only inside a start tag, and then walks it.** Record HTML
holds prose and escaped code samples, and a single attribute regex over the
whole string would prefix `src="/x.png"` wherever it appeared -- which `OUT`
would have to undo, and which would be visible in the editor meanwhile. So one
pattern selects a start tag (`<`, a letter, then no `<` or `>`).

Inside that tag the second pattern does not *search* for an attribute, it
**walks** the tag, consuming each `name="value"` whole and prefixing only the
names it wants. The difference is not cosmetic. A searching pattern opens its
value at the first quote after `src=`, so a tag whose *earlier* attribute value
contains the other quote character followed by the literal text ` src="` --
`<img alt='a" src="/x' src="/y">` -- misaligns and restructures the tag,
leaving the `<img>` with no `src` at all. `OUT` removes a prefix; it cannot put
a tag back together, so that value is what the record would have kept, broken
on both surfaces. Walking makes the `alt` value one token, so the `src` inside
it is never seen and the real `src` is the one prefixed. The shape is in the
Static-tier test, named for what it is.

Which is why the walk **consumes more than it prefixes**, and that is the rule
rather than a list of cases: any attribute it cannot tokenise is one whose
value it searches inside, and that is the same defect again. So the name it
consumes is the HTML attribute-name shape -- anything but whitespace, `=`,
`/`, `<`, `>` or a quote -- and not the four names anything is prefixed for;
the whitespace around the `=` is consumed and put back unchanged; an unquoted
value is consumed as a token too, even though nothing unquoted is ever
prefixed, because there is no delimiter to put back; and an attribute may
begin at a **quote** as well as at whitespace, because `<a href="/x"title="y">`
is legal and minified HTML writes it. That last one is why a quoted value ends
on a *lookahead*: the closing quote stays in the string instead of being
consumed, so it is there to be the next attribute's opener.

Five review rounds each found the same defect through a different spelling -- a
`:` in the name, a `.` or `_`, `alt = '...'`, `alt= href='...'`, and no
separator at all -- which is why the principle is written here and not only
the shapes it has been reached by. Each of them produced a tag with the
attribute *after* the misread one destroyed, and the strip cannot undo that.

Two shapes stay outside the pair, and both fail safely -- the URL keeps
escaping rather than being corrupted. A start tag holding a `>` inside an
attribute value is not recognised as a tag at all. And an unquoted value that
is itself a URL is not prefixed, whatever surrounds its `=`.

What *is* reached and is not really an attribute is markup nested inside
another attribute's value, a start tag written inside a comment, and a
`src="..."` inside somebody's unquoted value (`alt=a"src="/x"`, where a
browser reads one `alt` and no `src`): all three are prefixed -- visible in
the editor until the next load, never in the record, because `OUT` removes the
prefix from the whole string. The third is the price of accepting a quote as
an attribute opener, and it is the cheap side of that trade: the alternative
was destroying the attribute after a misread one.

**Why `OUT` is wider than `IN` rather than its mirror.** It is not only that
`IN` reaches the two not-really-attribute shapes above. The shim's own wrappers prefix attributes
`IN` never touches -- `xlink:href` through `setAttribute`, `srcset` through the
property setter -- and `savePendingImages` prefixes an image after the editor
is done. Removing every occurrence is the only rule that covers all of them,
and it is the right rule for a value on its way to storage: the prefix carries
the Supervisor token, so an occurrence of it in a record is the harm and not
content worth keeping. The cost is stated rather than hidden: prefix-shaped
text a user typed or pasted into a description is removed on save. That is
de-tokenising a credential, and the Static-tier test asserts it as a decision.

**Four attributes prefixed, and only a value beginning `/` and not `//`.**
`src`, `href`, `action` and `data-src` -- the ones whose whole value is one
URL. `srcset` is a candidate list that needs a parse rather than a substitution
and belongs to #166 with every other attribute rule; a `style` background
inside record HTML stays as it is (#194 covers page HTML). Both are *stripped*
on the way out anyway, because the shim's own wrappers can have put a prefix
there. The value runs to the *matching* quote -- the class excludes whichever
quote opened it, not both -- so a `'` inside a double-quoted `src` is part of
the URL, which an attachment called `Mary's photo.png` needs it to be.

The name test is case-insensitive, because `<IMG SRC="...">` is legal HTML and
the tag pattern already accepts it, and it is an *exact* name, so
`data-original-src` is not a `data-src`. It is a comma-delimited `indexOf`
rather than an anchored regex for a reason worth writing down: an anchored
regex needs a `$`, nginx reads a `$` in a quoted parameter as a variable, and
`$/i` is not a valid one -- `nginx -t` refuses the whole config. The
Static-tier test renders the template through a real nginx, which is how that
was caught rather than shipped.

The leading `/` leaves a relative value alone, because prefixing it would
*resolve* it and the resolved path is not what the record held; an absolute
same-origin URL is left alone for the same reason. Excluding `//` is a separate
rule and it is load-bearing, which the first draft of this postscript got
wrong by folding it into the first: `path()` returns a *cross-origin*
protocol-relative reference as it came, but a *same-host* one comes back as a
prefixed root-relative path, and the strip would then have stored `/x` -- a
link silently moved from one host to another rather than an unfixed one. So
`//` is excluded here, which is the limit every other prefix rule in this
template has and #166 owns.

**What the round trip does not promise.** `path()` normalises through `new
URL`, so a value already in normal form -- which is what Odoo writes into
record HTML -- comes back byte for byte, and one that is not comes back as the
same address in different bytes: `/web/image/1/my photo.png` returns
percent-encoded, `/a/../b.png` returns collapsed. The record is rewritten that
far on the first Ingress edit. Using `path()` rather than a hand-rolled
concatenation is this ADR's own rule -- one URL helper -- and each shape is
pinned by the Static-tier test so the next reader meets a measurement and not a
surprise.

**This is not a Group B hook, and the distinction is the whole decision.** A
hook on `innerHTML` prefixes every markup insertion in the page, including the
ones whose value is written back, and the token reaches the database. A
published helper is called by one rewritten expression at one measured site,
and the value it produces is stripped again before anything stores it. The
Static-tier test that asserts the shim has none of Group B's hooks keeps
passing and keeps meaning what it said; a second test asserts the helpers
themselves touch no DOM at all.

**What is not closed, said rather than left implicit.** The code view's
`editable.innerHTML = this.value` on toggling back (the `codeview` option,
which the To-do field does not set) -- closed by the last postscript below
(#240), which also found that the option is set by five shipped views and that
the bound is debug mode alone, and that the obvious rule written with `IN`
rather than #237's `IN_VALUE` would have been a silent no-op here; a snapshot a
collaborative *peer* sends
over WebRTC, which is worth naming precisely because it is the one open item
that is a **token write** and not only a render escape, and because this change
*widens* it -- the snapshot serialises that peer's editable, so it carries
*that* peer's Ingress prefix on every URL the prefixing reached, where before
this change it carried one only on what the media dialog had just inserted;
the strip removes only the prefix of the session doing the saving, so a second
editor could store a foreign Supervisor token in `project.task.description`. The *server* reset is covered; this one is not,
and it is not closed here for two reasons: nothing has measured the
collaboration transport on the test host (it needs two simultaneous Ingress
sessions on one to-do), and a strip that removes a *foreign* prefix has to
reason about what an Ingress prefix looks like, which today only nginx's
`safe_ingress_path` map does. It belongs to its own issue with its own
measurement -- and is closed by the third postscript below (#234), which found
that the token in that prefix is the **add-on's** rather than the session's, so
the two simultaneous Ingress sessions this paragraph asks for share one prefix
and the pair that can carry a foreign one is an Ingress session beside a
Public-origin one. Also open: the media dialog's two preselection comparisons --
`ImageSelector.isInitialMedia`, which compares a prefixed `src` with
`attachment.image_src`, and `DocumentSelector.fetchAttachments`, which compares
a prefixed `href` with `/web/content/<id>` -- so reopening the dialog on an
existing image or document link does not highlight the attachment it came
from. The first was already true before this change for anything the dialog
itself inserted under Ingress, because the shim's `setAttribute` wrapper
prefixes `src` and `href`; both are display state, and closing them means
teaching those comparisons about the prefix the way the `get_image_info`
argument was taught. Those two are closed by the fourth postscript below
(#239), where the measurement found that only the **image** one was ever
broken -- both of its branches, for two different reasons -- while the document
one's left operand is a `` `/web/ `` template literal this location already
prefixes, so it has been comparing prefix against prefix all along, and
teaching it about the prefix -- what this paragraph said to do -- would have
broken it. The readonly `HtmlViewer` was on this list -- none of the
five sites and reaching markup twice over -- and is closed by the postscript
below (#237). The legacy `web_editor` editor behind `html_legacy` and
`mass_mailing_html` was on it too, "which carries none of these expressions",
and is closed by the second postscript below (#238) -- which also found a third
widget on that editor the list never named. None has been measured escaping --
the peer snapshot included, which was unmeasured rather than clean and whose
Live row #243 now carries -- and each is its own issue.

All five patterns were measured on 2026-09-30 across every bundle the control
group serves; `odoo18ce/tests/fixtures/bundles/README.md` carries the counts.
Four of them occur once each in `web.assets_backend`, `web.assets_web` and
`web.assets_web_print` and nowhere else, so this reaches the backend web client
and leaves the website editor's own round trip exactly where the
snippet-thumbnail postscript left it, as a stated tension belonging to #194 and
#166. The fifth, the image-tools one, is also in the frontend bundles, and that
is wanted: the same comparison breaks the same way there. The Public origin is
untouched, and so is the Rewrite scan: record content is not in a bundle, so no
Generated rewrite could ever derive it.

`U-A6`'s probe list is *not* extended; its `innerHTML` probe still records the
escape as the decision it is. What proves this fix is the Static-tier contract
(`odoo18ce/tests/test_ingress_todo_description.py`: the two globals executed
against the rendered shim, all five patterns counted in captured bundle
excerpts, and each rewritten expression run in node with the globals present
and absent) plus the Live rerun, which is the maintainer's after Deploy: the
To-do form at `route_escape=0`/`http_4xx_5xx=0`/`console_error=0` on both
surfaces, and the stored `project.task.description` still root-relative after
saving the to-do in the editor under Ingress.

## Postscript (2026-10-01, the readonly html field)

The postscript above left the readonly `HtmlViewer` on its open list, as the
one item that "reaches markup twice over". This closes it (#237), and the
interesting part is not that there are two rewrites but what the second one is:
the first rewrite of an **OWL template** that has to survive OWL's own
expression compiler, and the first value in this family that is not a string.

`HtmlViewer` chooses its render path at `get showIframe()`
(`hasFullHtml || cssAssetId`, `html_editor/static/src/fields/html_viewer.js:111`
on the pinned deb) and reaches markup once down each:

| | Expression | Served in |
| --- | --- | --- |
| 1 | `<div t-ref="readonlyContent" class="o_readonly" t-out="state.value"/>` | `html_viewer.xml`, appended to the bundle by the xml bundle |
| 2 | `iframeTarget.innerHTML=content;` | `html_viewer.js` |

Both now call `__WOOW_INGRESS_MARKUP_IN_VALUE__`, a third helper published in
the same map as #210's two. Each occurs once in `web.assets_backend`,
`web.assets_web`, `web.assets_web_print` and `project.webclient`;
`odoo18ce/tests/fixtures/bundles/README.md` carries the counts and how they
were derived.

**Why the readonly path is the more common one, and why it is only a render
escape.** A field is readonly on every form the user cannot edit, on every
record shown to a portal -- `project.webclient` is the project-sharing client,
which carries these same bytes -- and in the html field's history dialog, which
mounts the same component. So the pictures and linked documents of stored
markup were fetched from the Home Assistant root and 404'd on the far more
common of the two paths, which is why #237 carries `severity: important` where
its siblings do not. But a viewer has no save, so there is **no `OUT` half**:
nothing here can put a Supervisor token in a record.

What carries that claim is *where* the prefix goes on, and it is worth stating
precisely because the obvious reassurance is false. The prefix goes on the value
**as it is inserted**: the helper returns a new value and mutates nothing, so
`state.value` -- and the revision the history dialog memoised -- still hold the
record's own bytes. The one write anywhere near this component is that dialog's
"Restore history", and it does **not** go through `HtmlField.updateValue`, so
#210's `OUT` is *not* standing behind it: the only implementation of
`restoreRequested` (`project/static/src/views/project_task_form/project_task_form_controller.js`)
hands `record.update()` the memoised ORM revision directly. It is clean because
nothing the viewer rendered is in that path, not because a strip would catch it
-- and the Static-tier test asserts the untouched original for that reason,
rather than trusting a strip that is not there.

**Why a third helper and not `IN`.** `IN` tests `typeof h === "string"` and
returns anything else as it came. The value a readonly html field renders is an
OWL `Markup` *object*: the relational model wraps every `html` field value as
`markup(value || "")` (`web/static/src/model/relational_model/utils.js`), and
`HtmlViewer.formatValue` keeps the wrapper. So calling `IN` at either site
would have been a silent no-op -- the shape of bug this ADR's "an unmatched
rewrite is a no-op" rule is about, reached from the other direction.
`__WOOW_INGRESS_MARKUP_IN_VALUE__` prefixes through `IN` and puts the wrapper
back through the **value's own constructor**, because OWL's `safeOutput`
inserts a value as HTML only when it `instanceof Markup` and *escapes*
everything else: returning a prefixed plain string would have displayed the
record's markup as text, which is worse than the 404 it fixes. A primitive
string goes through `IN` unchanged, so the one helper serves both sites --
`innerHTML` takes a string as markup too -- and anything else (an empty html
field is `false`) comes back as it came rather than as the word `"false"`.
`instanceof String` is realm-scoped, which is sound here and only here: a
page's OWL and that page's shim are one realm, and the Static-tier test builds
its `Markup` inside the shim's own context rather than reaching across.

**What the template rewrite had to learn.** Odoo 18 appends OWL templates to
the bundle after the JavaScript as `registerTemplate(name, path, template)`
with the last argument a template literal, which is what makes a template
reachable by an exact-expression rewrite at all -- the snippet-thumbnail
postscript found that. Three things beyond it:

- **The pattern is not the file.** The served bytes are lxml's
  re-serialisation of the template (`XMLAsset._fetch_content`, then
  `generate_xml_bundle`'s `etree.tostring`), so the file's two spaces after
  `t-ref` and its space before `/>` are gone. A pattern copied from the source
  file would have matched nothing, silently. The fixture is derived through
  Odoo's own serve path for that reason.
- **The anchor is the whole div**, because `t-out="state.value"` on its own
  also occurs in `web.MonetaryField`'s ghost value, in the same bundle.
- **The fallback must be an arrow function.** OWL compiles a template
  expression by rewriting every symbol it does not know into a `ctx[...]`
  lookup, and a `function`'s parameter is not exempt: the
  `(window.X||function(h){return h})(v)` idiom the five #210 rules use compiles
  to `function(ctx['h']){return ctx['h']}` and takes the whole template out at
  compile time. An arrow's parameter is tracked as a local and survives, and
  `window` is one of OWL's reserved words. Verified against the `owl.js` the
  pinned deb ships.

The `hasFullHtml` iframe is rendered with
`sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"`, and
the rewrite is indifferent to it: the helper runs in the parent realm on a
string, so what changes is the value assigned and not who assigns it. The
iframe is `about:blank` and inherits the page's base URL, which is why a
root-relative `src` resolved against the Home Assistant root in there in the
first place.

Group B stays uncovered and the Public origin stays untouched. What proves this
fix is the Static-tier contract
(`odoo18ce/tests/test_ingress_readonly_html_viewer.py`: the helper executed
against the rendered shim, including the no-op plain `IN` would have been;
both patterns counted in the derived excerpts; and both insertions run in node
with the globals present and absent, the iframe one with `hasFullHtml` set and
with only `cssAssetId` set).

**The Live rerun is done: 2026-10-02, Release 0.4.10, #243, all four checks on
both surfaces at `route_escape=0`/`http_4xx_5xx=0`/`console_error=0`, and the
record read back with no prefix** -- so the "no `OUT` half" decision holds where
it can be observed. Two of the screens this record and #243 named were wrong, and
both corrections are measurements rather than readings of the source. Check 1 is
not on the To-do form: only `ProjectTaskFormController` adds the *Version History*
cog item, and `project_todo`'s controller whitelists its own items and filters it
out, so the screen is the project task form. Check 2 cannot be taken on
`project.task.description` at all: that field is `sanitize_tags=True`, so the ORM
strips `<html>`, `<head>` and `<style>` and the full-HTML seed came back as the
bare `<img>` -- `computeContainsComplexHTML()` then never fires and the field
renders the *plain* path, which is check 1's screen measured twice. It was taken
on `mail.template.body_html`, which is `sanitize_tags=False` and renders through
`html_mail`, a subclass of the same field; the rendered attribute there is exactly
`sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"`, which
is also how the run knows which branch rendered. The `cssAssetId`-only branch
stays unmeasurable on that host for the reason given above, and this contract
stays its standing evidence. Evidence:
`docs/testing/evidence/2026-10-02-issue-243/`.

## Postscript (2026-10-01, the legacy `web_editor` editor)

The first postscript's open list ended with "the legacy `web_editor` editor
behind `html_legacy` and `mass_mailing_html`, which carries none of these
expressions". That was literally true, and it is what made this the largest of
the four: Odoo 18 ships **two** HTML editors, #210 and #237 rewrote
`html_editor`, and the previous editor's load and save sites are *different
expressions*, so not one of those eight rules fires on it. This closes it
(#238) with ten more rewrites on the Ingress asset location.

**Three widgets reach that editor, not two.** Read out of the pinned deb
(`ODOO_DEB_VERSION` 18.0.20260930) rather than assumed, because the first
acceptance question was which views are actually reachable:

| Widget | Views in the package | Reachable |
| --- | --- | --- |
| `html_legacy` | **none** | no — outside its own registration every occurrence in the package is a test (`web_editor/static/tests/`: `html_field_tests.js`, `banner_tests.js`, `link_tests.js`, `list_tests.js`) |
| `mass_mailing_html` | `mass_mailing/views/mailing_mailing_views.xml` (`body_arch`) | yes — the mail designer, on a module installed on `odoo_parity` |
| `account_payment_register_html` | `account/wizard/account_payment_register_views.xml` (`installments_switch_html`) | yes — Register Payment's installments note |

The third is this Iteration's finding and the issue did not name it: `account`
subclasses the legacy field and `t-inherit`s its template, so Register Payment
renders down the plain readonly path. Its own value is computed prose with no
URL in it, so nothing escaped there; the path is rewritten because the path is a
markup insertion of a record value, and the next value that arrives there is not
this ADR's to predict. `html_legacy` is recorded as a widget registration with
no view behind it -- a finding, not a screen.

**The ten rewrites.** Six put the prefix on where markup becomes DOM, four take
it off where a value becomes a record. Each occurs exactly **once** in the whole
package; `odoo18ce/tests/fixtures/bundles/README.md` carries the per-bundle
counts and the derivation.

| | Expression | Site | Helper |
| --- | --- | --- | --- |
| 1 | `editable.html(options.value);` | `Wysiwyg.startEdition`, the editable's first load | `IN_VALUE` |
| 2 | `this.editable.innerHTML=value;` | `OdooEditor.resetContent`, every later load | `IN_VALUE` |
| 3 | `iframeTarget.innerHTML=this.props.record.data[this.props.name];` | the readonly iframe's refresh branch | `IN_VALUE` |
| 4 | `iframeTarget.innerHTML=value;` | the readonly iframe's first load | `IN_VALUE` |
| 5 | `cwindow.document.documentElement.innerHTML=value;` | the readonly iframe's sandboxed preview | `IN_VALUE` |
| 6 | `<div t-ref="readonlyElement" class="o_readonly" t-out="markupValue"/>` | the plain readonly path, in the field's own template | `IN_VALUE` |
| 7 | `getEditingValue(){…}` | the one read every save goes through | `OUT` |
| 8 | `const inlineHtml=editableClone.innerHTML;` | mass_mailing's inlined `body_html` | `OUT` |
| 9 | `this.wysiwyg.odooEditor.toolbarHide();const value=this.wysiwyg.getValue();` | the code view, opening | `OUT` |
| 10 | `codeview.val();this.props.record.update({[this.props.name]:value});` | the code view, closing | `OUT` |

All six insertions call `__WOOW_INGRESS_MARKUP_IN_VALUE__`, the helper the
previous postscript added, and for the same reason: every value here is
`this.props.record.data[name]`, an OWL `Markup` object, and `IN` returns a
non-string as it came. The helper is type-preserving, so jQuery's `.html()` and
OWL's `t-out` both see the shape they saw before -- which matters at rule 1,
where jQuery branches on `typeof value === "string"` and takes a different code
path for a `String` object.

**Why the strip is on `getEditingValue` and not on the `record.update` beside
it.** This is the one design decision in the ten. `updateValue` compares the
editing value with the ORM value before writing; strip at the write instead and
that comparison is prefixed-against-unprefixed, so **every** commit looks dirty,
writes the field, and sets `currentEditingValue` to a value that makes the
Wysiwyg reset its content on the next update. Stripping at the read keeps every
comparison in the file apples-to-apples -- `updateValue`'s, `_isDirty`'s, and
`Wysiwyg.isDirty`'s `_initialValue`, which is taken from the editable after the
prefix is already on it. The rewrite keeps the method's body byte for byte
inside an arrow IIFE, so `this` is unchanged and the class gains no member a
subclass could collide with. The Static-tier test drives the unchanged commit on
both sets of bytes, so the reason is executed and not asserted in prose.

**Two of the ten patterns begin mid-identifier, and that is a constraint of
nginx and not a shortcut.** nginx reads `$` in a parameter as the start of a
variable, in the pattern as well as the replacement, and there is no escape for
it; an unknown variable is a config nginx refuses to load, which the Build-tier
probe would catch as an add-on that does not start. This editor is jQuery-era
code, so `this.$editable.html(options.value);` and `$codeview.val();…` cannot be
matched whole. Each pattern starts *after* the `$` and leaves `this.$` / `$`
outside the match -- the same move the `${`-crossing rules of #211 make. A test
asserts each pattern is really the tail of the full expression, because a suffix
could otherwise be matching something else entirely.

**Four writes, not one, which is the part worth carrying forward.** The other
editor has a single write expression; this one has four, and three of them do
not go through `getEditingValue`:

- mass_mailing's `commitChanges` writes a **second field**. It clones the
  editable into a `srcdoc` iframe, runs `toInline` over it and stores the result
  as `body_html` (the `inline-field` option) with its own `record.update`. Miss
  that one and a mailing is *sent* with the Supervisor token in every image URL
  -- the only place in this family where a token leaves the installation.
- `toggleCodeView` writes twice, once on each toggle. It is bounded by the same
  expression as #240's twin -- `codeview: Boolean(odoo.debug && options.codeview)`
  -- so it is a developer in debug mode and nobody else. Covered here rather
  than filed, because it is a token *write* and two lines, where #240's is a
  render escape. The second half of this bound as first written ("and no shipped
  view sets that option") was false and is corrected by the last postscript
  below: five shipped views set it, none of them on *this* editor's three
  widgets, so what bounds this pair is debug mode and the fact that no shipped
  view reaches the legacy field with the option at all.

**What the mail designer's nested iframes turned out to be.** The issue asked
for the globals to be shown reachable from where each rewritten expression runs,
"the nested iframe of the mail designer included". The answer is that every one
of the ten runs in the **page's** realm. The editor's own iframe is built by
`_loadIframe` with `document.open(...).write(...)`, so it never was an HTTP
response and no Runtime shim ran in it -- and the bundle it loads,
`web_editor.wysiwyg_iframe_editor_assets`, carries neither `wysiwyg.js` nor
`OdooEditor.js`, so no rewritten expression is in that realm at all. That is a
measurement in the fixtures' README, beside the counts. The editor itself
arrives through `web_editor.backend_assets_wysiwyg`, which `_lazyloadWysiwyg`
fetches with `loadBundle` -- a `<script src>` the shim prefixes, so the request
goes through the Ingress asset location and gets the rewritten bytes. The inner
`srcdoc` iframe of rule 8 is only *read* from, by the parent's own code. And the
iframe assets load at all only because the generic HTML location already
prefixes `"src": "/` in `/web/bundle` JSON, which that rule's comment predicted
for the website editor and which turns out to be what keeps this screen alive.

**What is deliberately left alone on this editor.** The code view's `<textarea
t-att-value="markupValue">` renders the record's stored bytes, which is what a
source view should show -- on first render. `commitChanges` then refills it with
`codeViewEl.value = this.wysiwyg.getValue()`, the editable's value and therefore
prefixed, so after a commit the source view *does* show Supervisor-token URLs.
Said precisely rather than left as the unconditional claim it first read as: it
is cosmetic and nothing stores it, because rule 7 strips that same textarea where
`getEditingValue` reads it and rule 10 strips it on the way out. Prefixing the
`t-att-value` instead would make the source view lie about the record on the one
render that is right today, so the escape stays where it is visible.
`_onReadonlyClickChecklist` and `_onReadonlyClickStar`
write a value the *server* computed (`/web_editor/checklist`,
`/web_editor/stars`), so there is no prefix in it. `_toInline` round-trips
through the editable and back through `setValue`, where rule 2 prefixes
idempotently. And the legacy `loadImageInfo` shares `const
relativeSrc=srcUrl.pathname;` with `html_editor`, so #210's fifth rule already
covered it here -- which the first postscript noted and is now the one piece of
this editor that was never broken.

Group B stays uncovered, the Public origin stays untouched, `U-A6`'s probe list
is not extended, and no new global is published: the three helpers of #210 and
#237 were enough. What proves this fix is the Static-tier contract
(`odoo18ce/tests/test_ingress_legacy_html_editor.py`: all ten patterns counted
in excerpts derived through Odoo's own serve path, the two mid-identifier
patterns proved to be tails of their expressions, the rewritten template parsed
back as XML and checked to keep the attribute `account`'s `t-inherit` selects it
by, the unchanged commit driven on both sets of bytes, and every one of the ten
sites run in node with the globals present **and** absent).

**The Live rerun is done: 2026-10-02, Release 0.4.10, #243, all three lines
`PARITY` on both surfaces.** The *sent* mailing's body renders through the
readonly iframe with the `<img>` **attribute itself** prefixed; the designer loads
under Ingress; and the save stores `mailing.mailing.body_arch` **and**
`body_html` root-relative -- both, which is the half that matters, because the
inlined second field does not go through `getEditingValue` and is the one that
leaves the installation. One thing the row did not anticipate: all four fixture
mailings on that database had **empty** bodies, so line 3 needed a root-relative
picture seeded into a sent mailing first, and line 1 needed the designer actually
*typed into* -- a body seeded over RPC leaves the form clean, the save button
hidden, and a read-back of the seeded value would have scored a pass while
exercising neither rule, since both are the save seam. Rules 9 and 10 stay
unreachable for this record's own reason -- no shipped view sets `codeview` on a
legacy-editor field -- and are recorded there as unreachable rather than dropped.
Evidence: `docs/testing/evidence/2026-10-02-issue-243/`.

## Postscript (2026-10-01, the collaborative peer snapshot)

The last item the 2026-09-30 postscript left open was the only one on its list
that is a **token write** and not a render escape: a snapshot a collaborative
peer sends, whose URLs carry the sending page's prefix, stored by the receiving
session because "the strip removes only the prefix of the session doing the
saving". This closes it (#234). The fix is the one that postscript predicted --
the strip stops being about one value and becomes about the *shape* of a prefix
-- and the reason for it is not the one it gave.

**The premise did not survive reading what the token in the path is.** It is
the **add-on's** `ingress_token`, not the user's and not the session's: one
persisted secret per installed add-on, defaulted once by `secrets.token_urlsafe`
in Supervisor's app user-data schema, while the per-user session is a separate
secret that travels as the `ingress_session` cookie and never appears in a path.
Read on 2026-10-01 from `home-assistant/supervisor` on `main`, and named so the
next reader can check it rather than take it: `supervisor/apps/validate.py`
(`SCHEMA_APP_USER`, `vol.Optional(ATTR_INGRESS_TOKEN, default=secrets.token_urlsafe)`
-- a *user-data* default, so it survives a restart and an update),
`supervisor/apps/app.py` (`ingress_token` reads `self.persist`, and
`ingress_entry` is `/api/hassio_ingress/<it>`) and `supervisor/ingress.py`
(`create_session` mints `secrets.token_hex(64)` with a 15-minute sliding
validity, and `_update_token_list` maps *app* tokens to slugs). That is the one
load-bearing claim here that this repository cannot test, which is why it is
cited rather than asserted -- and why the Live row below records both prefixes
instead of assuming them equal.
This repository says the same thing from the other side and has since #144: the
menu/action adapter reads the prefix from `/addons/<slug>/info` **once** and
uses it for every session it opens (`e2e_menu_action_adapter.py:789`), which
would be broken if a prefix belonged to a session. So two Ingress sessions on
one add-on edit the same to-do under the *same* prefix, `path()` recognises what
the peer sent, and #210's literal strip already covered that pair. "A second
editor could store another user's Supervisor token" is not the shape of this
hole, and the measurement #234 was written around -- two Ingress sessions, one
to-do -- cannot by itself produce a foreign prefix.

**What is left is still a token write, and it is wider than two sessions.** A
value reaches the field carrying a prefix this page was not handed whenever the
add-on's token is not the one in the value:

- the add-on's token changes -- an uninstall and reinstall mints a new one, and
  so does a restored backup -- so every URL stored under the old one is now a
  prefix nothing recognises, in a record that is still served;
- a second add-on, or a second Home Assistant, reaching the same database;
- **a peer on the Public origin**, which is the realistic pair and the one that
  can put the token in the record today. That surface serves no Runtime shim and
  no Literal rewrite -- ADR 0003 keeps it the control group -- so a prefix it
  receives over the collaboration transport is a prefix it stores, and it has
  nothing to strip with. The Ingress side cannot prevent that write. What the
  wider strip does for it is **heal** the record: the next Ingress session to
  save the field removes the prefix, whoever put it there.

The same reading corrects two rows of the parity plan, which called that token a
*session* token: `RC-15` (deep links are not shareable) and `G-07` (a tab Odoo
opens for you). Both keep their severity and their advice -- the path still
carries a credential, and a link pasted to a colleague still does not open --
but what refuses it is the `ingress_session` cookie their browser does not have,
not a path that differs per person. `DOCS.md` says "your session token" to a
user and is left as it is: the sentence it is in tells them to share the Public
origin address instead, which is the right advice either way, and which secret
it is is not a user's question.

**What the transport actually carries**, which is what decides where the strip
has to be and how wide. It is not a serialised document: the collaboration
plugin ships *steps over serialised nodes*, each attribute's value byte for byte
(`html_editor/static/src/core/history_plugin.js:1168`), and the peer that joins
second is handed the first peer's whole document as a snapshot. The receiver
applies each one with `node.setAttribute(key, value)` (`:1198`, and `:1087` for
a later attribute mutation) -- which the Runtime shim wraps, so the value goes
through the shim's own `path()`. `path()` does not recognise a prefix that is
not this page's, treats the whole thing as a root-relative path and prefixes it
**again**: the receiving editable holds `<this page's prefix><the sender's
prefix>/web/image/...`. That is why the rule is every occurrence of *a* prefix
and not one leading prefix, and the Static-tier contract executes the stacking
rather than describing it.

Two is the most it becomes, and that is worth one sentence because the
attribute-*mutation* path meets the wrapper **twice**: the collaboration plugin
registers its own `set_attribute_overrides`, and `safeSetAttribute` sets the
value on a clone so the sanitizer can see it, reads it back and sets it on the
node. What stops a third prefix is `path()`'s own already-prefixed check -- by
then the value begins with this page's prefix -- so the contract pins that too,
rather than leaving a reader to wonder whether the stack grows with each hop.

**The fix is one expression, and it keeps one authority for what a prefix is.**
`__WOOW_INGRESS_MARKUP_OUT__` now removes every occurrence of `__INGRESS_PATH__`
*and* every match of the shape nginx's `$safe_ingress_path` map validates. Both
halves are needed and the order is not arbitrary: the prefix the gateway handed
this page is removed whatever its shape, because the gateway is what decided it
was a prefix and the value is in the page -- #210's own contract renders the
shim with `/api/hassio_ingress/token`, which that map would refuse, and it keeps
passing untouched. The shape half is for prefixes this page never saw. The map
stays the single place that says what an Ingress prefix looks like;
`odoo18ce/tests/test_ingress_peer_snapshot_prefix.py` derives the strip's
pattern and the map's from the template and refuses a difference, bounds and
character class included. The shape is *not* published as a global: no rewritten
expression needs it, the strip is its only reader, and the prefix script -- the
parameter that is short of room, which `test_nginx_parameter_budget.py` now
measures -- is where a published global would have had to go.

**A token longer than the map accepts is left alone, not cut to the bound.**
The pattern ends in a lookahead at the token class, so a 129-character token
fails to match rather than matching its first 128 characters and leaving the
rest joined to the path. A URL with bytes taken out of its middle is worse than
the escape it was: the escape is measured, reversible and already named here,
while `/api/hassio_ingress/xxx…x` turned into `xxx/web/image/1` is a value
nobody can read back. The same rule as the two shapes `IN` refuses.

**And the two costs, said rather than discovered.** Prefix-shaped text a user
typed into a description is removed on save -- the same decision #210 made for
this page's prefix, for the same reason, which is that those bytes are a
Supervisor token and de-tokenising a credential is the right answer for a value
on its way to storage. And `IN` is deliberately **not** taught the shape: a
foreign prefix is not healed on render, it is stacked on as before, so a picture
a peer sent is fetched from a path that 404s until the value is saved and
reloaded. Healing on the way *in* would mean rewriting somebody else's address
into ours while the value is still the record's; the record is made clean on the
way out, where the token is the harm. That is the same half-rule the
snippet-thumbnail postscript states, applied to a value that arrived from
somewhere else.

No new global, no new rewrite and no new `sub_filter`: every save site in this
family already calls this helper, so the five of #210 and the four `OUT` rules
of #238 are all covered by the one change -- including the mailing's inlined
`body_html`, the one value in this family that leaves the installation. Group B
stays uncovered, the Public origin stays untouched, and `U-A6`'s probe list is
not extended.

What proves it at the Static tier is
`odoo18ce/tests/test_ingress_peer_snapshot_prefix.py`: the two patterns derived
from the template and held together, the bounds from both sides, the stacking
the peer path produces executed through the published `path()`, and the
rewritten `updateValue` and `_commitChanges` bytes driven over a peer value --
including that the urgent-save comparison still holds, since both of its sides
go through the same strip. **The Live row belongs to #243**, which carries this
family's reruns, and this Iteration refined that row rather than leaving it to
guess: two Ingress sessions on one to-do will show the *same* prefix and the row
must record both rather than assume a difference, and the pair that can produce
a foreign prefix on this host is one Ingress session and one Public-origin
session on the same record. The script is
`odoo18ce/tests/e2e_collab_peer_snapshot_live.py`, whose pure parts (the prefix
shape, the redaction that puts a session's label where its token was, the verdict
and the report) are tested at the Static tier by
`test_e2e_collab_peer_snapshot.py`.

**It has now been run: 2026-10-02, Release 0.4.10, #243.** Both pairs `CLEAN`,
`stored_prefixes` empty, `escalate_issue_234_to_blocker: false`, so **#234 stays
`severity: important`** -- nothing has measured an escape here, which is what its
own criteria say the escalation to blocker waits for. The prefix equality this
record predicted for the `ingress-ingress` pair was measured rather than assumed
(`prefixes_equal: true`), which is the reason that pair is clean.

Two things that run did **not** establish, and they bound how far its `CLEAN`
reaches. **The collaboration transport never delivered, on either pair**: the
sender's unsaved marker never reached the receiving session in 30 s, so the two
sessions never became peers. So the verdicts say the *save path* stores no
prefix; they do not say a *delivered* peer snapshot stores none, which is what
this postscript is about. And the two-step healing read this record asks for on
the `ingress-public` pair -- read after the Public peer saves, then save once
under Ingress and read again -- has no implementation in `do_run`, and had no
subject on that run because nothing was delivered. Both are #265. **Both are now
done, and the cause of the non-delivery was this repository's own driver and not
the host: see the 2026-10-02 postscript at the end of this record.** Separately,
`probe` turned out to write the field it says it does not, and its marker is a
constant, which made one reading a false `delivered: true` (#263). Evidence:
`docs/testing/evidence/2026-10-02-issue-243/`.

## Postscript (2026-10-01, the media dialog's preselection)

The 2026-09-30 postscript's open list ended with two comparisons rather than two
insertions: `ImageSelector.isInitialMedia` on `src` and
`DocumentSelector.fetchAttachments` on `href`, which decide whether reopening
the media dialog on an existing image or document link highlights the attachment
it came from. This closes both (#239), and the finding is that **only one of
them was ever broken, and doing to the other what this ADR said to do would have
broken it.**

| | Comparison | Measured | Shipped |
| --- | --- | --- | --- |
| 1 | `ImageSelector.isInitialMedia` on `getAttribute("src")` | element prefixed by the shim, `attachment.image_src` not | rewritten, `OUT` on the element side |
| 2 | the same on `dataset.originalSrc` | element prefixed by the **HTML location**, `attachment.image_src` not | rewritten, `OUT` on the element side |
| 3 | `DocumentSelector.fetchAttachments` on `getAttribute("href")` | both sides prefixed | left alone |

Each of the three exists twice, because Odoo 18 ships the media dialog twice --
`html_editor`'s, which a backend form opens, and the legacy `web_editor`'s,
which `wysiwyg.js` and the website editor's snippet options open. Nine files
import `@web_editor/components/media_dialog/media_dialog` from outside that
component's own directory, tests aside: two of them elsewhere in `web_editor`
itself (`.../js/wysiwyg/wysiwyg.js` and `.../js/editor/snippets.options.js`) and
seven in other addons (`website/static/src/snippets/s_image/options.js`,
`.../s_image_gallery/options.js`, `.../s_rating/options.js`,
`website/static/src/components/dialog/seo.js`,
`website_sale/static/src/js/website_sale.editor.js`,
`mass_mailing/static/src/snippets/s_rating/options.js` and
`web_unsplash/static/src/media_dialog_legacy/image_selector.js`). The two
`image_selector.js` files are the same code with different quote characters, so
row 1 is **two** `sub_filter` rules; row 2 is **one**, because it is the single
line the two dialogs spell identically. Fixing only the dialog the issue named
would have left the mail designer's and the website editor's as it was.

**Row 1 is the bug and the fix is the `get_image_info` move.** The element's
`src` carries the prefix under Ingress -- the shim's `setAttribute` wrapper puts
it there on an image the dialog just inserted, and `__WOOW_INGRESS_MARKUP_IN__`
puts it there on one that came out of the record -- while `attachment.image_src`
is `ir.attachment._compute_image_src`'s own
`/web/image/<id>-<checksum>/<quote(name)>`, delivered over `call_kw` and
root-relative. So the comparison never matched, every tile stayed unselected,
and the user had to find the file again. The element side goes through
`__WOOW_INGRESS_MARKUP_OUT__`, which is the same thing #210 did to
`get_image_info`'s argument: one URL authority, no new global, and a no-op on a
value that has no prefix. It also inherits #234 for free -- the strip removes
every prefix *of the shape* and not only this page's, so an image a collaborative
peer sent is matched too. The ORM side is left untouched, because it is never
prefixed, and that asymmetry is pinned from its own side: a test asserts that no
generic literal rule reaches either operand of this comparison.

**Row 2 is the one this Iteration nearly got wrong, and a review round caught
it.** The sentence this ADR already wrote is true and is not the whole answer:
`data-original-src` is not a `data-src`, the markup helper's attribute test is
an exact name, and the `setAttribute` wrapper's list is
`href`/`src`/`action`/`xlink:href` -- so nothing in **the shim** prefixes that
attribute, and `loadImageInfo` assigns the server's own `image_src` into it.
What prefixes it is the **generic HTML location**, whose rule is written for
`src="/` and, `sub_filter` being a plain substring search, matches inside the
longer attribute name `data-original-src="/...`; no neighbouring rule claims
that position first, and `data-src="/` claims only its own. Odoo ships that
attribute inside stored arch -- every themed image in
`mass_mailing_themes/views/mass_mailing_themes_templates.xml` carries one -- so
markup delivered as an HTML response reaches the browser with a prefixed
`data-original-src` while the same attribute on a field value, which arrives
over `call_kw` and is not rewritten, is root-relative.

That branch `return`s *before* row 1 for any image the image tools have
touched, so row 1 alone would never have reached the website editor's dialog:
the screen would have stayed broken with three rules shipped and every test
green. It is rewritten too, and the contract now holds the claim in two
executed pieces rather than one narrated one -- the shim driven over both the
markup helper and the `setAttribute` wrapper to show what it does *not* prefix,
and a page-HTML sample served through the generic location's own rules by a real
nginx to show what does. "Nothing prefixes this attribute" was exactly the kind
of claim that rots, and it was already false when written.

**Row 3 was already correct, and this is the part worth reading.** Its left
operand is the template literal `` `/web/content/${attachment.id}` ``, which
begins `` `/web/ `` -- one of the generic literal rules the Ingress asset
location has carried since #166. So the *bundle* arrives at the browser with the
prefix spliced into that literal, the `href` beside it is prefixed by the shim,
and the comparison has been prefix-against-prefix since Ingress existed. The
`OUT` this ADR's open list asked for would have stripped one side and left the
other, so the dialog would have stopped highlighting the document it came from
-- a regression on a working screen, delivered as a fix.

That was measured rather than reasoned, and the measurement is in the test
rather than in this paragraph. `odoo18ce/tests/test_ingress_media_dialog_preselect.py`
serves all four captured excerpts through a **real nginx** carrying that
location's own literal rule set and requires the answer to equal, byte for byte,
what the drivers' `str.replace` produced -- so the two document excerpts are
shown arriving with the prefix inside the literal, and the two image ones
changed by nothing but this family's own three rules. On top of that it derives
the `` `/web/ `` rule from the template rather than quoting it; asserts it is the
*only* generic rule reaching the excerpt; runs the comparison in node and reads
back which attachment was selected; executes the one-sided strip and shows it
selecting nothing; and refuses any `sub_filter` that names the `href` read at
all, so the rule the open list asked for cannot arrive later by a reader
following the list. The coupling runs through two independent mechanisms that
have to agree, which is exactly the kind of thing this repository holds with a
test rather than a comment -- remove the `` `/web/ `` rule and four tests in that
file go red naming it.

**A general rule this one earned, twice over.** A comparison is not a URL site
with a known direction. Before teaching one about the prefix, measure *both*
operands as the browser receives them: a literal in a bundle is subject to every
generic rule in the asset location, a DOM read to every generic rule in the
**HTML** location as well as to the shim's wrappers, and an ORM value to none of
them. Both of this postscript's surprises are the same mistake in opposite
directions -- row 3 assumed a prefix on one side only and would have been broken
by the fix; row 2 assumed no prefix at all, and "nothing in the shim touches it"
was read as "nothing touches it". The shim is not the only thing in this product
that adds a prefix, and a bare-substring `sub_filter` reaches further than the
attribute it was written for.

Display state only: nothing here is stored either way, which is why #239 is the
one row in #243's register that cannot escalate in severity from what the host
shows. No new global, no new helper, Group B still uncovered, the Public origin
untouched, `U-A6`'s probe list not extended, and the Rewrite scan unaffected --
an attachment's `image_src` is not in a bundle, so no Generated rewrite could
derive it. The Live rerun was #243's, and this Iteration refined that row by
comment rather than leaving it to guess: the document half has a different
expectation -- a check that a working screen still works, not that a broken one
was fixed -- and the image half is worth running on the website editor's dialog as
well as the To-do form, because row 2's prefix only appears on the HTML-response
path.

**It ran on 2026-10-02, Release 0.4.10 (#243), and one of the three lines was
measured.** The image line on the To-do description passes: Ingress preselects the
attachment with the element's `src` prefixed, Public does the same with it
root-relative. That run also asked the page whether the rule had arrived and got
`rule_in_served_method: true` under Ingress and **`false`** on the Public origin --
a direct measurement that the rewrite lives only in the Ingress asset location,
which is the same thing #237's check 3 says from the other side.

The other two lines are unmeasured, each for its own reason, and neither can move
#239's severity because nothing it measures is stored. **The document line has no
control that reopens the dialog** on the current editor: Replace is a toolbar item
in the `image` namespace and a document is an `<a class="o_image">`. Its premise
was measured instead and it holds -- the element's `href` arrives prefixed and so
does the served `fetchAttachments` literal (372 bytes against 309 on the Public
origin), so the comparison is prefixed-against-prefixed, which is why no `OUT` was
shipped for that read. **The `data-original-src` line was reached but not
exercised**: the only visible image on the website home page is a record-field
image whose `data-original-src` is absent, so row 2's branch never executes, and
both surfaces preselected none -- no divergence, and nothing measured. Both are
#266.

One shape worth keeping, because it is how a false negative looks here: a static
module asset and a URL-type library attachment *both* preselected none, correctly,
on both surfaces. `isInitialMedia` only matches an attachment the dialog listed, so
"none selected" is a finding only when the other surface selected one for the same
element. The fixture that measures anything is an attachment scoped to the record.
Evidence: `docs/testing/evidence/2026-10-02-issue-243/`.

## Postscript (2026-10-01, the code view round trip)

The first item on the 2026-09-30 postscript's open list was "the code view's
`editable.innerHTML = this.value` on toggling back". It is the last of that list
to close (#240), and the sixth markup insertion of `html_editor`'s own html
field. `toggleCodeView` commits, flips `state.showCodeView`, and -- going back
*off* -- assigns the record's value straight into the editable:

    async toggleCodeView() {
        await this.commitChanges();
        this.state.showCodeView = !this.state.showCodeView;
        if (!this.state.showCodeView && this.editor) {
            this.editor.editable.innerHTML = this.value;
            this.editor.shared.history.addStep();
        }
    }

None of #210's five rules is on that line, so under Ingress every root-relative
URL in the record was fetched from the Home Assistant root and answered 404 --
the same escape as the two onboarding pictures, on the same field, reached a
different way. One `sub_filter` on the Ingress asset location closes it, and the
interesting parts are the helper it calls, the half it does **not** need, and the
bound, which this Iteration found to be wider than both #240 and the second
postscript above said.

**The helper is `__WOOW_INGRESS_MARKUP_IN_VALUE__`, and writing the obvious rule
with `IN` would have shipped a silent no-op.** `get value()` returns
`markup(newVal)` whenever the record's value is a `Markup`, and every html
field's value is one -- the relational model wraps an `html` field that way. The
plain `IN` tests `typeof h === "string"` and returns anything else as it came, so
a rule written with it would have matched its pattern, changed the bytes, passed
a count test, and left the picture exactly where it was. That is #237's finding
applied at a site #237 did not touch, and
`odoo18ce/tests/test_ingress_code_view_toggle.py` executes it rather than
restating it: Odoo's own getter is a captured fixture spliced into the class the
test drives, and one test drives the `IN` rule and shows the picture still
fetched from the Home Assistant root.

**There is no `OUT` half, because the field already has one and this change must
leave it exactly as it was.** Nothing is stored by this site; what stores is
`_commitChanges` on the next blur, which reads the editable and hands the value
to `updateValue` -- #210's rule 2 -- and compares a clone through rule 5. The
strip only *removes* a prefix, so it is a no-op over a record that was never
prefixed and takes this rule's prefix off again over one that was. That is a
claim about two rules standing in a line, so the test drives the line: this
rule's own output into #210's shipped `updateValue` bytes, reading back what the
record got (root-relative, `lastValue` computed from the value that was stored),
and the same round trip through Odoo's *unrewritten* `updateValue` to show what
#210 is standing between this rule and the database for. So #240 stays a render
escape in both directions, and the `codeview` branch of `_commitChanges` --
which stores the textarea's own bytes -- was already covered by rule 2 when
#210 shipped.

**The bound is debug mode, and "no shipped view sets the option" was false.**
`codeview: Boolean(odoo.debug && options.codeview)` needs debug mode *and* a
view that sets the option, and the issue said no shipped view does; the second
postscript above repeated it for this field while bounding the legacy editor's
twin. Five shipped views in the pinned package set it, on four fields:
`res.users.signature` in both of `base`'s user forms (`view_users_form` and
Preferences' `view_users_form_simple_modif`), `ir.actions.act_window`'s
`help` -- which is #158's field -- `mail.template`'s `body_html`, and
`hr_recruitment`'s send-mail wizard body. The last two are `html_mail`, a
subclass of this field, so they inherit the site. What survives of the bound is
debug mode, which is why the label stays `severity: minor`: on the parity
database this is reachable by a developer in debug mode and by nobody else.

**And one shape of that screen produces a false pass, which is worth carrying
forward to every Live check in this family.** A value whose parse yields a
non-empty `<head>` turns `sandboxedPreview` on (`computeContainsComplexHTML`),
the field renders through the readonly `HtmlViewer` -- #237's two rules, not
this one -- and there is no `Wysiwyg`, so `this.editor` is undefined and
`toggleCodeView` never reaches this site. The toggle still works, the field
still looks right, and nothing under test runs. A mail template's `body_html` is
exactly the value most likely to be full HTML, so the screen to run is the user
signature, and the no-editor branch is driven in the Static tier on purpose.

The code view's own textarea is deliberately left alone:
`<textarea t-ref="codeView" class="o_codeview" t-att-value="this.value"/>` is a
source view and should show the bytes the record holds, which is the same
decision the second postscript above records for the legacy editor's textarea --
and here it is the stronger version of it, because this field's textarea is
*only* ever the record's value: `_commitChanges` stores from it rather than
refilling it. A test refuses a `sub_filter` that names it.

The pattern was derived from the pinned `.deb` through Odoo's own serve path and
occurs once each in `web.assets_backend`, `web.assets_web`,
`web.assets_web_print` and `project.webclient` -- the same four as #237's two,
and for the same reason: both files are `html_editor/static/src/fields/*`, which
exactly two manifests name. It is zero in the other fifteen bundles the control
group serves on that route, the media-dialog ones included, which is the
difference from #239. `odoo18ce/tests/fixtures/bundles/README.md` carries the
counts; a real nginx carrying this location's whole literal rule set is asked
what it does to both excerpts, so "no other rule reaches them" is measured and
not assumed.

No new global, no new helper, Group B still uncovered, the Public origin
untouched, `U-A6`'s probe list not extended, and the Rewrite scan unaffected --
record content is not in a bundle. With this closed, every item on the
2026-09-30 open list has an answer.

**The Live rerun is done: 2026-10-02, Release 0.4.10, #243, both halves `PARITY`
on both surfaces** -- the code view toggled off leaves the picture loading under
the Ingress prefix at `route_escape=0`/`http_4xx_5xx=0`/`console_error=0`, and the
saved value reads back root-relative. The toggle was the real toolbar command
(`codeview_buttons: 1`, `code_view_shown: true`), so the OFF click is the one that
reaches the assignment these two rules patch.

**The screen is not the one this postscript names.** It picked a user's signature
in Preferences precisely *because* `html_mail` was the thing to avoid -- a mail
body being the value most likely to be full HTML. On this build the signature is
served by that widget anyway (`o_field_html_mail`) and its editor comes up
**empty**, showing the `o-we-hint` placeholder with a fragment value present in
the record; an empty editable has no text to select, so the floating toolbar is
never raised and the `codeview` group never renders. The check was taken on
`ir.actions.act_window.help` -- the other view that sets the option, a plain `html`
field on the current editor, `sanitize_tags=True` so it cannot become a sandboxed
preview. And one thing no reading of the source would have given: **`?debug=1` is
not sticky across a navigation on this host.** After `/odoo?debug=1` the next page
reported `odoo.debug === ""`, the command was never registered, and the toolbar
came up with seven groups and no code view -- which reads exactly like a missing
button. The flag belongs on the form navigation itself. Evidence:
`docs/testing/evidence/2026-10-02-issue-243/`.

## Postscript (2026-10-02, #265, the peer snapshot that was actually delivered)

The postscript above about the collaborative peer snapshot ends with two things
#243's run did not establish. Both are now established, and the first one's cause
was **this repository's own driver** rather than anything about the host.

**Why nothing was ever delivered.** No view that shows
`project.task.description` sets `collaborative_trigger`, so the collaboration
plugin takes the `undefined` branch and joins the peer network on the editable's
`focus` event and nowhere else (`collaboration_odoo_plugin.js:91-99`, read from
the deployed image and confirmed against the pinned `.deb`). A session whose
`ptpJoined` is still false **discards every signalling notification it receives**,
including the other session's `ptp_join` (`:156-158`) -- no log, no console
message, nothing in the DOM. `e2e_collab_peer_snapshot_live.py` focused the
sending session by accident, because typing needs a focused editable, and focused
the receiving one only *after* the 30-second wait had expired. So both of #243's
pairs were predicted to time out by the source, before the host was involved at
all. The three questions #265 asked are each a reading in the record now: the
field is collaborative on both surfaces, the bus worker is `CONNECTED` on both,
and both sessions subscribe to
`editor_collaboration:project.task:description:<id>` -- the channel the plugin
builds from the record and not from the session, which is why one record is one
channel whatever surface each peer is on.

**What a delivered snapshot does.** 2026-10-02, the same Release 0.4.10, the same
host, run `WOOW-PEER-20261002T064500Z`:

- `ingress-ingress`: delivered, and still `CLEAN`. That is the sentence this ADR's
  earlier postscript was quoted for and which no run had yet made -- the strip ran
  on a value that arrived over the transport, not merely on one the same session
  had loaded.
- `ingress-public`: delivered, and the Public peer's save stored
  `/api/hassio_ingress/<the add-on's token>` on both of the to-do's images.
  **`FOREIGN-PREFIX-STORED`: the write this record has described since 2026-10-01,
  measured for the first time.** Then the two-step this record asked for -- the
  Ingress session discards its leftover, reloads the record so its editor holds
  what the Public peer stored (`loaded_prefixes: ["A"]`), and saves once -- and
  both `src` come back root-relative, `healing.verdict: CLEAN`.

So "the Ingress fix heals the record on the next Ingress save rather than
preventing the write" is no longer a prediction this record makes; both halves of
it are measured. The write is registered as `G-08` in the parity plan's section
11, because what it leaves behind is a record that no Ingress session saves
again: until one does, the token is in the row.

**The escalation rule reads every value the run read, and that is deliberate.**
#234's criterion is a *confirmed* stored foreign token, so
`escalate_issue_234_to_blocker` is `true` on this run: the prefix was in the
record, and a rule that looked only at the end of the run would answer "no" to
the very measurement that proves the escape exists. The first spelling of it did
look only at the end, and a review caught what that produced -- a boolean named
after #234's rule reporting `false` on the run that had just watched a Supervisor
token reach `project.task.description`. The heal is reported *beside* the
escalation and not instead of it (`foreign_prefix_healed`, plus
`foreign_prefix_still_stored` for what is in the field now), and `report` splits
`CLEAN` into `with_a_delivered_transport` and `with_no_delivery`, so the two
sentences #243's run was quoted as having said cannot be written as one again.
Whether #234's severity follows the confirmation or the persistence is a decision
for that issue; #265's run reports both readings and takes neither.

One thing the run found about its own method, worth keeping because it is the
second time a marker has cost a reading here (#263 was the first). A run is one
`--run-id` across **both** pairs and `run` stores its marker, so the second pair
opened a record already holding the first pair's `<run-id>-A`: the baseline guard
refused the match and returned without waiting, which made that transport reading
**void** rather than negative. The marker now carries the pair as well as the run
id. Evidence, including the void attempt:
`docs/testing/evidence/2026-10-02-issue-265/`.
