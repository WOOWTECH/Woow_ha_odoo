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
| `collaboration_reset_from_server.js` | `web.assets_backend` | `resetFromServerAndResyncWithPeers`, the collaboration plugin's stale-document reset, which assigns the ORM value straight to `editable.innerHTML` — the second render site, and one a `'collaborative': true` field reaches |
| `html_field_update_value.js` | `web.assets_backend` | `HtmlField.updateValue`, the one place the field writes the record — every save path reaches it, and `lastValue` is computed from the same argument |
| `html_field_commit_changes.js` | `web.assets_backend` | `HtmlField._commitChanges`, whose `comparisonValue` is read off the clone and compared with `lastValue` on the urgent path |
| `image_processing_relative_src.js` | `web.assets_backend` | `loadImageInfo`'s preamble, which turns an `<img>`'s `src` into the `relativeSrc` it sends to `/html_editor/get_image_info` |

Measured on 2026-09-30 across every bundle the control group serves on that
route. Each row is the `sub_filter` source as the template ships it, byte for
byte — a shortened stand-in would be a count of a different pattern:

| Pattern | Bundles that carry it, once each | Bundles that carry it zero times |
|---|---|---|
| `editable.innerHTML=fixInvalidHTML(this.config.content)` | `web.assets_backend`, `web.assets_web`, `web.assets_web_print` | the twelve others below |
| `if(content){this.editable.innerHTML=content;}` | the same three | the twelve others below |
| `async updateValue(value,{changeId}={changeId:this.lastChangeId}){this.lastValue=normalizeHTML(value,this.clearElementToCompare.bind(this));` | the same three | the twelve others below |
| `const comparisonValue=el.innerHTML;` | the same three | the twelve others below |
| `const relativeSrc=srcUrl.pathname;` | the same three, plus `web.assets_frontend`, `web.assets_frontend_lazy` and `web_editor.assets_wysiwyg` | the nine others |

The twelve others are `web.assets_frontend`, `web.assets_frontend_lazy`,
`web.assets_frontend_minimal`, `web.assets_backend_lazy`,
`web.report_assets_common`, `web_editor.assets_wysiwyg`,
`web_editor.assets_media_dialog`, `website.assets_wysiwyg`,
`website.assets_editor`, `mass_mailing.assets_wysiwyg`,
`im_livechat.assets_embed_external` and `html_builder.assets`. So the first
four rewrites reach the backend web client and no frontend or website-editor
bundle.

The fifth row, `const relativeSrc=srcUrl.pathname;`, reaches more, and that is
wanted: `loadImageInfo` exists twice in Odoo 18, once in `html_editor`
(`docHref.startsWith("about:")`, calling `/html_editor/get_image_info`) and
once in the legacy `web_editor` (`docHref==="about:srcdoc"`, calling
`/web_editor/get_image_info`). The pattern is the one line they share, both
routes are the same controller method, and
both need the same root-relative path — so one rule covers the backend and the
frontend editor alike. Only the `html_editor` variant is captured here, since
it is the one the To-do form loads; `test_the_fixtures_are_verbatim_regions`
pins the excerpt's ends so a drift in either shows up.

The first four excerpts are byte-identical in the three bundles that carry
them, so each is captured from `web.assets_backend` and stands for the others.
Each is a whole method or a self-contained preamble, because the test executes
it: `attachTo` and `resetFromServerAndResyncWithPeers` against an editable that
reports what the browser would fetch, `updateValue` against a record stand-in
that reports what would be stored, `_commitChanges` on its urgent path to count
the writes, and the preamble against a fake `<img>`.

Captured 2026-09-28 the same way, for the `/@` links of issue #211, and
re-derived on 2026-09-30 from the pinned `.deb` (`ODOO_DEB_VERSION`
18.0.20260930) through Odoo's own serve path -- `transpile_javascript()` then
`rjsmin.jsmin()` -- which reproduces both excerpts byte for byte, so the
capture is current for the Odoo this image pins:

| File | Bundle | What it holds |
|---|---|---|
| `website_frontend_to_backend_edit.js` | `web.assets_frontend_minimal` | `redirect.js`'s whole `DOMContentLoaded` listener, which builds the "Edit this content" button's `href` and the two `window.location.replace` addresses beside it |
| `website_link_popover_preview.js` | `website.assets_wysiwyg` | `LinkPopoverWidget._onPreviewLinkClick`, the website editor's "open this link in the backend" handler |

Measured 2026-09-30 across the fourteen bundles the control group serves on
that route:

| Pattern | Bundles that carry it, once each | Bundles that carry it zero times |
|---|---|---|
| ``currentUrl.pathname=`/@`` | `web.assets_frontend_minimal`, `web.assets_frontend`, `website.assets_wysiwyg` | the eleven others below |
| `!currentUrl.pathname.startsWith('/@/')` | `website.assets_wysiwyg` | the eleven others, plus `web.assets_frontend_minimal` and `web.assets_frontend` |

The eleven others are `web.assets_backend`, `web.assets_backend_lazy`,
`web.assets_frontend_lazy`, `web.assets_web`, `web.assets_web_print`,
`web.report_assets_common`, `web_editor.assets_wysiwyg`,
`web_editor.assets_media_dialog`, `website.assets_editor`,
`mass_mailing.assets_wysiwyg` and `im_livechat.assets_embed_external`.
`web.assets_frontend` carries the builder because
`web.assets_frontend_minimal` is part of it; `web.assets_frontend_lazy`
removes `redirect.js` again and so carries neither pattern. The two excerpts
are byte-identical wherever they occur, so each is captured from one bundle
and stands for the others -- which is what lets a single `sub_filter_once off`
rule serve all three sites.

Two other `/@` occurrences in those bundles are **not** link builders and no
rule touches them: `web.assets_backend`, `web.assets_web` and
`web.assets_web_print` carry `_isTopWindowURL`'s `pathname.startsWith('/@/')`,
a classifier for the website editor's iframe rather than a URL being built,
and several bundles carry an `@mediapipe` CDN path. Odoo's two server-side
`f'/@{action["url"]}'` builders (`website_sale`'s invoice and sale-order
actions) produce a canonical `/@/...` that reaches `browser.location.assign`
and is prefixed once by the issue #174 rule above.

The first excerpt is the whole listener and the second the whole method,
because the tests execute them: the listener against a document whose
`.o_frontend_to_backend_edit_btn` is an anchor with a real `href` accessor --
so the Runtime shim's own wrapper decides the address -- and the method
against a link popover driven with one target.

Derived 2026-10-01 from the pinned `.deb` (`ODOO_DEB_VERSION`
18.0.20260930) through Odoo's own serve path, for the readonly html field of
issue #237:

| File | Bundle | What it holds |
|---|---|---|
| `html_viewer_iframe_content.js` | `web.assets_backend` | `HtmlViewer.updateIframeContent`, the whole method — the render site of the `hasFullHtml`/`cssAssetId` path, which picks `documentElement` or `#iframe_target` and then assigns the value to `innerHTML` |
| `html_viewer_readonly_template.js` | `web.assets_backend` | the whole `registerTemplate("html_editor.HtmlViewer", …)` call the xml bundle appends — the render site of the plain path, `t-out="state.value"` on the `o_readonly` div |

| Pattern | Bundles that carry it, once each | Bundles that carry it zero times |
|---|---|---|
| `iframeTarget.innerHTML=content;` | `web.assets_backend`, `web.assets_web`, `web.assets_web_print`, `project.webclient` | the twelve others of #210's table |
| `<div t-ref="readonlyContent" class="o_readonly" t-out="state.value"/>` | the same four | the same twelve |

Both live in `html_editor/static/src/fields/html_viewer.{js,xml}`, and
`html_editor/static/src/**/*` is named by exactly two manifests:
`html_editor`'s own, in `web.assets_backend` (so `web.assets_web` and
`web.assets_web_print` carry it by inclusion), and `project`'s, in
`project.webclient` — the bundle `project_sharing_project_task_templates.xml`
calls for the project-sharing client, where a shared user's task description
is readonly. That fourth bundle is wanted: it is the same escape on a portal
screen. The twelve others #210's table lists carry neither pattern, because
neither file is a member of any of them.

**How each was counted.** Both patterns were counted in the served bytes of
every `*/static/src/**/*.{js,xml}` file in the pinned package, reproducing
`addons/base/models/assetsbundle.py`: for JavaScript,
`rjsmin(transpile_javascript(url, source))`; for a template, lxml's
`XMLAsset._fetch_content` unwrap followed by `generate_xml_bundle`'s
`etree.tostring` inside `registerTemplate(name, path, template)`. A template
is therefore served **unminified**, through the same Ingress asset location as
the code, and reachable by an exact-expression rewrite — the same property the
snippet-thumbnail rule of #170 uses.

Both counts are one per bundle, and the anchors are longer than they look for
measured reasons. `t-out="state.value"` alone occurs **twice** in
`web.assets_backend`: the viewer's div and `web.MonetaryField`'s ghost value
(`web/static/src/views/fields/monetary/monetary_field.xml`), so the rule
carries the whole `<div>`. The attributes in it are single-spaced and the tag
ends `"/>` although the source file has two spaces and a space before the
slash: `etree.tostring` normalises both, which is why the pattern has to come
from the serve path and not from the file. `iframeTarget.innerHTML` alone
occurs three more times, all in the legacy `web_editor`'s html field
(`iframeTarget.innerHTML!==this.props.record.data[this.props.name]`, the
assignment beside it, and `iframeTarget.innerHTML=value;`) — none of them is
`=content;`, and that editor is ADR 0004's own open item.

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
