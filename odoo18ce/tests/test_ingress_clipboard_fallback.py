#!/usr/bin/env python3
"""Contracts for the Ingress runtime shim's clipboard fallback (issue #60).

Opening Home Assistant over plain http on the LAN is a supported usage. That
page is not a secure context, so ``navigator.clipboard`` does not exist inside
the Ingress iframe and every Odoo copy button throws ``TypeError`` on
``writeText``. The shim must supply a ``writeText`` backed by
``document.execCommand("copy")`` in that case, and must leave a real
``navigator.clipboard`` alone.

The clipboard shim lives in its own nginx map, ``$ingress_clipboard_shim``,
spliced into ``$ingress_runtime_shim`` by variable reference, because nginx
reads each quoted parameter into a 4096-byte buffer and the URL shim alone is
close to that limit. Both scripts are executed here, in injection order, in a
node ``vm`` context against a minimal DOM stand-in, so the contract covers the
shim as shipped rather than an excerpt.
"""
import json
import re
import subprocess

from test_ingress_router_rewrite import TEMPLATE, runtime_shim

CLIPBOARD_MAP = "map $upstream_http_content_type $ingress_clipboard_shim {"
RUNTIME_MAP = "map $upstream_http_content_type $ingress_runtime_shim {"
# ngx_conf_read_token() reports "too long parameter" once a single parameter
# fills NGX_CONF_BUFFER, so a quoted value must stay strictly below it.
NGX_CONF_BUFFER = 4096

HARNESS = r"""
const assert = require("node:assert/strict");
const vm = require("node:vm");
const shim = JSON.parse(process.argv[1]);
const P = "/api/hassio_ingress/token";

function makeContext(options) {
  const execCalls = [];
  const bodyChildren = [];
  const body = {
    appendChild(el) { bodyChildren.push(el); el.parentNode = body; return el; },
    removeChild(el) {
      const index = bodyChildren.indexOf(el);
      assert.notEqual(index, -1, "removeChild of an element that is not attached");
      bodyChildren.splice(index, 1);
      el.parentNode = null;
      return el;
    },
  };
  const document = {
    body,
    documentElement: body,
    createElement(tag) {
      return {
        tagName: tag.toUpperCase(),
        value: "",
        style: {},
        attributes: {},
        parentNode: null,
        selected: false,
        setAttribute(name, value) { this.attributes[name] = String(value); },
        select() { this.selected = true; },
        setSelectionRange() {},
        focus() {},
      };
    },
    execCommand(command) {
      execCalls.push({
        command,
        attached: bodyChildren.map((el) => ({ tag: el.tagName, value: el.value, selected: el.selected })),
      });
      return options.execCommand();
    },
  };
  const navigator = { serviceWorker: undefined };
  if (options.clipboard) navigator.clipboard = options.clipboard;
  function XMLHttpRequest() {}
  XMLHttpRequest.prototype.open = function () {};
  function History() {}
  History.prototype.pushState = function () {};
  History.prototype.replaceState = function () {};
  function Element() {}
  Element.prototype.setAttribute = function () {};
  function WebSocket() {}
  const context = {
    document,
    navigator,
    location: { href: "http://ha.example:8123" + P + "/odoo", origin: "http://ha.example:8123", host: "ha.example:8123", reload() {} },
    sessionStorage: { getItem() { return null; }, setItem() {} },
    fetch() {},
    open() {},
    XMLHttpRequest,
    History,
    Element,
    WebSocket,
    URL,
    Request: function () {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(shim, context, { filename: "ingress-runtime-shim.js" });
  return { context, execCalls, bodyChildren };
}

(async () => {
  // Absent clipboard: writeText resolves through execCommand("copy") within
  // the caller's stack (user-gesture requirement) and the textarea is gone.
  {
    const { context, execCalls, bodyChildren } = makeContext({ execCommand: () => true });
    assert.equal(typeof context.navigator.clipboard, "object");
    assert.equal(typeof context.navigator.clipboard.writeText, "function");
    assert.equal(context.navigator.clipboard.write, undefined, "write() must stay absent so Odoo keeps its own catch");
    const pending = context.navigator.clipboard.writeText("https://ha.example/chat/2/abc");
    assert.equal(execCalls.length, 1, "execCommand must run synchronously inside writeText");
    assert.equal(execCalls[0].command, "copy");
    assert.deepEqual(execCalls[0].attached, [{ tag: "TEXTAREA", value: "https://ha.example/chat/2/abc", selected: true }]);
    assert.equal(await pending, undefined);
    assert.deepEqual(bodyChildren, [], "temporary textarea must be removed");
  }
  // Present clipboard: same reference, untouched.
  {
    const original = { writeText() { return Promise.resolve(); } };
    const { context, execCalls } = makeContext({ execCommand: () => true, clipboard: original });
    assert.equal(context.navigator.clipboard, original);
    assert.equal(context.navigator.clipboard.writeText, original.writeText);
    await context.navigator.clipboard.writeText("x");
    assert.deepEqual(execCalls, []);
  }
  // execCommand returns false: reject, textarea removed.
  {
    const { context, execCalls, bodyChildren } = makeContext({ execCommand: () => false });
    await assert.rejects(context.navigator.clipboard.writeText("x"));
    assert.equal(execCalls.length, 1);
    assert.deepEqual(bodyChildren, []);
  }
  // execCommand throws: reject, textarea removed.
  {
    const { context, bodyChildren } = makeContext({ execCommand: () => { throw new Error("blocked"); } });
    await assert.rejects(context.navigator.clipboard.writeText("x"));
    assert.deepEqual(bodyChildren, []);
  }
  // The URL shim still ran after the clipboard script.
  {
    const { context } = makeContext({ execCommand: () => true });
    assert.equal(context.window.__INGRESS_PATH__, P);
    assert.equal(typeof context.window.fetch, "function");
    assert.notEqual(context.window.fetch.toString(), "fetch() {}", "path shim must have wrapped fetch");
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def map_block(template: str, header: str) -> str:
    start = template.index(header)
    return template[start:template.index("\n    }", start)]


def clipboard_shim(template: str) -> str:
    """Return the clipboard script declared in its own map, injected for every value."""
    block = map_block(template, CLIPBOARD_MAP)
    match = re.search(r"default '<script>(.*?)</script>';", block, re.S)
    assert match, "clipboard shim not found in its map"
    assert "$" not in match.group(1), "clipboard shim must not reference nginx variables"
    return match.group(1)


def assert_injection_order(template: str) -> None:
    """The clipboard script is spliced in front of the URL shim, under its text/html gate."""
    block = map_block(template, RUNTIME_MAP)
    assert "'$ingress_clipboard_shim<script>" in block, (
        "the runtime shim map must splice $ingress_clipboard_shim in by variable reference"
    )
    assert template.count("$ingress_clipboard_shim") == 2, (
        "the clipboard shim must be injected only through $ingress_runtime_shim"
    )


def shipped_shim(template: str) -> str:
    return "\n".join(
        script.replace("$safe_ingress_path", "/api/hassio_ingress/token").replace(
            "%%INGRESS_CACHE_VERSION%%", "V"
        )
        for script in (clipboard_shim(template), runtime_shim(template))
    )


def assert_quoted_parameters_fit(template: str) -> None:
    """Every single-quoted nginx parameter must fit the config token buffer.

    The rendered file is never longer than the template: each %%PLACEHOLDER%%
    becomes a shorter add-on value, and $variables stay as written.
    """
    for number, line in enumerate(template.splitlines(), start=1):
        for value in re.findall(r"'([^']*)'", line):
            size = len(value.encode("utf-8"))
            assert size < NGX_CONF_BUFFER, (
                f"nginx.conf.template:{number}: quoted parameter is {size} bytes; "
                f"nginx rejects a parameter of {NGX_CONF_BUFFER} bytes or more "
                "('too long parameter'). Move the addition into its own map and "
                "splice it in by variable reference, as $ingress_clipboard_shim is."
            )


def main(node: str = "node") -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    assert_injection_order(template)
    assert_quoted_parameters_fit(template)
    result = subprocess.run(
        [node, "-e", HARNESS, json.dumps(shipped_shim(template))],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


if __name__ == "__main__":
    main()


def test_ingress_shim_quoted_parameters_fit_nginx_token_buffer() -> None:
    assert_quoted_parameters_fit(TEMPLATE.read_text(encoding="utf-8"))


def test_ingress_clipboard_fallback_contracts() -> None:
    from conftest import require_tool

    main(require_tool("node"))
