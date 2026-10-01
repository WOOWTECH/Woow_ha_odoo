#!/usr/bin/env python3
"""Record bullets under `## Unreleased` -> `### Changed` in a CHANGELOG.

Used by the weekly bump bot (`.github/workflows/odoo-bump.yml`), which since
issue #215 proposes the Odoo nightly pin and the Debian base-image tag in two
independent pull requests. Both write here, so the writer has to *merge*: it
adds its bullets to whatever `## Unreleased` already holds -- the other path's
open pull request may have put its own bullet there first, and the next
Release collects the whole section (ADR 0002).

Usage: changelog_unreleased.py <CHANGELOG.md> <bullet> [<bullet>...]
"""
import argparse
import sys

HEAD = "# Changelog\n\n"
SECTION = "## Unreleased\n"
MARKER = "### Changed\n"


def record(text: str, bullets: list) -> str:
    """`text` with `bullets` added under Unreleased -> Changed."""
    if not text.startswith(HEAD):
        raise ValueError("CHANGELOG.md must start with '# Changelog'")
    entry = "".join(f"- {bullet}\n" for bullet in bullets)
    rest = text[len(HEAD):]
    if rest.startswith(SECTION):
        body = rest[len(SECTION):]
        # Only a `### Changed` inside this section counts; the next `## `
        # heading is the released version below it.
        if MARKER in body.split("\n## ", 1)[0]:
            at = body.index(MARKER) + len(MARKER)
            body = body[:at] + entry + body[at:]
        else:
            body = "\n" + MARKER + entry + body
        rest = SECTION + body
    else:
        rest = SECTION + "\n" + MARKER + entry + "\n" + rest
    return HEAD + rest


def main(argv: list) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("changelog", help="path to the CHANGELOG.md to record in")
    parser.add_argument("bullet", nargs="+", help="one bullet, without its '- '")
    args = parser.parse_args(argv[1:])
    with open(args.changelog, encoding="utf-8") as handle:
        text = handle.read()
    try:
        recorded = record(text, args.bullet)
    except ValueError as unrecognised:
        raise SystemExit(str(unrecognised)) from unrecognised
    with open(args.changelog, "w", encoding="utf-8") as handle:
        handle.write(recorded)


if __name__ == "__main__":
    main(sys.argv)
