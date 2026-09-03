#!/usr/bin/env python3
"""Contracts for the narrow ingress rewrites used by Settings icons."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "rootfs/etc/nginx/nginx.conf.template"
DYNAMIC_SOURCE = 'imgurl:el.getAttribute("logo")||"/"+el.getAttribute("name")+"/static/description/icon.png"'
DYNAMIC_TARGET = 'imgurl:el.getAttribute("logo")||"$safe_ingress_path/"+el.getAttribute("name")+"/static/description/icon.png"'
DIRECT_LOGO_SOURCE = 'logo="/'
DIRECT_LOGO_TARGET = 'logo="$safe_ingress_path/'
ESCAPED_LOGO_SOURCE = r'logo=\"/'
ESCAPED_LOGO_TARGET = r'logo=\"$safe_ingress_path/'


def rule(source: str, target: str) -> str:
    return f"sub_filter '{source}' '{target}';"


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    public_start = template.index("# Internal public origin.")
    ingress_start = template.index("# HA Supervisor Ingress adapter.")
    public = template[public_start:ingress_start]
    ingress = template[ingress_start:]
    assets_start = ingress.index("location ^~ /web/assets/ {")
    generic_start = ingress.index("\n        location / {", assets_start)
    assets = ingress[assets_start:generic_start]
    generic = ingress[generic_start:]

    dynamic_rule = rule(DYNAMIC_SOURCE, DYNAMIC_TARGET)
    assert dynamic_rule in assets, "missing exact SettingsViewCompiler fallback icon rewrite"
    assert dynamic_rule not in generic
    assert dynamic_rule not in public, "Settings asset rewrite must not affect public origin"
    transformed_asset = DYNAMIC_SOURCE.replace(DYNAMIC_SOURCE, DYNAMIC_TARGET)
    assert transformed_asset == DYNAMIC_TARGET
    assert '||"$safe_ingress_path/"+el.getAttribute("name")' in transformed_asset

    direct_rule = rule(DIRECT_LOGO_SOURCE, DIRECT_LOGO_TARGET)
    escaped_rule = rule(ESCAPED_LOGO_SOURCE, ESCAPED_LOGO_TARGET)
    assert direct_rule in generic, "missing direct get_views logo rewrite"
    assert escaped_rule in generic, "missing JSON-escaped get_views logo rewrite"
    assert direct_rule not in public and escaped_rule not in public

    direct = '<app_settings_block logo="/base/static/description/settings.png">'
    escaped = r'{"arch":"<app_settings_block logo=\"/base/static/description/settings.png\">"}'
    assert direct.replace(DIRECT_LOGO_SOURCE, DIRECT_LOGO_TARGET) == (
        '<app_settings_block logo="$safe_ingress_path/base/static/description/settings.png">'
    )
    assert escaped.replace(ESCAPED_LOGO_SOURCE, ESCAPED_LOGO_TARGET) == (
        r'{"arch":"<app_settings_block logo=\"$safe_ingress_path/base/static/description/settings.png\">"}'
    )


if __name__ == "__main__":
    main()
