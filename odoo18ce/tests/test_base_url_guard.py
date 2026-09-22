#!/usr/bin/env python3
"""The base-URL guard: Odoo never writes the Canonical URL by itself.

``woow_base_url_guard`` ships inside the image and is named in
``server_wide_modules``, so Odoo imports it in every process and installs it
in no database. Both halves run here without a live Odoo: ``guard.py``
imports nothing, and the patch in ``__init__.py`` is applied to a stand-in
of the ``res.users`` class Odoo declares, carrying the guess this issue
removes.
"""
import ast
import importlib
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_ADDONS = ROOT / "rootfs/opt/woow-server-addons"
MODULE_NAME = "woow_base_url_guard"
MODULE = SERVER_ADDONS / MODULE_NAME

BASE_URL_KEY = "web.base.url"
FREEZE_KEY = "web.base.url.freeze"
# What Odoo derives from an Ingress request: the Home Assistant host, never
# the Canonical URL. Documentation host only.
BASE_LOCATION = "http://ha.example.test:8123"
CREDENTIAL = {"login": "admin", "type": "password", "password": "static-tier-placeholder"}
# Identity, not equality, is asserted on this: the guard hands back whatever
# Odoo returned, untouched.
AUTH_INFO = {"uid": 2, "auth_method": "password", "mfa": "default"}


def load_guard():
    spec = importlib.util.spec_from_file_location(MODULE_NAME + "_guard", MODULE / "guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# guard.py has to be importable without Odoo; loading it here is the proof.
guard = load_guard()


class FakeConfigParameters:
    """Just enough ``ir.config_parameter`` to observe the guess."""

    def __init__(self, params=None):
        self.params = dict(params or {})
        self.writes = []

    def get_param(self, key, default=False):
        return self.params.get(key, default)

    def set_param(self, key, value):
        self.writes.append((key, value))
        self.params[key] = value


def odoo_users(params=None):
    """Odoo res.users, guess included, as two classes and a parameter store.

    Transcribed from the source read on the `.6` host (18.0 nightly
    20260914): once ``_login`` has succeeded for a ``base.group_system``
    user, a ``base_location`` in ``user_agent_env`` is written into
    ``web.base.url`` unless ``web.base.url.freeze`` is set.

    Odoo declares one class and builds a subclass of it per database; only
    that subclass carries ``pool``, and the original reaches it through the
    ``cls`` it is called with. Returned are the declared class (what the
    guard patches), the registry subclass (what callers use) and the
    parameter store.
    """
    icp = FakeConfigParameters(params)
    calls = []

    class Users:
        _name = "res.users"
        pool = None
        calls_seen = calls
        config_parameters = icp

        @classmethod
        def authenticate(cls, db, credential, user_agent_env):
            assert cls.pool is not None, "authenticate must run on the registry class"
            calls.append((db, credential, user_agent_env))
            if user_agent_env and user_agent_env.get("base_location"):
                if not icp.get_param(FREEZE_KEY):
                    icp.set_param(BASE_URL_KEY, user_agent_env["base_location"])
            return AUTH_INFO

    class Registry(Users):
        pool = object()

    return Users, Registry, icp


def install_guard(declared):
    """Import the shipped ``__init__.py`` against a stand-in ``res.users``.

    The module patches at import time, so the import is the patch. The fake
    ``odoo`` package and the module itself are removed from ``sys.modules``
    again, leaving the rest of the run untouched.
    """
    res_users = types.ModuleType("odoo.addons.base.models.res_users")

    class Groups:  # a class in the same namespace that is not res.users
        _name = "res.groups"

    class UsersView(declared):  # inherits authenticate, declares none
        _name = "res.users"

    res_users.Groups = Groups
    res_users.Users = declared
    res_users.UsersView = UsersView

    fakes = {"odoo.addons.base.models.res_users": res_users}
    for name in ["odoo", "odoo.addons", "odoo.addons.base", "odoo.addons.base.models"]:
        fakes[name] = types.ModuleType(name)
    sys.modules.update(fakes)
    sys.path.insert(0, str(SERVER_ADDONS))
    try:
        return importlib.import_module(MODULE_NAME)
    finally:
        sys.path.remove(str(SERVER_ADDONS))
        for name in list(sys.modules):
            if name in fakes or name == MODULE_NAME or name.startswith(MODULE_NAME + "."):
                del sys.modules[name]


def ingress_env():
    return {"interactive": True, "base_location": BASE_LOCATION}


# --- The stand-in earns its place -------------------------------------------

def test_the_stand_in_reproduces_the_gap_when_nothing_guards_it() -> None:
    _, registry, icp = odoo_users()
    assert registry.authenticate("odoo_test", CREDENTIAL, ingress_env()) is AUTH_INFO
    assert icp.writes == [(BASE_URL_KEY, BASE_LOCATION)]


def test_the_stand_in_respects_the_freeze_like_odoo_does() -> None:
    _, registry, icp = odoo_users({FREEZE_KEY: True})
    registry.authenticate("odoo_test", CREDENTIAL, ingress_env())
    assert icp.writes == []


# --- The patched login path --------------------------------------------------

def test_the_patched_login_writes_no_base_url_and_returns_the_auth_info_unchanged() -> None:
    declared, registry, icp = odoo_users()
    install_guard(declared)
    # A database created between two starts carries no freeze; the guess
    # still never happens.
    result = registry.authenticate("odoo_test", CREDENTIAL, ingress_env())
    assert icp.writes == []
    assert icp.params == {}
    assert result is AUTH_INFO


def test_the_patched_login_delegates_everything_but_the_guess_input() -> None:
    declared, registry, _ = odoo_users()
    install_guard(declared)
    registry.authenticate("odoo_test", CREDENTIAL, user_agent_env=ingress_env())
    (db, credential, user_agent_env), = declared.calls_seen
    assert db == "odoo_test"
    assert credential is CREDENTIAL
    # The rest of the environment reaches Odoo untouched: auth_totp reads
    # `interactive` from it.
    assert user_agent_env == {"interactive": True}


def test_the_patch_is_applied_once_and_finds_the_class_that_declares_the_method() -> None:
    declared, registry, _ = odoo_users()
    module = install_guard(declared)
    assert module.users_class() is declared
    # A second pass over an already guarded class must not wrap the wrapper.
    assert module.patch_authenticate(declared) is False
    registry.authenticate("odoo_test", CREDENTIAL, ingress_env())
    assert declared.config_parameters.writes == []


# --- The decision itself -----------------------------------------------------

def test_the_guard_leaves_the_caller_environment_alone() -> None:
    env = ingress_env()
    assert guard.without_base_location(env) == {"interactive": True}
    assert env == ingress_env(), "the caller dict must not be mutated"


def test_an_environment_without_a_base_location_passes_through_untouched() -> None:
    env = {"interactive": True}
    assert guard.without_base_location(env) is env
    assert guard.without_base_location({}) == {}
    assert guard.without_base_location(None) is None


def test_an_empty_base_location_is_still_dropped() -> None:
    # Odoo skips the guess for a falsy base_location, so this only has to
    # stay harmless -- the key is gone either way.
    assert guard.without_base_location({"base_location": ""}) == {}


# --- What the image ships ----------------------------------------------------

def test_the_patch_is_applied_at_import_time_not_through_an_inherit() -> None:
    source = (MODULE / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # A server-wide module is installed in no database, so an ORM class --
    # an _inherit on res.users -- would never take effect here.
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)], (
        "the guard patches the res.users class; it must not declare an ORM class"
    )
    assert "classmethod(" in source, "authenticate is a classmethod and has to stay one"
    # The patch runs while the module is imported, not from a hook that only
    # a database install would reach: a statement, not just a definition,
    # has to call it.
    statements = [node for node in tree.body if not isinstance(node, ast.FunctionDef)]
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "patch_authenticate"
        for node in statements
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    ), "__init__.py must call patch_authenticate at module level"


def test_the_manifest_declares_a_module_that_is_never_installed() -> None:
    manifest = ast.literal_eval((MODULE / "__manifest__.py").read_text(encoding="utf-8"))
    assert manifest["depends"] == ["base"]
    assert manifest["installable"] is True
    assert manifest["auto_install"] is False
    # Nothing to install: no models, no data, no views.
    assert "data" not in manifest
    assert manifest["category"] == "Hidden"
    assert manifest["license"] == "LGPL-3"
