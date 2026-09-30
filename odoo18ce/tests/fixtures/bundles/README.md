# Asset bundle fixtures

Excerpts taken verbatim from the JavaScript bundles the control group serves
(ADR 0003), with the parity plan's 25 applications installed. They exist for
the exact-expression Literal rewrites of ADR 0006: an unmatched `sub_filter`
is a silent no-op — nginx does not complain, no test turns red, the page
renders and only the link is wrong — so a rule may never be written from a
guess about what the bundle says.

Captured 2026-09-22 from Odoo 18.0, through the control group's Public origin:

| File | Bundle | What it holds |
|---|---|---|
| `discuss_invitation_link.js` | `web.assets_backend` | `Thread.invitationLink`, the Discuss channel invitation link |
| `website_page_url_field.js` | `web.assets_backend` | `PageUrlField.setup`, the base shown before a website page's path |
| `website_share_snippet.js` | `web.assets_frontend` | `ShareWidget._onShareLinkClick`, the share snippet's outbound URL |

The same expressions appear unchanged in `web.assets_web`,
`web.assets_web_print`, `web.assets_frontend_lazy` and
`im_livechat.assets_embed_external`; each bundle carries exactly one
occurrence, and no in-Ingress address shares any of the three patterns.

Captured 2026-09-28 the same way, for the Ingress prefix rewrite of issue #170:

| File | Bundle | What it holds |
|---|---|---|
| `website_editor_snippet_thumbnail.js` | `web_editor.assets_wysiwyg` | `registerTemplate("web_editor.SnippetsMenu", ...)`, the Blocks panel's OWL template, which draws each tile with `t-attf-style="background-image: url({{snippet.thumbnailSrc}});"` |

Odoo 18 appends its OWL templates to the bundle unminified, after the
JavaScript, as `registerTemplate(<name>, <source path>, <template>)` with the
last two arguments written as template literals — so a template is served
through the same Ingress asset location as the code, and an exact-expression
rewrite can reach it. The excerpt is that whole call, because the test parses
its third argument as XML to prove the rewritten attribute is still
well-formed.

`url({{snippet.thumbnailSrc}})` was measured on 2026-09-28 across every bundle
the control group serves on that route. Only `web_editor.assets_wysiwyg` — the
bundle the website editor loads lazily — carries it, once. `web.assets_backend`,
`web.assets_web`, `web.assets_web_print`, `web.assets_frontend`,
`web.assets_frontend_lazy`, `web.assets_frontend_minimal`,
`web.assets_backend_lazy`, `web.report_assets_common`, `website.assets_wysiwyg`,
`website.assets_editor`, `web_editor.assets_media_dialog`,
`mass_mailing.assets_wysiwyg` and `im_livechat.assets_embed_external` carry it
zero times. `website.SnippetsMenu` (in `website.assets_wysiwyg`) does not repeat
the tile: it is a `t-inherit` patch over this template, so it takes the rewritten
attribute with it.

Captured 2026-09-28 the same way, for the `location` writes of issue #174:

| File | Bundle | What it holds |
|---|---|---|
| `action_menu_url_item.js` | `web.assets_web` | `ActionMenus.onItemSelected`, which runs `browser.location=item.url` for a cog-menu item that carries a `url` and no `action` — the invoice **Download > PDF** item |
| `act_url_self_target.js` | `web.assets_web` | `_executeActURLAction`, whose `target==="self"` branch runs `browser.location.assign(url)` |
| `home_client_action.js` | `web.assets_web` | the `home` client action, which builds `"/"+location.search` and runs the identical `browser.location.assign(url)` |

Measured on 2026-09-28 across every bundle the control group serves on that
route. `browser.location=item.url` occurs once and `browser.location.assign(url)`
twice — the `self` branch and the `home` action — in `web.assets_web`,
`web.assets_backend` and `web.assets_web_print`, and zero times in
`web.assets_frontend`, `web.assets_frontend_lazy`, `web.assets_frontend_minimal`,
`web.assets_backend_lazy`, `web.report_assets_common`, `web_editor.assets_wysiwyg`,
`website.assets_wysiwyg`, `website.assets_editor` and
`im_livechat.assets_embed_external`. The three excerpts above are byte-identical
in all three bundles that carry them, so one is captured from `web.assets_web`
and stands for the others.

Two other `location` writes share the neighbourhood and are deliberately left
alone: `browser.location.assign(_url.href)` and `browser.location.assign(href)`
(the router's `redirect()`, whose callers pass literals the shipped prefix rules
already cover) and `window.location.assign(response.url)` (session expiry, an
absolute URL). Neither matches either pattern.

Captured 2026-09-30 the same way, for the HTML editor's content round trip of
issue #210:

| File | Bundle | What it holds |
|---|---|---|
| `html_editor_attach_content.js` | `web.assets_backend` | `Editor.attachTo`, whose `editable.innerHTML=fixInvalidHTML(this.config.content)` is where an html field's stored value becomes DOM |
| `html_field_update_value.js` | `web.assets_backend` | `HtmlField.updateValue`, the one place the field writes the record — every save path reaches it, and `lastValue` is computed from the same argument |
| `image_processing_relative_src.js` | `web.assets_backend` | `loadImageInfo`'s preamble, which turns an `<img>`'s `src` into the `relativeSrc` it sends to `/html_editor/get_image_info` |

Measured on 2026-09-30 across every bundle the control group serves on that
route:

| Pattern | Bundles that carry it, once each | Bundles that carry it zero times |
|---|---|---|
| `editable.innerHTML=fixInvalidHTML(this.config.content)` | `web.assets_backend`, `web.assets_web`, `web.assets_web_print` | the twelve others below |
| `async updateValue(value,{changeId}={changeId:this.lastChangeId}){` | the same three | the twelve others below |
| `const relativeSrc=srcUrl.pathname;` | the same three, plus `web.assets_frontend`, `web.assets_frontend_lazy` and `web_editor.assets_wysiwyg` | the nine others |

The twelve others are `web.assets_frontend`, `web.assets_frontend_lazy`,
`web.assets_frontend_minimal`, `web.assets_backend_lazy`,
`web.report_assets_common`, `web_editor.assets_wysiwyg`,
`web_editor.assets_media_dialog`, `website.assets_wysiwyg`,
`website.assets_editor`, `mass_mailing.assets_wysiwyg`,
`im_livechat.assets_embed_external` and `html_builder.assets`. So the first two
rewrites reach the backend web client and no frontend or website-editor bundle.

The third reaches more, and that is wanted: `loadImageInfo` exists twice in
Odoo 18, once in `html_editor` (`docHref.startsWith("about:")`, calling
`/html_editor/get_image_info`) and once in the legacy `web_editor`
(`docHref==="about:srcdoc"`, calling `/web_editor/get_image_info`). The pattern
is the one line they share, both routes are the same controller method, and
both need the same root-relative path — so one rule covers the backend and the
frontend editor alike. Only the `html_editor` variant is captured here, since
it is the one the To-do form loads; `test_the_fixtures_are_verbatim_regions`
pins the excerpt's ends so a drift in either shows up.

The first two excerpts are byte-identical in the three bundles that carry them,
so each is captured from `web.assets_backend` and stands for the others. Each
is a whole method or a self-contained preamble, because the test executes it:
`attachTo` against an editable that reports what the browser would fetch,
`updateValue` against a record stand-in that reports what would be stored, and
the preamble against a fake `<img>`.

## Re-capturing

The bundles are public, so no login is needed; the asset route redirects a
stale version to the current one:

    curl -sL --compressed -o web.assets_backend.min.js \
      "$ODOO_BASE_URL/web/assets/1/any/web.assets_backend.min.js"

Then cut the region between the anchors the tests assert on
(`tests/test_ingress_browser_built_links.py`) and replace the file here. If an
Odoo upgrade moves one of the expressions, the fixture no longer contains the
`sub_filter` pattern and the test says so — but note the direction of that
guard: it protects the rules in this repository against a **fixture** that has
been re-captured, not against a live bundle that drifted while the fixture sat
still. Re-capture on every Odoo point release.
