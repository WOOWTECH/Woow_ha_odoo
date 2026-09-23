"""Is ``res.users.authenticate`` guarded in this Odoo process? Issue #88.

The build tier pipes this file into ``odoo shell`` in the image it just
built, with no database: by then Odoo's own loader has imported the
server-wide modules the add-on configures. When ``woow_base_url_guard``
cannot find its seam it raises ``ImportError``, and that loader only logs
it and carries on, so asking Odoo whether the patch is on is the one check
that goes red. The probe never imports the guard itself -- that would apply
the patch and pass by itself.

Prints ``base-url-guard: applied`` or ``base-url-guard: not applied``.
"""

# Set by woow_base_url_guard on the authenticate it installs.
GUARDED_FLAG = "_woow_base_url_guarded"


def guarded(res_users) -> bool:
    """True when a ``res.users`` class in Odoo's module resolves a guarded
    ``authenticate``. A seam that moved out of the module leaves none."""
    for candidate in vars(res_users).values():
        if not isinstance(candidate, type) or getattr(candidate, "_name", None) != "res.users":
            continue
        if getattr(getattr(candidate, "authenticate", None), GUARDED_FLAG, False):
            return True
    return False


if __name__ == "__main__":
    from odoo.addons.base.models import res_users

    print("base-url-guard: " + ("applied" if guarded(res_users) else "not applied"))
