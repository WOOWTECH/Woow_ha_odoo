#!/usr/bin/env python3
"""Canonical URL lock for one Odoo database.

odoo-maintenance-bootstrap pipes this file into ``odoo shell -d <db>
--no-http`` once per database on every add-on start, before Odoo serves
requests. Inputs arrive in the environment:

    ODOO_MAINT_DB           database name, for the log line only
    ODOO_MAINT_PUBLIC_URL   the public_url option, may be empty
    ODOO_MAINT_LAN_IPV4     host LAN address from the Supervisor, may be empty
    ODOO_MAINT_PORT         host port mapped to 8069/tcp, may be empty

The functions above ``apply`` are pure so the static tier can run the full
decision matrix (tests/test_maintenance_bootstrap.py) without Odoo or the
Supervisor.
"""
import os
import sys
from typing import NamedTuple, Optional

BASE_URL_KEY = "web.base.url"
FREEZE_KEY = "web.base.url.freeze"
INGRESS_MARKER = "/api/hassio_ingress/"
DEFAULT_PORT = "8069"


def _text(value) -> str:
    """bashio prints ``null`` for a JSON null; treat it like empty."""
    text = (value or "").strip() if isinstance(value, str) else ""
    return "" if text == "null" else text


def canonical_url(public_url, lan_ipv4, published_port) -> Optional[str]:
    """The URL to lock this start: public_url, else the host LAN origin, else None."""
    public_url = _text(public_url).rstrip("/")
    if public_url:
        return public_url
    # The Supervisor reports "192.168.2.6/24", possibly one address per line.
    lan_ipv4 = _text(lan_ipv4).splitlines()[0].strip().split("/")[0] if _text(lan_ipv4) else ""
    if not lan_ipv4:
        return None
    return f"http://{lan_ipv4}:{_text(published_port) or DEFAULT_PORT}"


def is_leaked(value) -> bool:
    """A stored value carrying an Ingress token is never kept."""
    return isinstance(value, str) and INGRESS_MARKER in value


class Decision(NamedTuple):
    action: str  # "write" | "keep" | "unprotected"
    base_url: Optional[str]  # value to write into web.base.url, None leaves it
    freeze: bool  # set web.base.url.freeze = True
    website_domain: Optional[str]  # value for the default website, None leaves it


def decide(canonical, stored) -> Decision:
    if canonical:
        return Decision("write", canonical, True, canonical)
    if stored and not is_leaked(stored):
        return Decision("keep", None, True, None)
    return Decision("unprotected", None, False, None)


def account_target(default_db, login) -> Optional[str]:
    """The maintenance account is created only in default_db."""
    if not _text(login) or not _text(default_db):
        return None
    return _text(default_db)


def apply(env, db_name: str, canonical: Optional[str]) -> Decision:
    params = env["ir.config_parameter"].sudo()
    stored = params.get_param(BASE_URL_KEY) or ""
    decision = decide(canonical, stored)

    if decision.base_url:
        params.set_param(BASE_URL_KEY, decision.base_url)
    if decision.freeze:
        params.set_param(FREEZE_KEY, "True")

    domain_note = "website module not installed"
    if decision.website_domain:
        if "website" in env.registry:
            website = env.ref("website.default_website", raise_if_not_found=False)
            if not website:
                website = env["website"].sudo().search([], order="id", limit=1)
            if website:
                website.sudo().write({"domain": decision.website_domain})
                domain_note = f"website.domain={decision.website_domain}"
            else:
                domain_note = "no website record"
    else:
        domain_note = "website.domain unchanged"

    if decision.action == "write":
        summary = f"{BASE_URL_KEY}={decision.base_url} {FREEZE_KEY}=True {domain_note}"
    elif decision.action == "keep":
        summary = f"no Canonical URL; {BASE_URL_KEY}={stored} kept and {FREEZE_KEY}=True"
    else:
        summary = (
            f"WARNING no Canonical URL and the stored {BASE_URL_KEY} is "
            f"{'leaked' if is_leaked(stored) else 'absent'}; the value is unprotected"
        )
    print(f"maintenance db={db_name}: {summary}", flush=True)
    return decision


if __name__ == "__main__":
    # `odoo shell` executes stdin with __name__ == "__main__" and `env` bound
    # to the database named by -d.
    apply(
        env,  # noqa: F821 - injected by odoo shell
        os.environ.get("ODOO_MAINT_DB", "?"),
        canonical_url(
            os.environ.get("ODOO_MAINT_PUBLIC_URL"),
            os.environ.get("ODOO_MAINT_LAN_IPV4"),
            os.environ.get("ODOO_MAINT_PORT"),
        ),
    )
    env.cr.commit()  # noqa: F821
    sys.stdout.flush()
