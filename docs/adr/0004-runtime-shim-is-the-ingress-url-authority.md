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
no backslash and no `${`, and quotes with `'` -- which is why this is the one
`sub_filter` in the template whose replacement is written with a double-quoted
parameter. `thumbnailSrc` keeps its raw value, so `save_snippet` stores exactly
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

Three shapes stay outside the pair, and all three fail safely -- the URL keeps
escaping rather than being corrupted. A start tag holding a `>` inside an
attribute value is not recognised as a tag. An unquoted value has no closing
delimiter to consume. And an unquoted value that swallows the attribute after
it (`alt=a"src="/x"`, which is how a browser parses it too) leaves the inner
`src` preceded by a quote rather than by whitespace, which the walk requires.
What *is* reached and is not really an attribute is markup nested inside
another attribute's value, and a start tag written inside a comment: both are
prefixed -- visible in the editor until the next load, never in the record,
because `OUT` removes the prefix from the whole string.

**Why `OUT` is wider than `IN` rather than its mirror.** It is not only that
`IN` can reach the two shapes above. The shim's own wrappers prefix attributes
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
which the To-do field does not set); a snapshot a collaborative *peer* sends
over WebRTC, which is worth naming precisely because it is the one open item
that is a **token write** and not only a render escape -- the snapshot
serialises that peer's editable, so it carries *that* peer's Ingress prefix,
and the strip removes only the prefix of the session doing the saving, so a
second editor could store a foreign Supervisor token in
`project.task.description`. The *server* reset is covered; this one is not,
and it is not closed here for two reasons: nothing has measured the
collaboration transport on the test host (it needs two simultaneous Ingress
sessions on one to-do), and a strip that removes a *foreign* prefix has to
reason about what an Ingress prefix looks like, which today only nginx's
`safe_ingress_path` map does. It belongs to its own issue with its own
measurement. Also open: the media dialog's two preselection comparisons --
`ImageSelector.isInitialMedia`, which compares a prefixed `src` with
`attachment.image_src`, and `DocumentSelector.fetchAttachments`, which compares
a prefixed `href` with `/web/content/<id>` -- so reopening the dialog on an
existing image or document link does not highlight the attachment it came
from. The first was already true before this change for anything the dialog
itself inserted under Ingress, because the shim's `setAttribute` wrapper
prefixes `src` and `href`; both are display state, and closing them means
teaching those comparisons about the prefix the way the `get_image_info`
argument was taught. Also open: the readonly `HtmlViewer`, which is none of
the five sites and reaches markup twice over -- `t-out` on the plain path and
`iframeTarget.innerHTML = content` on the `hasFullHtml`/`cssAssetId` path, so
whoever picks that item up has two insertions to cover and not one; and the
legacy `web_editor` editor behind `html_legacy` and `mass_mailing_html`, which
carries none of these expressions. None has been
measured escaping -- except the peer snapshot, which is unmeasured rather than
clean -- and each is its own issue.

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
