#!/usr/bin/env python3
"""Real Settings route regression for Odoo public and HA Ingress surfaces.

Credentials are read exclusively from the environment.  The test does not save,
change, or open business configuration controls.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

HA_BASE = os.environ.get("HA_BASE_URL", "https://woowtech-ha.woowtech.io").rstrip("/")
PUBLIC_BASE = os.environ.get("ODOO_PUBLIC_URL", "https://woowtech-odooo.woowtech.io").rstrip("/")
HA_USER = os.environ.get("HA_TEST_USER")
HA_PASSWORD = os.environ.get("HA_TEST_PASSWORD")
ODOO_LOGIN = os.environ.get("ODOO_TEST_LOGIN")
ODOO_PASSWORD = os.environ.get("ODOO_TEST_PASSWORD")
BASELINE_TAB_KEYS = {"general_settings", "calendar", "website", "stock", "account", "point_of_sale"}
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
ARTIFACT_DIR = Path(os.environ.get("E2E_ARTIFACT_DIR", "/tmp/odoo-settings-e2e")) / STAMP
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def require(value, name):
    if not value:
        raise RuntimeError(f"{name} is required in the environment")
    return value


def direct_ingress_frame(page):
    """Return only the current direct HA panel iframe, never a detached child."""
    for _ in range(100):
        frames = [
            frame for frame in page.frames
            if frame.parent_frame == page.main_frame and "/api/hassio_ingress/" in frame.url
        ]
        if frames:
            return frames[0]
        page.wait_for_timeout(200)
    raise AssertionError(f"direct ingress iframe absent; frames={[frame.url for frame in page.frames]}")


def add_evidence(page, evidence):
    page.on("response", lambda response: evidence["http_failures"].append({"status": response.status, "url": response.url}) if response.status >= 400 else None)
    page.on("requestfailed", lambda request: evidence["request_failures"].append({"url": request.url, "failure": request.failure}) )
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on("console", lambda message: evidence["console_errors"].append(message.text) if message.type == "error" else None)
    page.on("framenavigated", lambda frame: evidence["frame_navigations"].append(frame.url))


def redact_sensitive_urls(value):
    """Never persist ingress tokens or authorization query values."""
    if isinstance(value, str):
        value = re.sub(r"/api/hassio_ingress/[^/]+", "/api/hassio_ingress/<redacted>", value)
        value = re.sub(r"(https?://[^\s?#]+)\?[^\s#]*", r"\1", value)
        if value.startswith(("http://", "https://")):
            parts = urlsplit(value)
            value = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        return value
    if isinstance(value, list):
        return [redact_sensitive_urls(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_sensitive_urls(item) for key, item in value.items()}
    return value


def assert_no_http_failures(evidence):
    failures = evidence["http_failures"]
    if failures:
        raise AssertionError(f"HTTP >=400 responses: {failures}; artifacts: {ARTIFACT_DIR}")


def save(page, evidence, surface):
    try:
        page.screenshot(path=str(ARTIFACT_DIR / f"{surface}-final.png"), full_page=True)
    finally:
        (ARTIFACT_DIR / f"{surface}-evidence.json").write_text(
            json.dumps(redact_sensitive_urls(evidence), ensure_ascii=False, indent=2), encoding="utf-8"
        )


def login_ha_and_open_panel(page):
    require(HA_USER, "HA_TEST_USER")
    require(HA_PASSWORD, "HA_TEST_PASSWORD")
    # HA may complete its authorization-code callback after the login form has
    # disappeared.  Wait for the actual sidebar item rather than assuming a
    # fixed delay means the dashboard is ready.
    for attempt in range(3):
        page.goto(HA_BASE, wait_until="domcontentloaded", timeout=120000)
        for _ in range(100):
            username = page.locator('input[name="username"]')
            if username.count() and username.is_visible():
                username.fill(HA_USER)
                page.locator('input[name="password"]').fill(HA_PASSWORD)
                page.locator('input[name="password"]').press("Enter")
            panel = page.get_by_text("Woow Odoo", exact=True)
            if panel.count() and panel.is_visible():
                panel.click(timeout=30000)
                return direct_ingress_frame(page)
            page.wait_for_timeout(300)
        # Retry the root URL after an incomplete/expired HA authorization
        # callback; do not reuse an iframe or page handle from that attempt.
    raise AssertionError(f"HA sidebar did not become ready after authentication; url={page.url}")


def login_odoo_in_frame(page, frame):
    require(ODOO_LOGIN, "ODOO_TEST_LOGIN")
    require(ODOO_PASSWORD, "ODOO_TEST_PASSWORD")
    if frame.locator('input[name="login"]').count():
        frame.locator('input[name="login"]').fill(ODOO_LOGIN)
        frame.locator('input[name="password"]').fill(ODOO_PASSWORD)
        frame.get_by_role("button", name="Log in", exact=True).click()
    last = None
    for _ in range(100):
        try:
            frame = direct_ingress_frame(page)
            frame.locator(".o_main_navbar").wait_for(timeout=500)
            return frame
        except (AssertionError, PlaywrightError, PlaywrightTimeoutError) as error:
            last = error
    raise AssertionError(f"Odoo navbar did not become ready after login: {last}")


def open_ingress_settings(page):
    """Open Settings, retrying only HA parent re-auth/panel replacement."""
    last = None
    for _ in range(3):
        try:
            frame = direct_ingress_frame(page)
            frame.locator(".o_main_navbar").wait_for(timeout=15000)
            frame.locator(".o_navbar_apps_menu button").click()
            frame.locator('a.o_app[data-menu-xmlid="base.menu_administration"]').last.click()
            frame = direct_ingress_frame(page)
            frame.locator(".settings_tab").wait_for(timeout=20000)
            return frame
        except (AssertionError, PlaywrightError, PlaywrightTimeoutError) as error:
            last = error
            # HA may replace the panel with its authorization document. Reopen
            # the sidebar item instead of retaining a stale Frame handle.
            if "/auth/authorize" in page.url or not any("/api/hassio_ingress/" in f.url for f in page.frames):
                frame = login_ha_and_open_panel(page)
                login_odoo_in_frame(page, frame)
            else:
                continue
    raise AssertionError(f"could not open ingress Settings after retry: {last}")


def discover_tab_keys(frame):
    """Discover every visible, enabled Settings tab in stable DOM order."""
    tabs = frame.locator(".settings_tab a.tab[data-key]")
    keys = []
    for index in range(tabs.count()):
        tab = tabs.nth(index)
        key = tab.get_attribute("data-key")
        enabled = tab.get_attribute("aria-disabled") != "true" and tab.get_attribute("disabled") is None
        if key and enabled and tab.is_visible() and key not in keys:
            keys.append(key)
    missing = BASELINE_TAB_KEYS.difference(keys)
    assert not missing, f"baseline Settings tabs missing: {sorted(missing)}; discovered={keys}"
    return keys


def wait_for_selected_tab(page, frame_getter, key):
    """Reacquire replacement frames until the requested Settings tab is active."""
    last = None
    for _ in range(100):
        try:
            frame = frame_getter()
            selected = frame.locator('.settings_tab a.tab.selected[data-key]')
            selected_key = selected.get_attribute("data-key") if selected.count() else None
            last = {"url": frame.url, "selected": selected_key}
            if selected_key == key and frame.locator(".settings").is_visible():
                return frame, selected_key
        except (AssertionError, PlaywrightError, PlaywrightTimeoutError) as error:
            last = str(error)
        page.wait_for_timeout(100)
    raise AssertionError(f"Settings tab did not become selected: key={key}; last={last}")


def assert_tabs_in_frame(page, frame_getter, surface, evidence, post_click_frame_getter=None):
    post_click_frame_getter = post_click_frame_getter or frame_getter
    initial_frame = frame_getter()
    keys = discover_tab_keys(initial_frame)
    evidence["discovered_tabs"] = keys
    results = []
    for key in keys:
        frame = frame_getter()
        tab = frame.locator(f'.settings_tab a.tab[data-key="{key}"]')
        tab.wait_for(timeout=20000)
        before_url, before_href = frame.url, tab.get_attribute("href")
        tab.click()
        frame, selected_key = wait_for_selected_tab(page, post_click_frame_getter, key)
        result = {"key": key, "before_url": before_url, "before_href": before_href, "after_url": frame.url, "selected": selected_key}
        results.append(result)
        assert "/odoo/settings" in frame.url, result
        assert "/odoo/discuss" not in frame.url, result
        assert selected_key == key, result
        assert frame.locator(".settings").is_visible(), result
    evidence["tab_results"] = results
    return keys


def run_ingress(browser):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    evidence = {"surface": "ingress", "started": dt.datetime.now(dt.timezone.utc).isoformat(), "http_failures": [], "request_failures": [], "console_errors": [], "page_errors": [], "frame_navigations": []}
    add_evidence(page, evidence)
    try:
        frame = login_ha_and_open_panel(page)
        login_odoo_in_frame(page, frame)
        keys = assert_tabs_in_frame(
            page,
            lambda: open_ingress_settings(page),
            "ingress",
            evidence,
            post_click_frame_getter=lambda: direct_ingress_frame(page),
        )
        assert_no_http_failures(evidence)
    finally:
        save(page, evidence, "ingress")
        page.close()
    return keys


def run_public(browser):
    require(ODOO_LOGIN, "ODOO_TEST_LOGIN")
    require(ODOO_PASSWORD, "ODOO_TEST_PASSWORD")
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    evidence = {"surface": "public", "started": dt.datetime.now(dt.timezone.utc).isoformat(), "http_failures": [], "request_failures": [], "console_errors": [], "page_errors": [], "frame_navigations": []}
    add_evidence(page, evidence)
    try:
        page.goto(f"{PUBLIC_BASE}/web/login?redirect=/odoo/settings", wait_until="domcontentloaded", timeout=120000)
        if page.locator('input[name="login"]').count():
            page.locator('input[name="login"]').fill(ODOO_LOGIN)
            page.locator('input[name="password"]').fill(ODOO_PASSWORD)
            page.get_by_role("button", name="Log in", exact=True).click()
        page.locator(".settings_tab").wait_for(timeout=30000)
        keys = assert_tabs_in_frame(page, lambda: page.main_frame, "public", evidence)
        assert_no_http_failures(evidence)
    finally:
        save(page, evidence, "public")
        page.close()
    return keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface", choices=("ingress", "public", "both"), default="both")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            ingress_keys = run_ingress(browser) if args.surface in ("ingress", "both") else None
            public_keys = run_public(browser) if args.surface in ("public", "both") else None
            if args.surface == "both":
                assert set(ingress_keys) == set(public_keys), (
                    f"Settings tab mismatch: ingress={ingress_keys}; public={public_keys}"
                )
        finally:
            browser.close()
    print(f"Settings E2E artifacts: {ARTIFACT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Settings E2E failed; artifacts: {ARTIFACT_DIR}; error: {error}", file=sys.stderr)
        raise
