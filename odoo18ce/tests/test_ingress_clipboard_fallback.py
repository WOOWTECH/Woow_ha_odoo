#!/usr/bin/env python3
"""Contracts for the Ingress runtime shim's clipboard fallback (issue #60).

Opening Home Assistant over plain http on the LAN is a supported usage. That
page is not a secure context, so ``navigator.clipboard`` does not exist inside
the Ingress iframe and every Odoo copy button throws ``TypeError`` on
``writeText``. The shim must supply a ``writeText`` backed by
``document.execCommand("copy")`` in that case, and must leave a real
``navigator.clipboard`` alone.

The whole shim is executed in a node ``vm`` context against a minimal DOM
stand-in, so the contract covers the shim as shipped rather than an excerpt.
"""
import json
import subprocess

from test_ingress_router_rewrite import TEMPLATE, runtime_shim

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
  // The rest of the shim still ran after the clipboard block.
  {
    const { context } = makeContext({ execCommand: () => true });
    assert.equal(context.window.__INGRESS_PATH__, P);
    assert.equal(typeof context.window.fetch, "function");
    assert.notEqual(context.window.fetch.toString(), "fetch() {}", "path shim must have wrapped fetch");
  }
})().catch((error) => { console.error(error); process.exit(1); });
"""


def shim_javascript() -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    shim = runtime_shim(template)
    return shim.replace("$safe_ingress_path", "/api/hassio_ingress/token").replace(
        "%%INGRESS_CACHE_VERSION%%", "V"
    )


def main(node: str = "node") -> None:
    result = subprocess.run(
        [node, "-e", HARNESS, json.dumps(shim_javascript())],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


if __name__ == "__main__":
    main()


def test_ingress_clipboard_fallback_contracts() -> None:
    from conftest import require_tool

    main(require_tool("node"))
