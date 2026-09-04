#!/usr/bin/env python3
"""Isolated Settings control E2E for Odoo public and HA Ingress surfaces.

Every action/object/dialog control is exercised in its own browser context so a
Home Assistant authorization refresh or a detached ingress frame cannot poison
subsequent results. Credentials are accepted only through environment variables.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import e2e_settings_ingress as shared

RUN_ID = (
    dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    + "-"
    + uuid.uuid4().hex
)
ARTIFACT_ROOT = (
    Path(os.environ.get("E2E_CONTROLS_ARTIFACT_DIR", "/tmp/odoo-settings-controls-e2e"))
    / RUN_ID
)
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
SAVE_SELECTOR = os.environ.get("ODOO_SETTINGS_SAVE_SELECTOR")
SAVE_VALUE = os.environ.get("ODOO_SETTINGS_SAVE_VALUE")
EXTERNAL_NAME_RE = re.compile(r"(?:buy\s+credits|purchase|upgrade)", re.I)


def classify_control(control):
    """Classify a serialized visible Settings button through public attributes."""
    name = (control.get("name") or "").strip()
    href = (control.get("href") or "").strip()
    odoo_type = (control.get("odoo_type") or "").strip().lower()
    html_type = (control.get("html_type") or "").strip().lower()
    aria_haspopup = (control.get("aria_haspopup") or "").strip().lower()
    toggle = (control.get("toggle") or "").strip().lower()

    external_href = False
    if href.startswith(("http://", "https://")):
        external_href = urlsplit(href).netloc not in {
            urlsplit(shared.HA_BASE).netloc,
            urlsplit(shared.PUBLIC_BASE).netloc,
        }
    if external_href or EXTERNAL_NAME_RE.search(name):
        return "external-skip"
    if name in {"Save", "Discard"} or html_type == "submit":
        return "form-control"
    if odoo_type in {"action", "object"}:
        return odoo_type
    if aria_haspopup == "dialog" or toggle == "modal":
        return "dialog"
    return "other"


def assert_self_tests():
    shared.assert_sanitizer_contract()
    cases = [
        ({"name": "Manage Users", "odoo_type": "action"}, "action"),
        ({"name": "Update Info", "odoo_type": "object"}, "object"),
        ({"name": "Open", "aria_haspopup": "dialog"}, "dialog"),
        ({"name": "Save", "html_type": "button"}, "form-control"),
        ({"name": "Buy Credits", "href": "/iap"}, "external-skip"),
        ({"name": "Vendor", "href": "https://external.invalid/buy"}, "external-skip"),
        ({"name": "Internal", "href": shared.PUBLIC_BASE + "/odoo/settings"}, "other"),
        ({"name": "Internal tab", "href": "/odoo/settings", "target": "_blank"}, "other"),
    ]
    for payload, expected in cases:
        assert classify_control(payload) == expected, (payload, expected)
    secret = {
        "url": "api/hassio_ingress/token-value/odoo/settings?code=secret&state=secret",
        "nested": ["?code=secret&state=secret"],
    }
    rendered = json.dumps(shared.sanitize_diagnostic(secret), sort_keys=True)
    assert "token-value" not in rendered
    assert "code=secret" not in rendered
    assert "state=secret" not in rendered


def evidence_template(surface, scenario):
    return {
        "surface": surface,
        "scenario": scenario,
        "started": dt.datetime.now(dt.timezone.utc).isoformat(),
        "http_failures": [],
        "request_failures": [],
        "console_errors": [],
        "page_errors": [],
        "frame_navigations": [],
    }


def safe_slug(value):
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")
    return (slug or "unnamed")[:80]


def save_artifact(page, evidence, scenario):
    directory = ARTIFACT_ROOT / safe_slug(scenario)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(directory / "final.png"), full_page=True)
    except PlaywrightError as error:
        evidence["screenshot_error"] = shared.diagnostic_text(str(error))
    (directory / "evidence.json").write_text(
        json.dumps(shared.sanitize_diagnostic(evidence), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def assert_clean(evidence):
    problems = {
        key: evidence[key]
        for key in ("http_failures", "request_failures", "console_errors", "page_errors")
        if evidence[key]
    }
    if problems:
        raise AssertionError("browser errors: " + shared.diagnostic_text(problems))


def wait_settings_loaded(page, frame_getter):
    last = None
    for _ in range(120):
        try:
            frame = frame_getter()
            save = frame.get_by_role("button", name="Save", exact=True)
            if save.count() and save.is_visible() and save.is_enabled():
                return frame
            last = {"url": frame.url, "save_count": save.count()}
        except PlaywrightError as error:
            if not shared.is_detached_frame_error(error):
                raise
            last = shared.diagnostic_text(str(error))
        page.wait_for_timeout(250)
    raise AssertionError("Settings controls did not load: " + shared.diagnostic_text(last))


def new_evidence_session(browser, surface, scenario):
    """Create resources before navigation so callers always own their cleanup."""
    context = browser.new_context()
    page = context.new_page(viewport={"width": 1440, "height": 1100})
    evidence = evidence_template(surface, scenario)
    shared.add_evidence(page, evidence)
    return context, page, evidence


def prepare_surface(page, surface):
    """Authenticate one isolated page and return its reacquiring frame getter."""
    if surface == "ingress":
        frame = shared.login_ha_and_open_panel(page)
        shared.login_odoo_in_frame(page, frame)
        shared.open_ingress_settings(page)
        frame_getter = lambda: shared.direct_ingress_frame(page)
    else:
        shared.require(shared.ODOO_LOGIN, "ODOO_TEST_LOGIN")
        shared.require(shared.ODOO_PASSWORD, "ODOO_TEST_PASSWORD")
        page.goto(
            f"{shared.PUBLIC_BASE}/web/login?redirect=/odoo/settings",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        login = page.locator('input[name="login"]')
        if login.count():
            login.wait_for(state="visible", timeout=30000)
            login.fill(shared.ODOO_LOGIN)
            page.locator('input[name="password"]').fill(shared.ODOO_PASSWORD)
            page.get_by_role("button", name="Log in", exact=True).click()
        page.locator(".settings_tab").wait_for(timeout=30000)
        frame_getter = lambda: page.main_frame
    wait_settings_loaded(page, frame_getter)
    return frame_getter


def serialized_controls(frame):
    root = frame.locator(".o_action_manager")
    controls = root.get_by_role("button")
    serialized = []
    name_occurrences = {}
    for index in range(controls.count()):
        control = controls.nth(index)
        if not control.is_visible() or not control.is_enabled():
            continue
        item = control.evaluate(
            """element => ({
                name: (element.getAttribute('aria-label') || element.innerText ||
                       element.getAttribute('title') || '').trim(),
                odoo_type: element.getAttribute('type'),
                html_type: element.type || null,
                href: element.getAttribute('href'),
                target: element.getAttribute('target'),
                aria_haspopup: element.getAttribute('aria-haspopup'),
                toggle: element.getAttribute('data-bs-toggle'),
            })"""
        )
        item = shared.sanitize_diagnostic(item)
        item["category"] = classify_control(item)
        item["dom_index"] = index
        item["name_occurrence"] = name_occurrences.get(item["name"], 0)
        name_occurrences[item["name"]] = item["name_occurrence"] + 1
        item["id"] = f"{item['category']}:{item['name']}:{item['name_occurrence']}"
        serialized.append(item)
    return serialized


def discover_controls(browser, surface):
    scenario = f"{surface}-inventory"
    context, page, evidence = new_evidence_session(browser, surface, scenario)
    try:
        frame_getter = prepare_surface(page, surface)
        controls = serialized_controls(frame_getter())
        evidence["controls"] = controls
        assert controls, "no visible Settings controls discovered"
        assert_clean(evidence)
        return controls
    finally:
        try:
            save_artifact(page, evidence, scenario)
        finally:
            context.close()


def locate_control(frame, item):
    matches = frame.locator(".o_action_manager").get_by_role(
        "button", name=item["name"], exact=True
    )
    occurrence = item["name_occurrence"]
    if matches.count() <= occurrence:
        raise AssertionError(
            "Settings control disappeared: "
            + shared.diagnostic_text({"id": item["id"], "count": matches.count()})
        )
    return matches.nth(occurrence)


def observe_outcome(page, frame_getter, before_url):
    last = None
    for _ in range(100):
        frame = frame_getter()
        dialogs = frame.locator(".modal.show, .o_dialog")
        visible_dialog = next(
            (dialogs.nth(i) for i in range(dialogs.count()) if dialogs.nth(i).is_visible()),
            None,
        )
        if visible_dialog is not None:
            title = visible_dialog.locator(".modal-title, .o_dialog_title")
            return {
                "kind": "dialog",
                "url": frame.url,
                "dialog_title": title.first.inner_text().strip() if title.count() else None,
            }
        last = frame.url
        if frame.url != before_url:
            return {"kind": "navigation", "url": frame.url, "dialog_title": None}
        page.wait_for_timeout(100)
    return {"kind": "same-page", "url": last, "dialog_title": None}


def execute_control(browser, surface, item):
    scenario = f"{surface}-{item['id']}"
    context, page, evidence = new_evidence_session(browser, surface, scenario)
    result = {"id": item["id"], "name": item["name"], "category": item["category"]}
    try:
        frame_getter = prepare_surface(page, surface)
        frame = frame_getter()
        control = locate_control(frame, item)
        before_url = frame.url
        control.click(timeout=30000)
        outcome = observe_outcome(page, frame_getter, before_url)
        outcome = shared.sanitize_diagnostic(outcome)
        result.update(outcome)
        assert "/odoo/discuss" not in outcome["url"], shared.diagnostic_text(result)
        assert_clean(evidence)
        result["status"] = "passed"
    except (AssertionError, RuntimeError, PlaywrightError) as error:
        result.update({"status": "failed", "error": shared.diagnostic_text(str(error))})
    finally:
        evidence["result"] = result
        try:
            save_artifact(page, evidence, scenario)
        finally:
            context.close()
    return result


def run_discard(browser, surface):
    scenario = f"{surface}-discard"
    context, page, evidence = new_evidence_session(browser, surface, scenario)
    result = {"scenario": "discard"}
    try:
        frame_getter = prepare_surface(page, surface)
        frame = frame_getter()
        checkboxes = frame.locator(
            '.o_action_manager input[type="checkbox"]:not([disabled])'
        )
        index = next(
            (i for i in range(checkboxes.count()) if checkboxes.nth(i).is_visible()),
            None,
        )
        assert index is not None, "no visible enabled checkbox available for Discard"
        checkbox = checkboxes.nth(index)
        original = checkbox.is_checked()
        checkbox.click()
        assert checkbox.is_checked() != original, "checkbox did not change before Discard"
        frame.get_by_role("button", name="Discard", exact=True).click()
        frame = wait_settings_loaded(page, frame_getter)
        restored = frame.locator(
            '.o_action_manager input[type="checkbox"]:not([disabled])'
        ).nth(index).is_checked()
        assert restored == original, {"original": original, "after_discard": restored}
        assert "/odoo/discuss" not in frame.url
        assert_clean(evidence)
        result.update({"status": "passed", "restored": True, "url": shared.sanitize_diagnostic(frame.url)})
    except (AssertionError, RuntimeError, PlaywrightError) as error:
        result.update({"status": "failed", "error": shared.diagnostic_text(str(error))})
    finally:
        evidence["result"] = result
        try:
            save_artifact(page, evidence, scenario)
        finally:
            context.close()
    return result


def mutate_explicit_field(field, new_value=None):
    field_type = (field.get_attribute("type") or "text").lower()
    if field_type == "checkbox":
        original = field.is_checked()
        field.click()
        return original, not original, "checkbox"
    if new_value is None:
        raise RuntimeError(
            "ODOO_SETTINGS_SAVE_VALUE is required for a non-checkbox save selector"
        )
    original = field.input_value()
    field.fill(new_value)
    return original, new_value, field_type


def field_equals(field, expected, field_type):
    if field_type == "checkbox":
        return field.is_checked() == expected
    return field.input_value() == expected


def run_save_restore(browser, surface):
    scenario = f"{surface}-save-restore"
    if not SAVE_SELECTOR:
        return {
            "scenario": "save-restore",
            "status": "blocked",
            "reason": "ODOO_SETTINGS_SAVE_SELECTOR is required; no arbitrary setting was mutated",
        }
    context, page, evidence = new_evidence_session(browser, surface, scenario)
    result = {"scenario": "save-restore", "selector_supplied": True}
    try:
        frame_getter = prepare_surface(page, surface)
        frame = frame_getter()
        field = frame.locator(SAVE_SELECTOR).first
        field.wait_for(state="visible", timeout=30000)
        assert field.is_enabled(), "explicit save field is disabled"
        original, changed, field_type = mutate_explicit_field(field, SAVE_VALUE)
        frame.get_by_role("button", name="Save", exact=True).click()
        frame = wait_settings_loaded(page, frame_getter)
        persisted = frame.locator(SAVE_SELECTOR).first
        persisted.wait_for(state="visible", timeout=30000)
        assert field_equals(persisted, changed, field_type), "saved value did not persist"
        if field_type == "checkbox":
            persisted.click()
        else:
            persisted.fill(original)
        frame.get_by_role("button", name="Save", exact=True).click()
        frame = wait_settings_loaded(page, frame_getter)
        restored = frame.locator(SAVE_SELECTOR).first
        restored.wait_for(state="visible", timeout=30000)
        assert field_equals(restored, original, field_type), "original value was not restored"
        assert "/odoo/discuss" not in frame.url
        assert_clean(evidence)
        result.update({"status": "passed", "restored": True, "field_type": field_type})
    except (AssertionError, RuntimeError, PlaywrightError) as error:
        result.update({"status": "failed", "error": shared.diagnostic_text(str(error))})
    finally:
        evidence["result"] = result
        try:
            save_artifact(page, evidence, scenario)
        finally:
            context.close()
    return result


def comparable_controls(controls):
    return {
        (item["name"], item["name_occurrence"], item["category"])
        for item in controls
        if item["category"] in {"action", "object", "dialog", "external-skip"}
    }


def run_surface(browser, surface):
    controls = discover_controls(browser, surface)
    results = []
    for item in controls:
        if item["category"] == "external-skip":
            results.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "status": "skipped",
                    "reason": "external/IAP purchase control is never clicked",
                }
            )
        elif item["category"] in {"action", "object", "dialog"}:
            results.append(execute_control(browser, surface, item))
    discard = run_discard(browser, surface)
    save_restore = run_save_restore(browser, surface)
    return {
        "surface": surface,
        "controls": controls,
        "results": results,
        "discard": discard,
        "save_restore": save_restore,
    }


def assert_surface_success(report):
    failures = [item for item in report["results"] if item["status"] == "failed"]
    assert not failures, shared.diagnostic_text(failures)
    assert report["discard"]["status"] == "passed", shared.diagnostic_text(report["discard"])
    assert report["save_restore"]["status"] in {"passed", "blocked"}, shared.diagnostic_text(
        report["save_restore"]
    )


def assert_parity(ingress, public):
    assert comparable_controls(ingress["controls"]) == comparable_controls(public["controls"]), (
        "Settings controls differ: "
        + shared.diagnostic_text(
            {
                "ingress": sorted(comparable_controls(ingress["controls"])),
                "public": sorted(comparable_controls(public["controls"])),
            }
        )
    )
    ingress_outcomes = {
        item["id"]: item.get("kind")
        for item in ingress["results"]
        if item["status"] == "passed"
    }
    public_outcomes = {
        item["id"]: item.get("kind")
        for item in public["results"]
        if item["status"] == "passed"
    }
    assert ingress_outcomes == public_outcomes, (
        "Settings control outcomes differ: "
        + shared.diagnostic_text({"ingress": ingress_outcomes, "public": public_outcomes})
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface", choices=("ingress", "public", "both"), default="both")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    assert_self_tests()
    if args.self_test:
        print("Settings controls self-tests passed")
        return
    reports = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            if args.surface in {"ingress", "both"}:
                reports["ingress"] = run_surface(browser, "ingress")
                assert_surface_success(reports["ingress"])
            if args.surface in {"public", "both"}:
                reports["public"] = run_surface(browser, "public")
                assert_surface_success(reports["public"])
            if args.surface == "both":
                assert_parity(reports["ingress"], reports["public"])
        finally:
            browser.close()
    (ARTIFACT_ROOT / "summary.json").write_text(
        json.dumps(shared.sanitize_diagnostic(reports), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Settings controls E2E artifacts: {ARTIFACT_ROOT}")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, PlaywrightError) as error:
        safe_error = shared.diagnostic_text(str(error))
        print(
            f"Settings controls E2E failed; artifacts: {ARTIFACT_ROOT}; error: {safe_error}",
            file=sys.stderr,
        )
        raise RuntimeError(safe_error) from None
