#!/usr/bin/env python3
"""Live tier: links Odoo builds in the browser carry the Canonical URL (issue #70).

Some Odoo 18 links are absolute addresses assembled in the page, from whatever
is in the address bar, for somebody outside to open. Through Ingress that
address is the Home Assistant host, and the lock on ``web.base.url`` cannot
reach them because the value never passes through the server. ADR 0006 has the
Runtime shim publish the Canonical URL and moves each link onto it with one
exact-expression Literal rewrite.

``test_ingress_browser_built_links.py`` pins those rewrites against captured
bundle bytes. This is the other half: it reads the value a person actually
sees, on a running add-on, through Ingress.

What it asserts:

- The Ingress page publishes ``window.__WOOW_CANONICAL_URL__``, and its value
  is the Canonical URL with no trailing slash.
- The Discuss invitation link shown in *Invite People* starts with that
  Canonical URL and carries no Ingress token. An unrewritten link would start
  with the Home Assistant host instead, which is the failure this exists for.
- The Public origin serves the same bundles unrewritten, so the rewrites stay
  where the Ingress listener put them.

Run it once per Home Assistant entrance -- the plain http LAN address and the
https one -- because the browser origin differs and only one of them is a
secure context.

Environment, the same names as the other Live tests:

    HA_BASE_URL          the Home Assistant entrance under test (required)
    HA_TEST_USER         Home Assistant login (required)
    HA_TEST_PASSWORD     Home Assistant password (required)
    ODOO_TEST_LOGIN      Odoo login (required)
    ODOO_TEST_PASSWORD   Odoo password (required)
    ODOO_PUBLIC_URL      the Public origin, which is the expected Canonical URL
    ADDON_SLUG           the add-on to open; a host may run more than one
    E2E_ARTIFACT_DIR     where the screenshots go

    python odoo18ce/tests/e2e_browser_built_links.py
"""
import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HA_BASE = os.environ.get("HA_BASE_URL", "").rstrip("/")
PUBLIC_BASE = os.environ.get("ODOO_PUBLIC_URL", "").rstrip("/")
HA_USER = os.environ.get("HA_TEST_USER")
HA_PASSWORD = os.environ.get("HA_TEST_PASSWORD")
ODOO_LOGIN = os.environ.get("ODOO_TEST_LOGIN")
ODOO_PASSWORD = os.environ.get("ODOO_TEST_PASSWORD")
ADDON_SLUG = os.environ.get("ADDON_SLUG", "")
GLOBAL_NAME = "__WOOW_CANONICAL_URL__"
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
ARTIFACTS = Path(os.environ.get("E2E_ARTIFACT_DIR", "/tmp/odoo-browser-built-links")) / STAMP


def require(value, name):
    if not value:
        sys.exit(f"error: {name} is required in the environment")
    return value


def mask(value):
    """Ingress tokens and channel invitation tokens are secrets; never print them."""
    text = str(value)
    text = re.sub(r"(/api/hassio_ingress/)[^/\s?#\"']+", r"\1<redacted>", text)
    text = re.sub(r"(/chat/\d+/)[^/\s?#\"']+", r"\1<redacted>", text)
    return text


def login_home_assistant(page):
    """Log in, then persist the session the way "keep me logged in" would.

    Home Assistant keeps its tokens in memory unless that box is ticked, and
    the box is a custom element Playwright cannot actuate, so the first full
    navigation would bounce back to the login form. Capture the frontend's own
    token exchange instead and write it back in the shape it reads.
    """
    captured = {}

    def on_response(response):
        if "/auth/token" in response.url and response.status == 200:
            try:
                body = response.json()
            except ValueError:
                return
            if body.get("access_token"):
                captured.update(body)

    page.on("response", on_response)
    page.goto(HA_BASE, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_selector('input[name="username"]', timeout=60_000)
    page.fill('input[name="username"]', HA_USER)
    page.fill('input[name="password"]', HA_PASSWORD)
    page.locator('input[name="password"]').press("Enter")
    for _ in range(120):
        if captured.get("access_token"):
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError("Home Assistant never completed a token exchange")

    page.evaluate(
        """({ tokens, hassUrl }) => {
            localStorage.setItem("hassTokens", JSON.stringify({
                access_token: tokens.access_token,
                token_type: tokens.token_type || "Bearer",
                refresh_token: tokens.refresh_token,
                expires_in: tokens.expires_in,
                hassUrl,
                clientId: hassUrl + "/",
                expires: Date.now() + (tokens.expires_in || 1800) * 1000,
            }));
        }""",
        {"tokens": captured, "hassUrl": HA_BASE},
    )


def ingress_frame(page):
    frames = [frame for frame in page.frames if "/api/hassio_ingress/" in frame.url]
    if not frames:
        raise AssertionError("no Ingress iframe; url=" + mask(page.url))
    return frames[0]


def open_addon(page):
    """Open one add-on by slug. A host may run several, so never pick by name."""
    page.goto(f"{HA_BASE}/{require(ADDON_SLUG, 'ADDON_SLUG')}", wait_until="domcontentloaded", timeout=120_000)
    for _ in range(120):
        if any("/api/hassio_ingress/" in frame.url for frame in page.frames):
            return ingress_frame(page)
        page.wait_for_timeout(500)
    page.screenshot(path=str(ARTIFACTS / "no-ingress-frame.png"))
    raise AssertionError("the add-on panel never loaded an Ingress iframe; url=" + mask(page.url))


def login_odoo(page, frame):
    if frame.locator('input[name="login"]').count():
        frame.locator('input[name="login"]').fill(ODOO_LOGIN)
        frame.locator('input[name="password"]').fill(ODOO_PASSWORD)
        frame.get_by_role("button", name="Log in", exact=True).click()
        page.wait_for_timeout(8000)
        frame = ingress_frame(page)
    frame.wait_for_selector(".o_main_navbar", timeout=60_000)
    return frame


def invitation_link(page, frame, channel):
    """The literal the Invite People panel shows for one channel."""
    prefix = re.match(r"(https?://[^/]+/api/hassio_ingress/[^/]+)", frame.url).group(1)
    frame.goto(prefix + "/odoo/discuss", wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(9000)
    frame = ingress_frame(page)
    frame.get_by_text(channel, exact=False).first.click()
    page.wait_for_timeout(5000)
    frame = ingress_frame(page)
    frame.locator('button[title="Invite People"]').first.click()
    page.wait_for_timeout(4000)
    frame = ingress_frame(page)
    page.screenshot(path=str(ARTIFACTS / "invite-people.png"))
    links = frame.evaluate(
        """() => Array.from(document.querySelectorAll("input, textarea"))
             .map(el => el.value).filter(v => v && v.includes("/chat/"))"""
    )
    if not links:
        raise AssertionError("the Invite People panel showed no invitation link")
    return links[0]


def run_ingress(browser, channel):
    page = browser.new_context(viewport={"width": 1500, "height": 1000}).new_page()
    login_home_assistant(page)
    frame = open_addon(page)
    page.wait_for_timeout(5000)
    frame = ingress_frame(page)

    # The shim runs on every Ingress page, including the login page, so this
    # is checked before Odoo authentication: an add-on serving it without the
    # global fails here rather than somewhere deep in the web client.
    published = frame.evaluate(f"window.{GLOBAL_NAME}")
    print(f"  {GLOBAL_NAME} on the Ingress page: {published!r}")
    assert published == PUBLIC_BASE, (
        f"the Runtime shim published {published!r}; expected the Canonical URL {PUBLIC_BASE!r}"
    )
    assert not published.endswith("/"), "the Canonical URL must carry no trailing slash"

    frame = login_odoo(page, frame)
    link = invitation_link(page, frame, channel)
    print(f"  Discuss invitation link: {mask(link)}")
    assert link.startswith(PUBLIC_BASE + "/chat/"), (
        f"the invitation link is on the wrong base: {mask(link)}; expected {PUBLIC_BASE}"
    )
    assert "/api/hassio_ingress/" not in link, "the invitation link carries an Ingress token"
    assert not link.startswith(HA_BASE), "the invitation link is still on the Home Assistant host"
    page.context.close()


def run_public(browser):
    """The Public origin serves the bundles as Odoo ships them."""
    page = browser.new_context().new_page()
    for bundle in ("web.assets_backend", "web.assets_frontend"):
        response = page.request.get(f"{PUBLIC_BASE}/web/assets/1/any/{bundle}.min.js", timeout=180_000)
        assert response.ok, f"{bundle}: {response.status} from the Public origin"
        body = response.text()
        assert GLOBAL_NAME not in body, (
            f"{bundle} on the Public origin carries {GLOBAL_NAME}; the rewrites must be Ingress-only"
        )
        print(f"  Public origin {bundle}: unrewritten ({len(body)} bytes)")
    page.context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=("ingress", "public", "both"), default="both")
    parser.add_argument("--channel", default="Administrators", help="the Discuss channel to read")
    args = parser.parse_args()

    for name, value in (
        ("HA_BASE_URL", HA_BASE),
        ("ODOO_PUBLIC_URL", PUBLIC_BASE),
        ("HA_TEST_USER", HA_USER),
        ("HA_TEST_PASSWORD", HA_PASSWORD),
        ("ODOO_TEST_LOGIN", ODOO_LOGIN),
        ("ODOO_TEST_PASSWORD", ODOO_PASSWORD),
    ):
        require(value, name)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"Home Assistant entrance: {HA_BASE}")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            if args.surface in ("ingress", "both"):
                run_ingress(browser, args.channel)
            if args.surface in ("public", "both"):
                run_public(browser)
        finally:
            browser.close()
    print(f"PASS  artifacts in {ARTIFACTS}")


if __name__ == "__main__":
    main()
