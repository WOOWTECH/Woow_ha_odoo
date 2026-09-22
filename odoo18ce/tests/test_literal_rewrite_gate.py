#!/usr/bin/env python3
"""Static-tier contracts for the Literal rewrite gate (issue #58, ADR 0004).

The gate's four pure stages run here on fixed string fixtures: extracting
root-relative literals from a bundle, classifying each by how the bundle
consumes it, parsing the prefixes the nginx template's Literal rewrite covers,
and matching approved exceptions. No network and no live Odoo.
"""
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import require_tool

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "rootfs/usr/local/lib/literal_rewrite_gate.py"
TEMPLATE = (ROOT / "rootfs/etc/nginx/nginx.conf.template").read_text(encoding="utf-8")
EXCEPTIONS_FILE = ROOT / "rootfs/usr/local/lib/literal_rewrite_exceptions.yaml"


def load_gate():
    spec = importlib.util.spec_from_file_location("literal_rewrite_gate", LIB)
    module = importlib.util.module_from_spec(spec)
    # The module annotates its dataclasses lazily, and dataclasses resolves
    # those annotations through sys.modules, so it is registered first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The fixtures below are built from the module, so it is loaded at import
# time rather than through a fixture.
gate = load_gate()

# One bundle that exercises every classification branch. Written the way
# Odoo's minified bundles read: no spaces, chained member access, template
# strings next to plain ones.
BUNDLE = (
    'rpc("/discuss/channel/notify",{id:1});'
    "loadJS('/html_editor/static/lib/x.js');"
    "const url=`/web_editor/image/${id}`;"
    'location.assign("/forum");'
    "redirect('/livechat/start');"
    'browser.location.pathname.startsWith("/scoped_app")&&run();'
    '["/web","/odoo"].includes(url.pathname)||x;'
    'rpc("/forum/x");'
)

CSS = (
    ".a{background:url(/web/static/img/a.png)}"
    ".b{background:url(\"/web_editor/img/b.png\")}"
    ".c{background:url('/survey/static/c.png')}"
)

RULES = gate.rewrite_rules(TEMPLATE)
EXPECTED_PREFIXES = {
    "/web/", "/website/", "/mail/", "/calendar/", "/base_setup/", "/my/", "/report/", "/odoo",
    # added after the gate's first full-application run (issue #58)
    "/shop/", "/payment/", "/contactus",
}


# --- extraction -----------------------------------------------------------

def test_extracts_every_quote_variant_with_the_first_segment_as_prefix():
    counts = gate.extract_prefixes(BUNDLE)
    assert counts["/discuss/"] == 1
    assert counts["/html_editor/"] == 1
    assert counts["/web_editor/"] == 1
    assert counts["/forum"] == 1
    assert counts["/forum/"] == 1
    assert counts["/livechat/"] == 1


def test_a_bare_segment_and_a_slashed_segment_are_distinct_prefixes():
    counts = gate.extract_prefixes(BUNDLE)
    assert counts["/web"] == 1  # `"/web"` in the includes() array
    assert counts["/odoo"] == 1
    assert "/web/" not in counts


def test_extracts_css_url_literals_quoted_or_not():
    counts = gate.extract_prefixes(CSS)
    assert counts == {"/web/": 1, "/web_editor/": 1, "/survey/": 1}


def test_ignores_protocol_relative_and_non_path_strings():
    text = 'a="//cdn.example/x";b="/";c=" /web/x";d=x/2/y;'
    assert gate.extract_prefixes(text) == {}


# --- classification -------------------------------------------------------

@pytest.mark.parametrize("prefix,level", [
    ("/forum", "FAIL"),        # location.assign("/forum")
    ("/livechat/", "FAIL"),    # redirect('/livechat/start')
    ("/scoped_app", "WARN"),   # pathname.startsWith("/scoped_app")
    ("/web", "WARN"),          # ["/web","/odoo"].includes(url.pathname)
    ("/discuss/", "INFO"),     # rpc("/discuss/...")
    ("/html_editor/", "INFO"), # loadJS('/html_editor/...')
    ("/web_editor/", "INFO"),  # template string
    ("/forum/", "INFO"),       # rpc("/forum/x")
])
def test_classifies_by_how_the_literal_is_consumed(prefix, level):
    assert gate.classify(BUNDLE, prefix) == level


@pytest.mark.parametrize("snippet", [
    'location.href="/forum"',
    'window.location.href = "/forum"',
    "location.pathname='/forum'",
    "location.replace(`/forum`)",
    'window.location="/forum"',
    'location.assign("/forum")',
    "redirect('/forum')",
    # a fallback, ternary or concatenation between the operator and the literal
    'window.location.href=url||"/forum"',
    'location.href=x?"/forum":"/odoo"',
    'location.href=x?"/odoo":"/forum"',
    'location.assign(base+"/forum")',
    'redirect(next??"/forum")',
])
def test_whole_page_navigations_are_fail(snippet):
    assert gate.classify(snippet, "/forum") == "FAIL"


@pytest.mark.parametrize("snippet", [
    'allocation="/forum"',                    # not the location object
    'geolocation.assign("/forum")',
    'location.href=a;rpc("/forum")',          # a statement boundary in between
])
def test_navigation_lookalikes_are_not_fail(snippet):
    assert gate.classify(snippet, "/forum") != "FAIL"


@pytest.mark.parametrize("snippet", [
    'location.pathname==="/forum"',
    '"/forum"===location.pathname',
    'location.href.includes("/forum")',
    'pathname.indexOf("/forum")===0',
    'location.pathname!=="/forum"',
    'window.location.pathname==="/forum"',
    "pathname.startsWith('/forum')||other",
    'new URL(sheet.href,browser.location.origin).pathname.startsWith("/forum")',
])
def test_path_comparisons_are_warn(snippet):
    assert gate.classify(snippet, "/forum") == "WARN"


def test_a_long_literal_on_the_left_of_a_comparison_is_still_seen():
    assert gate.classify('"/forum/some/long/path"===location.pathname', "/forum/") == "WARN"
    assert gate.classify('["/forum/a","/forum/b"].includes(location.pathname)', "/forum/") == "WARN"


@pytest.mark.parametrize("snippet", [
    'rpc("/forum")',
    'fetch("/forum")',
    'redirectUrl:"/forum"',
    'name==="/forum"',          # a comparison, but not against the location
    'x.startsWith("/forum")',   # same
    # the location is in the same statement, but the comparison is against
    # an attachment field (seen in the html_editor bundle)
    'new URL(a,window.location.origin);if(attachment.image_src.startsWith("/forum"))',
    '.a{background:url("/forum")}',
])
def test_everything_else_is_info(snippet):
    assert gate.classify(snippet, "/forum") == "INFO"


def test_a_prefix_takes_its_highest_level_across_the_bundle():
    text = 'rpc("/forum/x");location.assign("/forum/y");'
    assert gate.classify(text, "/forum/") == "FAIL"


def test_css_url_findings_are_marked_as_css():
    findings = gate.scan_bundle(CSS)
    assert {finding.context for finding in findings} == {"css_url"}
    assert {finding.quote for finding in findings} == {"", '"', "'"}


# --- nginx rules ----------------------------------------------------------

def test_parses_the_current_prefixes_from_the_template():
    assert gate.rewrite_prefixes(TEMPLATE) == EXPECTED_PREFIXES


def test_the_batch_findings_are_rewritten_in_every_quote_variant():
    for prefix in ("/shop/", "/payment/", "/contactus"):
        assert RULES[prefix] == frozenset({'"', "'", "`"}), prefix


def test_rules_record_the_quote_variants_each_prefix_is_rewritten_in():
    assert RULES["/web/"] == frozenset({'"', "'", "`"})
    assert RULES["/odoo"] == frozenset({'"', "'", "`"})
    assert RULES["/report/"] == frozenset({'"'})
    assert RULES[gate.CSS_URL_RULE] == frozenset({"", '"', "'"})


def test_rules_come_only_from_the_ingress_asset_location():
    # The Ingress HTML location has `'`/web/webclient/'` and the public
    # listener has no sub_filter at all; neither may leak into the rule set.
    assert "/web/webclient/" not in RULES
    public_rule = "sub_filter '\"/forum/' '\"$safe_ingress_path/forum/';"
    polluted = TEMPLATE.replace(
        "listen 8069 default_server;",
        "listen 8069 default_server;\n        " + public_rule,
        1,
    )
    assert "/forum/" not in gate.rewrite_prefixes(polluted)


def test_adding_a_rule_to_the_template_needs_no_script_change():
    added = TEMPLATE.replace(
        "sub_filter '\"/report/' '\"$safe_ingress_path/report/';",
        "sub_filter '\"/report/' '\"$safe_ingress_path/report/';\n"
        "            sub_filter '\"/forum/' '\"$safe_ingress_path/forum/';",
        1,
    )
    assert gate.rewrite_prefixes(added) == EXPECTED_PREFIXES | {"/forum/"}


def test_the_asset_block_is_found_however_the_template_is_indented():
    block = gate.ingress_assets_block(TEMPLATE)
    assert block.startswith("location ^~ /web/assets/ {")
    assert "location / {" not in block
    reindented = "\n".join(line[4:] if line.startswith("    ") else line for line in TEMPLATE.splitlines())
    assert gate.rewrite_prefixes(reindented) == EXPECTED_PREFIXES
    assert "/web/webclient/" not in gate.rewrite_rules(reindented)


def test_exact_expression_patches_are_not_prefix_rules():
    assert not any(":" in prefix or "(" in prefix for prefix in RULES if prefix != gate.CSS_URL_RULE)


# --- coverage -------------------------------------------------------------

def test_a_bare_rule_covers_the_slashed_literal_but_not_the_reverse():
    odoo = gate.scan_bundle('location.assign("/odoo/discuss")')[0]
    assert gate.is_covered(odoo, RULES)
    web = gate.scan_bundle('location.assign("/web")')[0]
    assert not gate.is_covered(web, RULES)  # rule is "/web/", literal is "/web"


def test_coverage_respects_the_quote_variant():
    double = gate.scan_bundle('location.assign("/report/x")')[0]
    single = gate.scan_bundle("location.assign('/report/x')")[0]
    assert gate.is_covered(double, RULES)
    assert not gate.is_covered(single, RULES)


def test_css_url_literals_are_covered_by_the_generic_url_rule():
    for finding in gate.scan_bundle(CSS):
        assert gate.is_covered(finding, RULES), finding


# --- generated include ----------------------------------------------------

# website_sale's redirect to the cart, the shape that first made /shop/ a
# Shipped rewrite. With no Shipped rules in play it is what the Rewrite scan
# would generate for it.
FAIL_BUNDLE = 'location.assign("/shop/cart")'
GENERATED_FOR_SHOP = (
    'sub_filter \'"/shop/\' \'"$safe_ingress_path/shop/\';\n'
    'sub_filter "\'/shop/" "\'$safe_ingress_path/shop/";\n'
    'sub_filter \'`/shop/\' \'`$safe_ingress_path/shop/\';\n'
)


def test_generate_include_writes_three_quote_variants_per_fail_prefix():
    assert gate.generate_include(gate.scan_bundle(FAIL_BUNDLE), {}, set()) == GENERATED_FOR_SHOP


@pytest.mark.parametrize("bundle", [
    'browser.location.pathname.startsWith("/scoped_app")',  # WARN
    'rpc("/discuss/channel/notify",{id:1});',               # INFO
    ".a{background:url(/survey/static/c.png)}",             # INFO, and CSS
])
def test_generate_include_covers_navigations_only(bundle):
    assert gate.generate_include(gate.scan_bundle(bundle), {}, set()) == ""


def test_generate_include_never_repeats_a_prefix_the_template_rewrites():
    bundle = (
        'location.assign("/shop/cart");'       # a slashed Shipped rule
        'location.assign("/odoo/discuss");'    # a bare Shipped rule, slashed literal
        'location.replace("/web/login");'
    )
    assert gate.generate_include(gate.scan_bundle(bundle), RULES, set()) == ""


def test_generate_include_skips_a_registered_exception():
    findings = gate.scan_bundle(FAIL_BUNDLE)
    assert gate.generate_include(findings, {}, {("/shop/", "FAIL")}) == ""
    # An exception excuses exactly one level, as it does for the gate.
    assert gate.generate_include(findings, {}, {("/shop/", "WARN")}) == GENERATED_FOR_SHOP


def test_generate_include_is_byte_stable_for_the_same_input():
    findings = gate.scan_bundle(
        'location.assign("/forum");redirect("/livechat/start");location.assign("/forum");'
    )
    text = gate.generate_include(findings, RULES, set())
    assert text.count("sub_filter") == 6  # /forum and /livechat/, three variants each
    assert gate.generate_include(list(reversed(findings)), RULES, set()) == text
    assert gate.generate_include(findings + findings, RULES, set()) == text


def _wait_for_socket(process: subprocess.Popen, socket: Path) -> None:
    for _ in range(100):
        if socket.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"nginx harness exited: {stdout}{stderr}")
        time.sleep(0.02)
    raise AssertionError("nginx harness socket did not become ready")


def test_nginx_rewrites_a_bundle_through_a_generated_include(tmp_path):
    """A real nginx loading a generated file prefixes the navigation literal."""
    nginx = require_tool("nginx")
    curl = require_tool("curl")
    ingress_prefix = "/api/hassio_ingress/static-test-token"

    include = tmp_path / "generated-rewrites.conf"
    include.write_text(gate.generate_include(gate.scan_bundle(FAIL_BUNDLE), {}, set()), encoding="utf-8")
    bundle = tmp_path / "bundle.js"
    bundle.write_text(FAIL_BUNDLE, encoding="utf-8")
    upstream, gateway = tmp_path / "upstream.sock", tmp_path / "gateway.sock"
    config = tmp_path / "nginx.conf"
    config.write_text(
        "\n".join((
            "daemon off;",
            "master_process off;",
            f"pid {tmp_path / 'nginx.pid'};",
            f"error_log {tmp_path / 'error.log'} notice;",
            "events {}",
            "http {",
            "  access_log off;",
            # The stub upstream stands in for Odoo serving an asset bundle.
            f"  server {{ listen unix:{upstream};",
            f"    location = /bundle.js {{ default_type application/javascript; alias {bundle}; }}",
            "  }",
            # The gateway is the Ingress asset location in miniature: the same
            # sub_filter setup, with the generated file as its only rules.
            f"  server {{ listen unix:{gateway};",
            "    location = /bundle.js {",
            f"      set $safe_ingress_path {ingress_prefix};",
            f"      proxy_pass http://unix:{upstream}:/bundle.js;",
            '      proxy_set_header Accept-Encoding "";',
            "      sub_filter_once off;",
            "      sub_filter_types application/javascript;",
            f"      include {include};",
            "    }",
            "  }",
            "}",
        )),
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [nginx, "-p", str(tmp_path), "-c", str(config)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _wait_for_socket(process, gateway)
        response = subprocess.run(
            [curl, "--fail", "--silent", "--unix-socket", str(gateway), "http://localhost/bundle.js"],
            check=True, capture_output=True, text=True,
        ).stdout
        assert response == f'location.assign("{ingress_prefix}/shop/cart")'
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


# --- exceptions -----------------------------------------------------------

def test_load_exceptions_returns_prefix_level_pairs():
    text = (
        "- prefix: /scoped_app\n"
        "  level: WARN\n"
        "  reason: the router compares the stripped path\n"
        "- prefix: /forum\n"
        "  level: FAIL\n"
        "  reason: tested by hand\n"
    )
    assert gate.load_exceptions(text) == {("/scoped_app", "WARN"), ("/forum", "FAIL")}


@pytest.mark.parametrize("text", [
    "- prefix: /scoped_app\n  level: WARN\n",
    "- prefix: /scoped_app\n  level: WARN\n  reason: ''\n",
    "- prefix: /scoped_app\n  reason: why\n",
    "- level: WARN\n  reason: why\n",
    "- prefix: /scoped_app\n  level: MAYBE\n  reason: why\n",
    "- prefix: scoped_app\n  level: WARN\n  reason: why\n",
])
def test_load_exceptions_rejects_incomplete_entries(text):
    with pytest.raises(ValueError):
        gate.load_exceptions(text)


def test_load_exceptions_accepts_an_empty_file():
    assert gate.load_exceptions("") == set()
    assert gate.load_exceptions("# nothing yet\n") == set()


def test_checked_in_exceptions_file_registers_scoped_app():
    exceptions = gate.load_exceptions(EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    assert ("/scoped_app", "WARN") in exceptions


# --- evaluation and exit code ---------------------------------------------

def test_unlisted_navigation_fails_the_gate():
    report = gate.evaluate({"a.min.js": 'location.assign("/forum")'}, RULES, set())
    assert report.exit_code == 1
    assert [f.prefix for f in report.bundles["a.min.js"].unregistered_failures] == ["/forum"]


def test_the_same_prefix_used_only_through_rpc_passes():
    report = gate.evaluate({"a.min.js": 'rpc("/forum/x")'}, RULES, set())
    assert report.exit_code == 0
    assert report.bundles["a.min.js"].levels["/forum/"] == "INFO"


def test_a_registered_exception_is_reported_as_a_hit_and_does_not_fail():
    bundles = {"a.min.js": 'location.assign("/forum");pathname.startsWith("/scoped_app")'}
    report = gate.evaluate(bundles, RULES, {("/forum", "FAIL"), ("/scoped_app", "WARN")})
    assert report.exit_code == 0
    hits = report.bundles["a.min.js"].exception_hits
    assert {(f.prefix, f.level) for f in hits} == {("/forum", "FAIL"), ("/scoped_app", "WARN")}


def test_an_exception_at_a_lower_level_does_not_excuse_a_failure():
    report = gate.evaluate({"a.min.js": 'location.assign("/forum")'}, RULES, {("/forum", "WARN")})
    assert report.exit_code == 1


def test_covered_prefixes_are_not_reported():
    report = gate.evaluate({"a.min.js": 'location.assign("/odoo/x");rpc("/web/y")'}, RULES, set())
    assert report.exit_code == 0
    assert report.bundles["a.min.js"].levels == {}


def test_warn_and_info_never_fail():
    bundles = {"a.min.js": BUNDLE.replace('location.assign("/forum");', "").replace("redirect('/livechat/start');", "")}
    report = gate.evaluate(bundles, RULES, set())
    assert report.exit_code == 0
    assert report.bundles["a.min.js"].levels["/scoped_app"] == "WARN"
    assert report.bundles["a.min.js"].levels["/discuss/"] == "INFO"


# --- output ---------------------------------------------------------------

def test_report_lists_levels_and_exception_hits_per_bundle():
    bundles = {"web.assets_web.min.js": BUNDLE}
    report = gate.evaluate(bundles, RULES, {("/scoped_app", "WARN")})
    text = gate.format_report(report)
    assert "web.assets_web.min.js" in text
    assert "FAIL" in text and "/forum" in text and "/livechat/" in text
    assert "WARN" in text and "/web" in text
    assert "INFO" in text and "/discuss/" in text and "/html_editor/" in text
    assert "exception" in text and "/scoped_app" in text


def test_report_masks_ingress_tokens():
    bundles = {"/api/hassio_ingress/secret-token/web/assets/a.min.js": 'location.assign("/api/hassio_ingress/secret-token/forum")'}
    report = gate.evaluate(bundles, RULES, set())
    text = gate.format_report(report)
    assert "secret-token" not in text
    assert "<redacted>" in text


def test_mask_redacts_every_token_shape():
    assert gate.mask("api/hassio_ingress/abc/odoo") == "api/hassio_ingress/<redacted>/odoo"
    assert gate.mask("https://ha.example/api/hassio_ingress/abc?x=1") == "https://ha.example/api/hassio_ingress/<redacted>?x=1"
    assert gate.mask("no token here") == "no token here"
