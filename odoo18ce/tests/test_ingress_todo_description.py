#!/usr/bin/env python3
"""Contracts for the HTML editor's content round trip (issue #210).

Under Ingress the To-do form showed two broken pictures. The onboarding to-do
Odoo creates for every user copies ``project_todo``'s ``todo_user_onboarding``
template into ``project.task.description``, and that HTML carries
``<img src="/project_todo/static/img/todo_access.png">`` and one more like it.
The HTML editor field inserts the stored value as markup, the browser resolved
both root-relative URLs against the Home Assistant root, and Home Assistant
answered 404 -- ``route_escape=2``, ``http_4xx_5xx=2``, ``console_error=2``,
with the Public origin clean (#163's ``open`` run, add-on 0.4.5, `odoo_parity`).

Markup insertion is the way ADR 0004 leaves uncovered *because of this very
field*: the editor loads a value and saves the same value back, so a Runtime
shim hook on ``innerHTML`` would write the token-bearing Ingress prefix into
the database. The value arrives on ``/web/dataset/call_kw``, which the
action-help postscript names as the response it refuses to rewrite. So the fix
follows the rule the snippet-thumbnail postscript states -- rewrite where the
URL is *rendered*, leave the delivered value alone -- and adds the half that
rule did not need there: the prefix comes **off** again at the one place
content leaves the editor.

What is pinned here:

- **The two globals.** The rendered Runtime shim publishes
  ``__WOOW_INGRESS_MARKUP_IN__`` and ``__WOOW_INGRESS_MARKUP_OUT__``,
  read-only, only when the Ingress prefix is non-empty, and ``IN`` prefixes
  through the shim's own ``path()`` -- so a fragment, a ``data:`` URL, a
  cross-origin or protocol-relative reference, an already prefixed value and a
  non-string behave exactly as they do everywhere else in the shim.
- **The shim still hooks nothing.** Publishing a helper a rewritten expression
  calls is not intercepting a property;
  ``test_ingress_injection_hooks.py`` keeps asserting Group B is absent, and
  the assertion here says the same thing from this side.
- **The rewrites match the bundle.** An unmatched ``sub_filter`` is a silent
  no-op, so each pattern is counted in bytes captured from the bundles the
  control group serves, kept under ``fixtures/bundles/``.
- **The round trip.** Both rewritten expressions are executed in node: the
  render site against an editable that reports what the browser would fetch,
  the save site against a DOM stand-in whose clone is serialised. With the
  rules the picture is requested under the prefix and the saved markup is
  root-relative; without them the first escapes and the second keeps whatever
  the shim put on.
- **Ingress only.** ``ingress_rule`` refuses a rule found outside the Ingress
  asset location, which would change what the Public origin serves.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from test_ingress_clipboard_fallback import INGRESS_PREFIX, clipboard_shim, directive_lines
from test_ingress_router_rewrite import TEMPLATE, ingress_rule, map_block, runtime_shim

FIXTURES = Path(__file__).resolve().parent / "fixtures/bundles"

MARKUP_MAP = "map $upstream_http_content_type $ingress_markup_global_shim {"
RUNTIME_MAP = "map $upstream_http_content_type $ingress_runtime_shim {"
IN_GLOBAL = "__WOOW_INGRESS_MARKUP_IN__"
OUT_GLOBAL = "__WOOW_INGRESS_MARKUP_OUT__"

# Documentation address only (RFC 2606); no real host here.
HA_ORIGIN = "http://ha.example:8123"
PAGE = HA_ORIGIN + INGRESS_PREFIX + "/odoo/action-454/5"

# The two pictures of the onboarding to-do, as `todo_user_onboarding` writes
# them into project.task.description.
TODO_PICTURES = (
    "/project_todo/static/img/todo_access.png",
    "/project_todo/static/img/convert_todo.png",
)

# Each rewrite: the fixture it was measured in, how many times the pattern
# occurs there, and the exact expression the Ingress asset location rewrites.
REWRITES = {
    "render": {
        "fixture": "html_editor_attach_content.js",
        "source": "editable.innerHTML=fixInvalidHTML(this.config.content)",
        "occurrences": 1,
    },
    "save": {
        "fixture": "html_editor_save_content.js",
        "source": (
            "getElContent(){const el=this.editable.cloneNode(true);"
            'this.resources["clean_for_save_handlers"].forEach((cb)=>cb({root:el}));'
            "return el;}"
        ),
        "occurrences": 1,
    },
}

# A DOM stand-in small enough to read and faithful in the three things these
# rewrites depend on: a deep clone, attribute selectors, and an
# `Element.prototype.setAttribute` the Runtime shim can wrap.
DOM = r"""
function makeElement(context) {
  function Element() { this.tagName = "DIV"; this.attrs = {}; this.children = []; }
  Element.prototype.setAttribute = function (name, value) { this.attrs[name] = String(value); };
  Element.prototype.getAttribute = function (name) {
    return name in this.attrs ? this.attrs[name] : null;
  };
  Element.prototype.setAttributeNS = function (ns, name, value) { this.setAttribute(name, value); };
  Element.prototype.descendants = function () {
    const out = [];
    for (const child of this.children) { out.push(child); out.push(...child.descendants()); }
    return out;
  };
  // Only the attribute-presence selector the strip uses, e.g. "[src],[href]".
  Element.prototype.querySelectorAll = function (selector) {
    const names = selector.split(",").map((part) => {
      const match = /^\s*\[([A-Za-z-]+)\]\s*$/.exec(part);
      if (!match) throw new Error("unsupported selector: " + selector);
      return match[1];
    });
    return this.descendants().filter((el) => names.some((name) => name in el.attrs));
  };
  Element.prototype.cloneNode = function (deep) {
    const copy = new Element();
    copy.tagName = this.tagName;
    copy.attrs = Object.assign({}, this.attrs);
    if (deep) copy.children = this.children.map((child) => child.cloneNode(true));
    return copy;
  };
  Object.defineProperty(Element.prototype, "markup", {
    get() {
      return this.children.map((child) => {
        const attrs = Object.keys(child.attrs)
          .map((name) => " " + name + '="' + child.attrs[name] + '"')
          .join("");
        return "<" + child.tagName.toLowerCase() + attrs + ">" + child.markup +
          "</" + child.tagName.toLowerCase() + ">";
      }).join("");
    },
  });
  context.makeNode = function (tagName, attrs) {
    const el = new Element();
    el.tagName = tagName;
    // Through the prototype, so the Runtime shim's wrapper is in the path --
    // which is how an image the media dialog inserts gets a prefix today.
    for (const name of Object.keys(attrs)) el.setAttribute(name, attrs[name]);
    return el;
  };
  return Element;
}
"""

# The rendered Runtime shim runs first in every case, so what the drivers call
# is the helper the page actually gets.
HARNESS = r"""
const assert = require("node:assert/strict");
const vm = require("node:vm");
const payload = JSON.parse(process.argv[1]);
const P = "/api/hassio_ingress/token";
const ORIGIN = "http://ha.example:8123";
const PAGE = ORIGIN + P + "/odoo/action-454/5";
__DOM__

function run(shim, program) {
  function XMLHttpRequest() {}
  XMLHttpRequest.prototype.open = function () {};
  function History() {}
  History.prototype.pushState = function () {};
  History.prototype.replaceState = function () {};
  function WebSocket() {}
  const context = {
    navigator: { serviceWorker: undefined },
    location: { href: PAGE, origin: ORIGIN, host: "ha.example:8123" },
    sessionStorage: { getItem() { return null; }, setItem() {} },
    fetch() {},
    open() {},
    XMLHttpRequest,
    History,
    WebSocket,
    URL,
    Request: function () {},
    P,
    PAGE,
    result: undefined,
  };
  context.Element = makeElement(context);
  context.document = { body: {}, documentElement: {}, activeElement: null };
  context.window = context;
  vm.createContext(context);
  if (shim) vm.runInContext(shim, context, { filename: "ingress-runtime-shim.js" });
  vm.runInContext(program, context);
  return context;
}

for (const { name, shim, program, expected } of payload) {
  // The driver builds its result inside the vm context, so its Array is not
  // this realm's; compare the values and not the prototypes.
  const value = run(shim, program).result;
  assert.equal(JSON.stringify(value), JSON.stringify(expected),
    name + ": got " + JSON.stringify(value));
}
""".replace("__DOM__", DOM)

# The render site. `fixInvalidHTML` is the identity here -- what it does to
# invalid markup is Odoo's business; what matters is that the prefix is on the
# string the editable is assigned, before anything can be fetched. The fake
# editable resolves every src the way a browser resolves it against the page.
RENDER_DRIVER = r"""
const fixInvalidHTML = (value) => value;
const isEmpty = () => false;
const createBaseContainer = () => makeNode("DIV", {});
const fillShrunkPhrasingParent = () => {};
const initElementForEdition = () => {};
const requested = [];
const editable = {
  ownerDocument: { },
  classList: { add() {} },
  style: {},
  setAttribute() {},
  replaceChildren() {},
  set innerHTML(value) {
    for (const match of String(value).matchAll(/src="([^"]*)"/g)) {
      requested.push(new URL(match[1], PAGE).href);
    }
  },
};
class Editor {
  constructor(content) {
    this.config = { content };
    this.isDestroyed = false;
    this.editable = null;
    this.document = null;
  }
__SLICE__
  preparePlugins() {}
  startPlugins() {}
}
new Editor(__CONTENT__).attachTo(editable);
result = requested;
"""

# The save site. The editable holds what the render site left plus one image
# the media dialog inserted through `setAttribute`, which the shim prefixed.
# `getContent()` is the string the field commits, so that is what is read.
SAVE_DRIVER = r"""
const editable = makeNode("DIV", {});
editable.children = __CHILDREN__;
class Editor {
  constructor(el) {
    this.editable = el;
    this.resources = { clean_for_save_handlers: [] };
  }
__SLICE__
}
const saved = new Editor(editable).getElContent();
result = saved.markup;
"""

# Everything the two globals promise, executed against the rendered shim.
GLOBALS_HARNESS = r"""
const assert = require("node:assert/strict");
const vm = require("node:vm");
const { shim, emptyShim } = JSON.parse(process.argv[1]);
const P = "/api/hassio_ingress/token";
const ORIGIN = "http://ha.example:8123";
const PAGE = ORIGIN + P + "/odoo/action-454/5";
const PICTURE = "/project_todo/static/img/todo_access.png";
__DOM__

function run(script) {
  function XMLHttpRequest() {}
  XMLHttpRequest.prototype.open = function () {};
  function History() {}
  History.prototype.pushState = function () {};
  History.prototype.replaceState = function () {};
  function WebSocket() {}
  const fetched = [];
  const context = {
    navigator: { serviceWorker: undefined },
    location: { href: PAGE, origin: ORIGIN, host: "ha.example:8123" },
    sessionStorage: { getItem() { return null; }, setItem() {} },
    fetch(input) { fetched.push(input); return Promise.resolve(); },
    open() {},
    XMLHttpRequest,
    History,
    WebSocket,
    URL,
    Request: function () {},
  };
  context.Element = makeElement(context);
  context.document = { body: {}, documentElement: {}, activeElement: null };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(script, context, { filename: "ingress-runtime-shim.js" });
  return { context, fetched };
}

const { context, fetched } = run(shim);
const markupIn = context.__WOOW_INGRESS_MARKUP_IN__;
const markupOut = context.__WOOW_INGRESS_MARKUP_OUT__;
assert.equal(typeof markupIn, "function", "the shim must publish __WOOW_INGRESS_MARKUP_IN__");
assert.equal(typeof markupOut, "function", "the shim must publish __WOOW_INGRESS_MARKUP_OUT__");

// The onboarding to-do's own markup: both pictures, nothing else changed.
const stored = '<h1>Hey</h1><img class="img-fluid" src="' + PICTURE + '" alt="todo-access"/>';
assert.equal(
  markupIn(stored),
  '<h1>Hey</h1><img class="img-fluid" src="' + P + PICTURE + '" alt="todo-access"/>',
  "a root-relative src must come out under the prefix, with the rest of the markup untouched"
);

// It prefixes through the shim's own path(), so path()'s rules hold here.
assert.equal(markupIn('<a href="' + P + PICTURE + '">x</a>'),
  '<a href="' + P + PICTURE + '">x</a>', "an already prefixed value is unchanged");
// Only a value whose first byte is `/` is a candidate, which is the shape the
// nginx prefix rules match as well. That excludes a protocol-relative
// reference, where every other rule of the template has to be told to stop,
// and it also leaves an absolute same-origin URL alone -- Odoo writes
// root-relative URLs into record HTML, and an absolute one somebody pasted is
// unmeasured rather than fixed (see ADR 0004's postscript for this issue).
for (const untouched of [
  '<a href="#anchor">x</a>',
  '<a href="https://other.example/x">x</a>',
  '<a href="//other.example/x">x</a>',
  '<a href="' + ORIGIN + PICTURE + '">x</a>',
  '<a href="' + ORIGIN + P + PICTURE + '">x</a>',
  '<img src="data:image/png;base64,iVBOR"/>',
  '<img src="blob:' + ORIGIN + '/9f1c"/>',
  '<img src="todo_access.png"/>',
  '<img data-oe-thumbnail="' + PICTURE + '"/>',
  '<img srcset="' + PICTURE + ' 1x"/>',
  '<div style="background-image: url(' + PICTURE + ')"></div>',
]) {
  assert.equal(markupIn(untouched), untouched, "must be left alone: " + untouched);
}
for (const value of [null, undefined, 7, false]) {
  assert.equal(markupIn(value), value, "a non-string is returned as it came");
}
assert.equal(markupIn("<p>no url here</p>"), "<p>no url here</p>");
// Single-quoted attributes are the same attributes.
assert.equal(markupIn("<img src='" + PICTURE + "'/>"), "<img src='" + P + PICTURE + "'/>");
// Idempotent: the render site may run twice over the same content.
assert.equal(markupIn(markupIn(stored)), markupIn(stored), "no value may be prefixed twice");

// It is the same path() the shim's own wrappers use, not a copy of it.
context.fetch(PICTURE);
assert.deepEqual(fetched, [P + PICTURE], "fetch must prefix through the same helper");

// OUT takes the prefix off the same four attributes, in place, on a clone.
const tree = context.makeNode("DIV", {});
tree.children = [
  context.makeNode("IMG", { src: P + PICTURE }),
  context.makeNode("A", { href: ORIGIN + P + "/web/content/7" }),
  context.makeNode("FORM", { action: P + "/web/dataset/call_kw" }),
  context.makeNode("IMG", { "data-src": P + PICTURE }),
  context.makeNode("A", { href: "https://other.example/x" }),
  context.makeNode("IMG", { src: PICTURE }),
  context.makeNode("IMG", { srcset: P + PICTURE + " 1x" }),
];
assert.equal(markupOut(tree), tree, "the helper returns the root it was handed");
assert.deepEqual(tree.children.map((el) => el.attrs), [
  { src: PICTURE },
  { href: "/web/content/7" },
  { action: "/web/dataset/call_kw" },
  { "data-src": PICTURE },
  { href: "https://other.example/x" },
  { src: PICTURE },
  { srcset: P + PICTURE + " 1x" },
]);
// A value that is the prefix and nothing else is the root.
const bare = context.makeNode("DIV", {});
bare.children = [context.makeNode("A", { href: P })];
markupOut(bare);
assert.deepEqual(bare.children[0].attrs, { href: "/" });
// Anything that is not an element tree is handed straight back.
for (const value of [null, undefined, "text", 7]) {
  assert.equal(markupOut(value), value);
}

// Read-only: a bundle cannot replace a helper a rewritten expression calls.
// Assignment to a non-writable property is silent outside strict mode, which
// is how an asset bundle runs.
for (const [name, expected] of [[
  "__WOOW_INGRESS_MARKUP_IN__", markupIn], ["__WOOW_INGRESS_MARKUP_OUT__", markupOut]]) {
  try { context[name] = function () { return "owned"; }; } catch (error) {}
  assert.equal(context[name], expected, name + " must be read-only");
  try { delete context[name]; } catch (error) {}
  assert.equal(context[name], expected, name + " must be non-configurable");
}

// With no Ingress prefix the shim returns before publishing anything.
const empty = run(emptyShim).context;
assert.equal(empty.__WOOW_INGRESS_MARKUP_IN__, undefined, "no prefix, no global");
assert.equal(empty.__WOOW_INGRESS_MARKUP_OUT__, undefined, "no prefix, no global");
""".replace("__DOM__", DOM)


def template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def fixture(name: str) -> str:
    return (FIXTURES / REWRITES[name]["fixture"]).read_text(encoding="utf-8")


def rewritten(name: str) -> str:
    """The fixture as the Ingress asset location serves it."""
    rewrite = REWRITES[name]
    replacement = ingress_rule(template(), rewrite["source"], rewrite["fixture"])
    assert IN_GLOBAL in replacement or OUT_GLOBAL in replacement, (
        "the rewrite must go through a helper the Runtime shim publishes"
    )
    return fixture(name).replace(rewrite["source"], replacement)


def rendered_shim(prefix: str) -> str:
    text = template()
    return "\n".join(
        script.replace("$safe_ingress_path", prefix).replace("%%INGRESS_CACHE_VERSION%%", "V")
        for script in (clipboard_shim(text), runtime_shim(text))
    )


def node(harness: str, payload) -> None:
    from conftest import require_tool

    result = subprocess.run(
        [require_tool("node"), "-e", harness, json.dumps(payload)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def render_program(text: str, content: str) -> str:
    """The fixture's `attachTo`, driven with one stored description."""
    slice_start = text.index("attachTo(editable){")
    body = text[slice_start:].rstrip()
    return (
        RENDER_DRIVER.replace("__SLICE__", body).replace("__CONTENT__", json.dumps(content))
    )


def save_program(text: str, children: str) -> str:
    """The fixture's `getContent`/`getElContent`, driven over one editable."""
    slice_start = text.index("getContent(){")
    body = text[slice_start:].rstrip()
    return SAVE_DRIVER.replace("__SLICE__", body).replace("__CHILDREN__", children)


# --- the globals the Runtime shim publishes -----------------------------------

def test_the_runtime_shim_publishes_the_markup_helpers() -> None:
    node(GLOBALS_HARNESS, {"shim": rendered_shim(INGRESS_PREFIX), "emptyShim": rendered_shim("")})


def test_the_helpers_prefix_through_the_shims_own_path() -> None:
    """One URL helper, published rather than copied (ADR 0004)."""
    text = template()
    shim = runtime_shim(text)
    assert shim.count("var path=function(u)") == 1, "there must be exactly one URL helper"
    markup_map = map_block(text, MARKUP_MAP)
    assert "path(v)" in markup_map, (
        "the markup helper must prefix through the shim's own path(), not a second helper"
    )
    assert "A.call(" in markup_map, (
        "the strip must write through the native setAttribute the shim captured; the shim's "
        "own wrapper would put the prefix straight back on"
    )


def test_the_helpers_are_spliced_into_the_runtime_shim_and_nowhere_else() -> None:
    text = template()
    assert "$ingress_markup_global_shim" in map_block(text, RUNTIME_MAP), (
        "the Runtime shim map must splice $ingress_markup_global_shim in by variable reference"
    )
    references = [
        number
        for number, line in directive_lines(text)
        if "$ingress_markup_global_shim" in line and not line.lstrip().startswith("map ")
    ]
    assert len(references) == 1, (
        "$ingress_markup_global_shim must be referenced only inside $ingress_runtime_shim, "
        f"found it on lines {references}"
    )


def test_publishing_a_helper_is_not_hooking_the_property() -> None:
    """ADR 0004's Group B stays uncovered: the shim intercepts nothing here."""
    markup_map = map_block(template(), MARKUP_MAP)
    for hook in ("innerHTML", "outerHTML", "insertAdjacentHTML", "defineProperty(Element"):
        assert hook not in markup_map, (
            f"the markup helpers must not touch {hook}: a hook on markup insertion writes the "
            "Ingress prefix into the database, which is why ADR 0004 leaves Group B uncovered. "
            "These are functions a rewritten expression calls, nothing more."
        )


# --- the rewrites -------------------------------------------------------------

@pytest.mark.parametrize("name", REWRITES)
def test_the_rewrite_matches_the_bundle_the_expected_number_of_times(name: str) -> None:
    """A pattern that does not match is a silent no-op, so measure it."""
    rewrite = REWRITES[name]
    found = fixture(name).count(rewrite["source"])
    assert found == rewrite["occurrences"], (
        f"{name}: {rewrite['fixture']} holds {found} occurrences of {rewrite['source']!r}, "
        f"expected {rewrite['occurrences']}; re-capture the fixture and re-measure the rewrite"
    )


@pytest.mark.parametrize("name", REWRITES)
def test_every_rewrite_is_ingress_only(name: str) -> None:
    """A rule on the 8069 listener would change what the Public origin serves."""
    ingress_rule(template(), REWRITES[name]["source"], name)


def test_the_rewrites_name_nothing_route_scoped() -> None:
    """The pair is the editor's own round trip, not a rewrite of the call_kw response.

    ADR 0004 refuses to rewrite ``/web/dataset/call_kw``, which is how the HTML
    editor both loads a field and saves it. Nothing here may reach for it.
    """
    text = template()
    for forbidden in ("/web/dataset/call_kw", "project.task", "web_read"):
        offenders = [number for number, line in directive_lines(text) if forbidden in line]
        assert not offenders, (
            f"no directive may name {forbidden!r} (found on lines {offenders}): rewriting the "
            "response the HTML editor also saves through is what ADR 0004 decided against"
        )


# --- the render site ----------------------------------------------------------

STORED = (
    '<h1>Hey Administrator</h1>'
    '<img class="img-fluid d-none d-sm-block" src="%s" alt="todo-access"/>'
    '<p>Using the editor</p>'
    '<img class="img-fluid d-none d-sm-block" src="%s" alt="convert-todo"/>'
) % TODO_PICTURES


def test_the_pictures_are_fetched_from_the_home_assistant_root_without_the_rewrite() -> None:
    """The starting point: the bundle as Odoo ships it, run under Ingress."""
    node(HARNESS, [{
        "name": "render, as Odoo ships it",
        "shim": rendered_shim(INGRESS_PREFIX),
        "program": render_program(fixture("render"), STORED),
        "expected": [HA_ORIGIN + picture for picture in TODO_PICTURES],
    }])


def test_the_rewrite_fetches_the_pictures_under_the_ingress_prefix() -> None:
    node(HARNESS, [{
        "name": "render, under Ingress",
        "shim": rendered_shim(INGRESS_PREFIX),
        "program": render_program(rewritten("render"), STORED),
        "expected": [
            HA_ORIGIN + INGRESS_PREFIX + picture for picture in TODO_PICTURES
        ],
    }])


def test_without_the_globals_the_render_site_inserts_the_raw_value() -> None:
    """An Ingress page whose shim did not run must still render, not throw."""
    node(HARNESS, [{
        "name": "render, with no Runtime shim",
        "shim": "",
        "program": render_program(rewritten("render"), STORED),
        "expected": [HA_ORIGIN + picture for picture in TODO_PICTURES],
    }])


# --- the save site ------------------------------------------------------------

# What the editable holds under Ingress once the render site has run: the two
# pictures with the prefix on, plus one image the media dialog inserted through
# `setAttribute`, which the Runtime shim prefixed on the way in.
EDITED = (
    "["
    'makeNode("IMG", {src: P + %(first)s}),'
    'makeNode("IMG", {src: P + %(second)s}),'
    'makeNode("IMG", {src: "/web/image/42-abc/pasted.png"}),'
    'makeNode("A", {href: "https://odoo.example/docs"}),'
    "]"
) % {"first": json.dumps(TODO_PICTURES[0]), "second": json.dumps(TODO_PICTURES[1])}

SAVED_ROOT_RELATIVE = (
    '<img src="%s"></img><img src="%s"></img>'
    '<img src="/web/image/42-abc/pasted.png"></img>'
    '<a href="https://odoo.example/docs"></a>'
) % TODO_PICTURES

SAVED_WITH_THE_PREFIX = (
    '<img src="%(p)s%(first)s"></img><img src="%(p)s%(second)s"></img>'
    '<img src="%(p)s/web/image/42-abc/pasted.png"></img>'
    '<a href="https://odoo.example/docs"></a>'
) % {"p": INGRESS_PREFIX, "first": TODO_PICTURES[0], "second": TODO_PICTURES[1]}


def test_the_editor_saves_the_ingress_prefix_without_the_rewrite() -> None:
    """The harm ADR 0004 names: the prefix, token and all, reaching the record."""
    node(HARNESS, [{
        "name": "save, as Odoo ships it",
        "shim": rendered_shim(INGRESS_PREFIX),
        "program": save_program(fixture("save"), EDITED),
        "expected": SAVED_WITH_THE_PREFIX,
    }])


def test_the_rewrite_saves_a_root_relative_value() -> None:
    node(HARNESS, [{
        "name": "save, under Ingress",
        "shim": rendered_shim(INGRESS_PREFIX),
        "program": save_program(rewritten("save"), EDITED),
        "expected": SAVED_ROOT_RELATIVE,
    }])


# With no Runtime shim there is no `setAttribute` wrapper either, so the image
# the media dialog inserted keeps the value it was given; the two pictures still
# carry the prefix the render site put on before the shim stopped running.
SAVED_WITHOUT_THE_SHIM = (
    '<img src="%(p)s%(first)s"></img><img src="%(p)s%(second)s"></img>'
    '<img src="/web/image/42-abc/pasted.png"></img>'
    '<a href="https://odoo.example/docs"></a>'
) % {"p": INGRESS_PREFIX, "first": TODO_PICTURES[0], "second": TODO_PICTURES[1]}


def test_without_the_globals_the_save_site_returns_the_clone_unchanged() -> None:
    """An Ingress page whose shim did not run must still save, not throw."""
    node(HARNESS, [{
        "name": "save, with no Runtime shim",
        "shim": "",
        "program": save_program(rewritten("save"), EDITED),
        "expected": SAVED_WITHOUT_THE_SHIM,
    }])


def test_the_round_trip_returns_the_stored_value() -> None:
    """Render then save: what the database gets back is what it held."""
    from conftest import require_tool

    harness = r"""
const assert = require("node:assert/strict");
const vm = require("node:vm");
const shim = JSON.parse(process.argv[1]);
const P = "/api/hassio_ingress/token";
const ORIGIN = "http://ha.example:8123";
const PAGE = ORIGIN + P + "/odoo/action-454/5";
__DOM__
function XMLHttpRequest() {}
XMLHttpRequest.prototype.open = function () {};
function History() {}
History.prototype.pushState = function () {};
History.prototype.replaceState = function () {};
function WebSocket() {}
const context = {
  navigator: { serviceWorker: undefined },
  location: { href: PAGE, origin: ORIGIN, host: "ha.example:8123" },
  sessionStorage: { getItem() { return null; }, setItem() {} },
  fetch() {}, open() {}, XMLHttpRequest, History, WebSocket, URL,
  Request: function () {},
};
context.Element = makeElement(context);
context.document = { body: {}, documentElement: {}, activeElement: null };
context.window = context;
vm.createContext(context);
vm.runInContext(shim, context, { filename: "ingress-runtime-shim.js" });

const PICTURE = "/project_todo/static/img/todo_access.png";
const prefixed = context.__WOOW_INGRESS_MARKUP_IN__('<img src="' + PICTURE + '"/>');
assert.equal(prefixed, '<img src="' + P + PICTURE + '"/>');
// The editable, as the browser parsed the prefixed markup.
const editable = context.makeNode("DIV", {});
editable.children = [context.makeNode("IMG", { src: P + PICTURE })];
context.__WOOW_INGRESS_MARKUP_OUT__(editable.cloneNode(true));
const saved = context.__WOOW_INGRESS_MARKUP_OUT__(editable.cloneNode(true));
assert.equal(saved.markup, '<img src="' + PICTURE + '"></img>',
  "the value that goes back to the database must be the value it held");
""".replace("__DOM__", DOM)
    result = subprocess.run(
        [require_tool("node"), "-e", harness, json.dumps(rendered_shim(INGRESS_PREFIX))],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


# --- the fixtures -------------------------------------------------------------

def test_the_fixtures_are_the_editor_and_nothing_else() -> None:
    """Both excerpts are verbatim bundle bytes, so they must parse as one region."""
    render = fixture("render")
    assert render.startswith("attachTo(editable){")
    assert render.rstrip().endswith("this.config.onEditorReady?.();}")
    save = fixture("save")
    assert save.startswith("getContent(){return this.getElContent().innerHTML;}")
    assert re.search(r"getElContent\(\)\{const el=this\.editable\.cloneNode\(true\);", save)
