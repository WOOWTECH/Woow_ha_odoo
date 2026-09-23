"""Is ``res.users.authenticate`` guarded in this Odoo process? Issues #88, #121.

The build tier pipes this file into ``odoo shell`` in the image it just
built, with no database: by then Odoo's own loader has imported the
server-wide modules the add-on configures. When ``woow_base_url_guard``
cannot find its seam it raises ``ImportError``, and that loader only logs
it and carries on, so asking Odoo whether the patch is on is the one check
that goes red. The probe never imports the guard itself -- that would apply
the patch and pass by itself.

Two things the flag alone does not prove (issue #121):

* the class the guard patched is the one the registry resolves. Odoo builds
  a model from every class declaring its ``_name``, later declarations
  overriding earlier ones, so the ``authenticate`` that runs is the one on
  the last class in ``res_users`` that declares it. A later class the guard
  never saw carries the guess back, flag or no flag;
* the wrapper still fits upstream. ``functools.wraps`` keeps the original
  under ``__wrapped__``; if a nightly changed its parameters the guard still
  installs and every login raises ``TypeError``.

Prints one of ``base-url-guard: applied``, ``base-url-guard: not applied``
or ``base-url-guard: signature mismatch (...)``. Exit status 0 only for the
first.
"""
import inspect
import sys

# Set by woow_base_url_guard on the authenticate it installs.
GUARDED_FLAG = "_woow_base_url_guarded"
MODEL = "res.users"
METHOD = "authenticate"


def registry_users(res_users):
    """The class whose ``authenticate`` the registry's ``res.users`` runs.

    The last class in module order that declares the method in its own
    namespace: Odoo's model class puts later declarations ahead of earlier
    ones in its MRO. A class that only inherits the method changes nothing
    and is skipped. None when nothing in the module declares it, which is
    the seam having moved out of the module.
    """
    resolved = None
    for candidate in vars(res_users).values():
        if not isinstance(candidate, type) or getattr(candidate, "_name", None) != MODEL:
            continue
        if METHOD in vars(candidate):
            resolved = candidate
    return resolved


def guarded(res_users) -> bool:
    """True when the registry's ``authenticate`` is the guarded one."""
    users = registry_users(res_users)
    return users is not None and getattr(users.authenticate, GUARDED_FLAG, False)


def parameter_names(function):
    """Parameter names after the class argument, as the function declares them."""
    signature = inspect.signature(function, follow_wrapped=False)
    return [name for name in signature.parameters][1:]


def signature_mismatch(res_users):
    """A sentence naming the mismatch between the wrapper and upstream, or None.

    The wrapper forwards its parameters by position to the original it
    wrapped; the two lists have to be the same names in the same order.
    """
    users = registry_users(res_users)
    wrapper = vars(users)[METHOD].__func__
    original = getattr(wrapper, "__wrapped__", None)
    if original is None:
        return "the guarded authenticate keeps no __wrapped__ original to compare against"
    forwarded = parameter_names(wrapper)
    upstream = parameter_names(original)
    if forwarded == upstream:
        return None
    return f"wrapper forwards {forwarded}, upstream authenticate takes {upstream}"


def main(res_users, out=sys.stdout) -> int:
    if not guarded(res_users):
        print("base-url-guard: not applied", file=out)
        return 1
    mismatch = signature_mismatch(res_users)
    if mismatch is not None:
        print(f"base-url-guard: signature mismatch ({mismatch})", file=out)
        return 1
    print("base-url-guard: applied", file=out)
    return 0


if __name__ == "__main__":
    from odoo.addons.base.models import res_users

    sys.exit(main(res_users))
