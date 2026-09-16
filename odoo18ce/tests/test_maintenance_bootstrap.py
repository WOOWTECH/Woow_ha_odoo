"""Canonical URL decision matrix for the maintenance bootstrap.

The bootstrap runs once per add-on start, before Odoo serves requests, and
pipes ``rootfs/usr/local/lib/odoo-maintenance.py`` into ``odoo shell`` once
per database. The decision functions in that file are pure, so the whole
matrix -- ``public_url`` set/unset x ``default_db`` set/unset x stored value
clean/leaked/absent x LAN address available/unavailable -- runs here without
a live Odoo or Supervisor.
"""
import importlib.util
import itertools
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "rootfs/usr/local/lib/odoo-maintenance.py"
BOOTSTRAP = ROOT / "rootfs/usr/local/bin/odoo-maintenance-bootstrap"
CONFIG = ROOT / "config.yaml"

PUBLIC = "https://odoo.example.test"
LAN_IPV4 = "192.168.2.6/24"
LEAKED = "https://ha.example.test/api/hassio_ingress/token-value"
CLEAN = "https://kept.example.test"


def load_lib():
    spec = importlib.util.spec_from_file_location("odoo_maintenance", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def lib():
    return load_lib()


# --- Canonical URL choice -----------------------------------------------------

def test_public_url_wins_and_loses_its_trailing_slash(lib) -> None:
    assert lib.canonical_url(PUBLIC + "/", LAN_IPV4, "8069") == PUBLIC
    assert lib.canonical_url("  " + PUBLIC + "  ", None, None) == PUBLIC


def test_lan_fallback_strips_prefix_length_and_uses_published_port(lib) -> None:
    assert lib.canonical_url("", LAN_IPV4, "18069") == "http://192.168.2.6:18069"
    assert lib.canonical_url(None, "192.168.2.6", "8069") == "http://192.168.2.6:8069"


def test_lan_fallback_defaults_to_8069_when_the_port_mapping_is_empty(lib) -> None:
    assert lib.canonical_url("", LAN_IPV4, "") == "http://192.168.2.6:8069"
    assert lib.canonical_url("", LAN_IPV4, None) == "http://192.168.2.6:8069"
    # bashio prints `null` for a JSON null mapping.
    assert lib.canonical_url("", LAN_IPV4, "null") == "http://192.168.2.6:8069"


def test_lan_fallback_takes_the_first_address_only(lib) -> None:
    assert lib.canonical_url("", "192.168.2.6/24\n10.0.0.5/8", "") == "http://192.168.2.6:8069"


def test_no_source_means_no_canonical_url(lib) -> None:
    assert lib.canonical_url("", "", "8069") is None
    assert lib.canonical_url(None, None, None) is None
    assert lib.canonical_url("", "null", "8069") is None


# --- Leak detection -----------------------------------------------------------

@pytest.mark.parametrize("value", [
    LEAKED,
    "http://192.168.2.6:8123/api/hassio_ingress/abc/odoo",
    "/api/hassio_ingress/abc",
])
def test_ingress_token_urls_are_leaked(lib, value) -> None:
    assert lib.is_leaked(value)


@pytest.mark.parametrize("value", [PUBLIC, "http://192.168.2.6:8069", "http://127.0.0.1:8070", "", None, False])
def test_ordinary_or_absent_values_are_not_leaked(lib, value) -> None:
    assert not lib.is_leaked(value)


# --- Per-database decision ----------------------------------------------------

@pytest.mark.parametrize("stored", [CLEAN, LEAKED, "", None, False])
def test_canonical_url_is_written_frozen_and_becomes_the_website_domain(lib, stored) -> None:
    decision = lib.decide(PUBLIC, stored)
    assert decision.action == "write"
    assert decision.base_url == PUBLIC
    assert decision.freeze is True
    assert decision.website_domain == PUBLIC


def test_without_canonical_url_a_clean_stored_value_is_kept_and_frozen(lib) -> None:
    decision = lib.decide(None, CLEAN)
    assert decision.action == "keep"
    assert decision.base_url is None
    assert decision.freeze is True
    assert decision.website_domain is None


@pytest.mark.parametrize("stored", [LEAKED, "", None, False])
def test_without_canonical_url_an_absent_or_leaked_value_is_left_unprotected(lib, stored) -> None:
    decision = lib.decide(None, stored)
    assert decision.action == "unprotected"
    assert decision.base_url is None
    assert decision.freeze is False
    assert decision.website_domain is None


# --- Test account -------------------------------------------------------------

def test_account_needs_default_db_and_keeps_the_file_otherwise(lib) -> None:
    assert lib.account_target("odoo_test", "e2e") == "odoo_test"
    assert lib.account_target("", "e2e") is None
    assert lib.account_target(None, "e2e") is None
    # No file, nothing to do regardless of default_db.
    assert lib.account_target("odoo_test", "") is None


# --- The full matrix ----------------------------------------------------------

STORED = {"clean": CLEAN, "leaked": LEAKED, "absent": False}


@pytest.mark.parametrize(
    "public_url,default_db,stored,lan",
    list(itertools.product([PUBLIC, ""], ["odoo_test", ""], list(STORED), [LAN_IPV4, ""])),
)
def test_decision_matrix(lib, public_url, default_db, stored, lan) -> None:
    canonical = lib.canonical_url(public_url, lan, "8069")
    decision = lib.decide(canonical, STORED[stored])

    if public_url:
        expected_url = PUBLIC
    elif lan:
        expected_url = "http://192.168.2.6:8069"
    else:
        expected_url = None

    if expected_url:
        # Every shape with a Canonical URL writes it, freezes it and mirrors it
        # into the website domain, whatever was stored before.
        assert decision == lib.Decision("write", expected_url, True, expected_url)
    elif stored == "clean":
        assert decision == lib.Decision("keep", None, True, None)
    else:
        assert decision == lib.Decision("unprotected", None, False, None)

    # default_db only governs the test account; the URL lock never needs it.
    assert lib.account_target(default_db, "e2e") == (default_db or None)


# --- Shipped-file contracts ---------------------------------------------------

def test_bootstrap_processes_every_database_and_never_requires_default_db() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")
    assert "pg_database" in script
    assert "ir_config_parameter" in script
    assert "/usr/local/lib/odoo-maintenance.py" in script
    assert "bashio::network.ipv4_address" in script
    assert "bashio::addon.port" in script
    # public_url without default_db used to be a start-up failure.
    assert "default_db is required" not in script
    # The file policy violations stay fatal; everything else exits zero.
    assert "must be owned by root with mode 0600" in script
    assert "must contain at least 20 characters" in script
    assert script.rstrip().endswith("exit 0")


def test_manifest_grants_supervisor_api_for_the_lan_fallback() -> None:
    manifest = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    # The Ingress-only fallback reads the host LAN address from
    # /network/interface/default/info, which needs hassio_api; the default
    # role covers the two /info endpoints, so hassio_role stays unset.
    assert manifest["hassio_api"] is True
    assert "hassio_role" not in manifest
