"""The Ingress checks that have no adapter subcommand, driven one at a time.

`e2e_menu_action_adapter.py` opens a screen and judges it against the same
screen on the other surface. Three of the things a Live run has to see are not
that shape -- they are one action taken in one browser, on one surface, whose
result is read somewhere else:

    visit     one website page view through Ingress. What it proves is in
              `website.track`, not on the page (#160: the row carries the
              Canonical URL).
    editbtn   the website page's "Edit this content" link. Its literal is a
              two-surface question the adapter already answers; whether
              *following* it opens the page in the web client is a click
              (#211).
    todosave  the To-do form's description saved in the HTML editor. What it
              proves is in `project.task.description` afterwards: the stored
              `src` is still root-relative (#210).

So this driver takes the action and records what it saw; the reading that
judges it is taken on the host and written into the evidence README. There is
no pure decision here to test on the Static tier -- every field of the record
is read from the page.

It borrows `e2e_menu_action_adapter`'s `SurfaceDriver` rather than logging in
by hand: that is where the Ingress session, the session cookie, the database
reading and the `Masker` live, so a record written here hides the same
credentials, prefixes and origins the adapter's records hide.

    ~/venvs/woow/bin/python odoo18ce/tests/e2e_ingress_hand_checks.py visit \
      --env-file /projects/Woow_ha_odoo/.env --out hand-checks.jsonl

Each run appends one JSON object to `--out`. Writing: `visit` creates a
`website.visitor` / `website.track` row, `todosave` writes
`project.task.description`, `editbtn` writes nothing. The boundary is
ADR 0012.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import e2e_menu_action_adapter as adapter  # noqa: E402

# The marker typed into the to-do description, so a human reading the record
# afterwards knows which run put it there. The description is restored from the
# reading taken before the save, which is part of the evidence.
DEFAULT_MARKER = "WOOW-PARITY hand check"
HTML_FIELD = ".o_field_html"
EDITABLE = HTML_FIELD + " .odoo-editor-editable"
EDIT_BUTTON = "a.o_frontend_to_backend_edit_btn"
TODO_FORM = "/odoo/action-project_todo.project_task_action_todo/5"


def watch(page, requested: list[str], failed: list[str], console: list[str]) -> None:
    """Record every request the page makes, the failures, and console errors.

    The adapter counts the same three signals; this is the same reading taken
    on a page the adapter is not driving.
    """
    page.on("request", lambda request: requested.append(request.url))
    page.on("response", lambda response: failed.append(
        "HTTP%d %s" % (response.status, response.url)) if response.status >= 400 else None)
    page.on("console", lambda message: console.append(
        "%s: %s" % (message.type, message.text)) if message.type == "error" else None)


def escaped_to_the_ha_root(urls: list[str], ha_origin: str | None, base: str) -> list[str]:
    """The requests that went to the Home Assistant host outside the prefix.

    This is `route_escape` in the adapter's vocabulary, read on this page: a
    request to the Home Assistant origin that does not carry the Ingress
    prefix is a request Odoo never sees.
    """
    if not ha_origin:
        return []
    return sorted({url for url in urls if url.startswith(ha_origin) and not url.startswith(base)})


def route_of(driver, url: str) -> str | None:
    """`url` with the Ingress prefix taken off, or None when it is not on it.

    The `Masker` writes `<INGRESS_BASE>` for the origin and the prefix
    together, so a recorded URL alone does not say which page was reached.
    This is the adapter's own normalisation, which is what the two-surface
    records are joined on.
    """
    try:
        path = urlsplit(url).path
        return adapter.normalize_route(
            path, adapter.Surface.HA_INGRESS, ingress_prefix=driver.prefix).as_string()
    except ValueError:
        return None


def do_visit(page, driver, record, path) -> None:
    page.goto(driver.base + path, wait_until="load", timeout=120000)
    # The tracked row is written by the dispatch of this page view; the wait is
    # for the page to finish, not for the row.
    page.wait_for_timeout(3000)
    record["url_after"] = page.url
    record["route_after"] = route_of(driver, page.url)
    record["title"] = page.title()


def do_editbtn(page, driver, record, path, preview_selector: str | None = None) -> None:
    page.goto(driver.base + path, wait_until="load", timeout=120000)
    page.wait_for_timeout(2000)
    buttons = page.locator(EDIT_BUTTON)
    record["button_count"] = buttons.count()
    if not record["button_count"]:
        record["error"] = "no %s on this page: the user cannot edit it" % EDIT_BUTTON
        return
    button = buttons.first
    # The attribute is what the bundle built; the property is what the browser
    # resolved it against. #211 is about the attribute, and a relative
    # attribute with the right property would still be a pass.
    record["href_attribute"] = button.get_attribute("href")
    record["href_resolved"] = button.evaluate("element => element.href")
    button.click()
    page.wait_for_load_state("load", timeout=120000)
    page.wait_for_timeout(5000)
    record["url_after"] = page.url
    record["route_after"] = route_of(driver, page.url)
    record["navbar"] = page.locator(".o_main_navbar").count() > 0
    record["website_preview"] = page.locator(".o_website_preview").count() > 0
    if record["website_preview"]:
        # The editor holds two iframes: the page and the hidden fallback it
        # navigates through. Which one is first in the DOM is not a contract,
        # so every frame is recorded and the page is the one showing the
        # selector. A link that resolved to the wrong path leaves only the
        # fallback, with nothing of the page in it.
        record["preview_iframe_src"] = page.locator(
            ".o_website_preview iframe").first.get_attribute("src")
        frames = []
        shown = False
        for handle in page.locator(".o_website_preview iframe").element_handles():
            frame = handle.content_frame()
            if frame is None:
                frames.append({"route": None, "title": None, "shows_selector": None})
                continue
            here = {"route": route_of(driver, frame.url), "title": frame.title()}
            if preview_selector:
                try:
                    here["shows_selector"] = frame.locator(preview_selector).count() > 0
                except Exception as error:                      # a frame that navigated away
                    here["shows_selector"] = "unreadable: %s" % type(error).__name__
                shown = shown or here["shows_selector"] is True
            frames.append(here)
        record["preview_frames"] = frames
        record["preview_shows_selector"] = shown if preview_selector else None


def do_todosave(page, driver, record, marker, *, save: bool = True) -> None:
    page.goto(driver.base + TODO_FORM, wait_until="load", timeout=120000)
    editable = page.locator(EDITABLE).first
    editable.wait_for(timeout=60000)
    page.wait_for_timeout(3000)
    images = page.locator(HTML_FIELD + " img")
    # What the editor put in the DOM, what the browser resolved it to, and
    # whether the picture actually arrived. #210's fix is the first of these
    # carrying the prefix and the third being true.
    record["img_src_attribute"] = images.evaluate_all(
        "els => els.map(e => e.getAttribute('src'))")
    record["img_src_resolved"] = images.evaluate_all("els => els.map(e => e.src)")
    record["img_loaded"] = images.evaluate_all(
        "els => els.map(e => e.complete && e.naturalWidth > 0)")
    record["saved"] = save
    if not save:
        # Reading the editor without writing it: what the field rendered is
        # already the whole of #210's render-site half, and a run that is only
        # confirming the selectors still work should not write the record.
        return
    editable.click()
    page.keyboard.press("End")
    page.keyboard.type(" " + marker)
    page.wait_for_timeout(1000)
    save = page.locator(".o_form_button_save").first
    record["save_button"] = save.count() > 0
    save.click()
    page.wait_for_timeout(8000)
    record["url_after"] = page.url
    # An unsaved record keeps the save/discard pair on screen.
    record["unsaved_after_save"] = page.locator(
        ".o_form_status_indicator_buttons:not(.invisible)").count() > 0


def run(command: str, out_path: str, *, path: str, marker: str, save: bool = True,
        preview_selector: str | None = None) -> int:
    from playwright.sync_api import sync_playwright

    ignore_https = os.environ.get("IGNORE_HTTPS_ERRORS", "0") == "1"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        driver = None
        try:
            driver = adapter.SurfaceDriver(
                adapter.Surface.HA_INGRESS, browser,
                ignore_https_errors=ignore_https, viewport=(1920, 1080),
            )
            driver.log_in()
            record = {
                "check": command,
                "surface": adapter.Surface.HA_INGRESS.value,
                "database": adapter.session_database(driver.database),
                "run_id": adapter.new_run_id(),
                "target": os.environ.get("PARITY_TARGET", "local"),
            }
            requested: list[str] = []
            failed: list[str] = []
            console: list[str] = []
            page = driver.context.new_page()
            watch(page, requested, failed, console)
            try:
                if command == "visit":
                    do_visit(page, driver, record, path)
                elif command == "editbtn":
                    do_editbtn(page, driver, record, path, preview_selector)
                else:
                    do_todosave(page, driver, record, marker, save=save)
            finally:
                record["console_error"] = console[:40]
                record["http_4xx_5xx"] = sorted(set(failed))
                record["route_escape"] = escaped_to_the_ha_root(
                    requested, driver.ha_origin, driver.base)
                page.close()
            line = json.dumps(driver.masker.value(record), ensure_ascii=False, sort_keys=True)
            with open(out_path, "a", encoding="utf-8") as out:
                out.write(line + "\n")
            print(line)
            return 0
        finally:
            if driver is not None:
                driver.close()
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["visit", "editbtn", "todosave"])
    parser.add_argument("--out", required=True, help="JSONL evidence file; appended to")
    parser.add_argument("--path", default="/", help="website path for visit and editbtn")
    parser.add_argument("--marker", default=DEFAULT_MARKER,
                        help="text typed into the to-do description before saving")
    parser.add_argument("--env-file", help="read unset credentials from this NAME=value file")
    parser.add_argument("--preview-selector",
                        help="editbtn: a selector that must be inside the opened preview")
    parser.add_argument("--no-save", action="store_true",
                        help="todosave: read the editor and write nothing")
    args = parser.parse_args(argv)
    if args.env_file:
        with open(args.env_file, encoding="utf-8") as handle:
            adapter.parse_env_file(handle, os.environ)
    return run(args.command, args.out, path=args.path, marker=args.marker,
               save=not args.no_save, preview_selector=args.preview_selector)


if __name__ == "__main__":
    raise SystemExit(main())
