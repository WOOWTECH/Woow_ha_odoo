#!/usr/bin/env python3
"""Static-tier contract for the folders the app maps (issue #126).

Supervisor 2026.07 renamed the app-scoped map types: `addon_config` became
`app_config`, and the old names are logged as legacy on every build. The
manifest uses the new name with the same `rw` access, so the container
still sees its config folder at `/config`. Supervisors older than 2026.07.1
reject `app_config`; the CHANGELOG states that minimum.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {"addon_config", "addons", "all_addon_configs"}


def mapped() -> list:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return [str(entry) for entry in config["map"]]


def test_the_config_folder_is_mapped_as_app_config_rw() -> None:
    assert "app_config:rw" in mapped()
    assert "share:rw" in mapped()


def test_no_legacy_map_type_is_listed() -> None:
    offenders = [entry for entry in mapped() if entry.split(":", 1)[0] in LEGACY]
    assert offenders == [], offenders
