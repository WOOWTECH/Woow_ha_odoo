"""Is ``website.visitor._handle_webpage_dispatch`` patched in this Odoo? Issue #160.

The build tier pipes this file into ``odoo shell`` in the image it just
built, with no database: by then Odoo's own loader has imported the
server-wide modules the add-on configures. When ``woow_visitor_url`` cannot
find its seam, or cannot import ``website`` at all, that loader only logs it
and carries on, so asking Odoo whether the patch is on is the one check that
goes red. The probe never imports the module itself -- that would apply the
patch and pass by itself.

What the flag alone would not prove -- the two things ADR 0010's amendment
named for the Canonical URL guard (issue #121), and the one the reopened #160
adds:

* the class the module patched is the last one in ``website_visitor``
  declaring ``_handle_webpage_dispatch``. Odoo builds a model from every
  class declaring its ``_name``, later declarations overriding earlier ones,
  so within that module the last declaration is the one the registry runs.
  Overrides in other modules are not read here: the tracked URL is built in
  ``website_visitor``, and an override elsewhere reaches it through
  ``super()``;
* the wrapper still fits upstream. ``functools.wraps`` keeps the original
  under ``__wrapped__``; if a nightly changed its parameters the patch still
  installs and every tracked page view raises ``TypeError``;
* the swap the patch performs takes on the request Odoo builds. This is the
  half issue #160 was reopened over: the flag was on the host and every
  Ingress page view still recorded the Home Assistant host, because
  ``odoo.http.HTTPRequest`` forwards ``url`` through a plain ``property`` that
  never reads the instance ``__dict__``. A flag cannot see that; building this
  image's own ``request`` and replacing the url on it can.

Prints one of ``visitor-url: applied``, ``visitor-url: not applied``,
``visitor-url: signature mismatch (...)``, ``visitor-url: url not replaceable
(...)`` or ``visitor-url: url swap unprovable (...)``. Exit status 0 only for
the first.
"""
import inspect
import sys

# Set by woow_visitor_url on the dispatch it installs.
PATCHED_FLAG = "_woow_visitor_url_patched"
MODEL = "website.visitor"
METHOD = "_handle_webpage_dispatch"
# The attribute the patch replaces for the length of one dispatch.
URL_ATTRIBUTE = "url"
# A complete, minimal WSGI environ: enough for werkzeug to compute a url and
# for Odoo's wrapper to be built over it, with no server, no database and no
# request behind it. The port is not the scheme's default, so the url werkzeug
# computes from it carries one and cannot be mistaken for the replacement.
PROBE_ENVIRON = {
    "wsgi.url_scheme": "http",
    "REQUEST_METHOD": "GET",
    "SERVER_NAME": "probe.invalid",
    "SERVER_PORT": "8069",
    "SCRIPT_NAME": "",
    "PATH_INFO": "/probe",
    "QUERY_STRING": "",
}
REPLACEMENT = "https://canonical.invalid/probe"
# The two ways the replacement can fail, kept apart because the build step says
# something different about each: the first is a request that changed shape and
# tells nothing about the patch, the second is a page view that would record
# the Home Assistant host.
UNPROVABLE = "url swap unprovable"
NOT_REPLACEABLE = "url not replaceable"


def registry_visitor(website_visitor):
    """The class whose ``_handle_webpage_dispatch`` the registry's
    ``website.visitor`` runs, among those declared in Odoo's
    ``website_visitor`` module.

    The last class in module order that declares the method in its own
    namespace: Odoo's model class puts later declarations ahead of earlier
    ones in its MRO. A class that only inherits the method changes nothing
    and is skipped. None when nothing in the module declares it, which is
    the seam having moved out of the module.
    """
    resolved = None
    for candidate in vars(website_visitor).values():
        if not isinstance(candidate, type) or getattr(candidate, "_name", None) != MODEL:
            continue
        if METHOD in vars(candidate):
            resolved = candidate
    return resolved


def patched(website_visitor) -> bool:
    """True when the registry's dispatch is the patched one."""
    visitor = registry_visitor(website_visitor)
    return visitor is not None and getattr(vars(visitor)[METHOD], PATCHED_FLAG, False)


def forwarded_names(wrapper):
    """The positional parameters the wrapper declares, after ``self``.

    Read from the code object: ``functools.wraps`` copies the original's
    ``__dict__`` onto the wrapper, and a ``__signature__`` in there would
    make ``inspect.signature`` describe the original instead of the wrapper.
    """
    code = wrapper.__code__
    return list(code.co_varnames[1:code.co_argcount])


def upstream_fit(forwarded, original):
    """A sentence naming how the original does not take what the wrapper
    forwards by position, or None when every call the wrapper makes is one
    the original accepts.

    Each forwarded name has to be the original's next positional parameter
    (same name, same order, accepted by position). Parameters the original
    takes beyond those have to be optional, or it would want more than the
    wrapper sends.
    """
    positional = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    upstream = list(inspect.signature(original).parameters.values())[1:]

    def describe(p):
        if p.kind is p.VAR_POSITIONAL:
            return f"*{p.name}"
        if p.kind is p.VAR_KEYWORD:
            return f"**{p.name}"
        name = p.name if p.default is p.empty else f"{p.name}={p.default!r}"
        return f"{name} (keyword-only)" if p.kind is p.KEYWORD_ONLY else name

    taken = [describe(p) for p in upstream]
    described = (
        f"wrapper forwards {forwarded} by position, upstream {METHOD} takes {taken}"
    )
    for index, name in enumerate(forwarded):
        if index >= len(upstream):
            return described
        parameter = upstream[index]
        if parameter.name != name or parameter.kind not in positional:
            return described
    for parameter in upstream[len(forwarded):]:
        if parameter.kind in positional and parameter.default is parameter.empty:
            return described
        if parameter.kind is parameter.KEYWORD_ONLY and parameter.default is parameter.empty:
            return described
    return None


def signature_mismatch(website_visitor):
    """A sentence naming the mismatch between the wrapper and upstream, or None."""
    wrapper = vars(registry_visitor(website_visitor))[METHOD]
    original = getattr(wrapper, "__wrapped__", None)
    if original is None:
        return f"the patched {METHOD} keeps no __wrapped__ original to compare against"
    return upstream_fit(forwarded_names(wrapper), original)


def probe_request(http):
    """``(request, None)``, or ``(None, sentence)`` saying why it cannot be built.

    The two steps Odoo's WSGI application takes: the werkzeug request is
    wrapped in an ``odoo.http.HTTPRequest``, and that wrapper is handed to
    ``odoo.http.Request``, which is the object every module reads as
    ``odoo.http.request``. Building both is what lets the swap below run on
    the expression the patch evaluates -- ``request.httprequest`` -- rather
    than on a class this file names. Nothing here needs a database, a session
    or the network, and every step is reported rather than raised, because a
    probe that dies prints no ``visitor-url:`` line and the build then blames
    the container instead of what it found.
    """
    for attribute in ("HTTPRequest", "Request"):
        if not hasattr(http, attribute):
            return None, f"odoo.http has no {attribute}; the request it builds cannot be read here"
    try:
        return http.Request(http.HTTPRequest(dict(PROBE_ENVIRON))), None
    except Exception as exc:
        return None, f"odoo.http.Request could not be built over a bare environ: {exc!r}"


def url_swap(http):
    """``(None, None)`` when the url replacement the patch performs takes here,
    and ``(verdict, sentence)`` when it does not.

    The verdict tells apart the two ways this can fail, because they mean
    different things to whoever reads the build:

    * ``"url swap unprovable"`` -- this Odoo could not be asked. Its
      ``odoo.http`` no longer has what the probe reads, or its request cannot
      be built over a bare environ, or its url cannot be read. A nightly
      changed the shape of the request; nothing is known about the patch.
    * ``"url not replaceable"`` -- it was asked and the swap did not take, so a
      page view would record the address the request arrived on. This is the
      0.4.6 defect, and the half issue #160 was reopened over.

    ``http`` is Odoo's ``odoo.http``. What the dispatch reads is
    ``request.httprequest``, an ``odoo.http.HTTPRequest``: a wrapper that
    installs one plain ``property`` per forwarded attribute, ``url`` included,
    whose getter and setter reach the werkzeug request it wraps
    (``make_request_wrap_methods``). The patch assigns to that attribute, so
    this builds the request over a bare environ and asks it to read the
    assignment back.

    What it does not read is Odoo's WSGI application putting that wrapper on
    the request in the first place. If a nightly interposes something else
    there, this stays green and the module's own read-back guard catches it at
    runtime -- a warning per page view, which is what the host logged on 0.4.6.
    """
    request, unbuildable = probe_request(http)
    if unbuildable is not None:
        return UNPROVABLE, unbuildable
    httprequest = request.httprequest
    name = f"request.httprequest ({type(httprequest).__module__}.{type(httprequest).__qualname__})"
    try:
        arrived = getattr(httprequest, URL_ATTRIBUTE)
    except Exception as exc:
        return UNPROVABLE, f"{name}.{URL_ATTRIBUTE} could not be read: {exc!r}"
    try:
        setattr(httprequest, URL_ATTRIBUTE, REPLACEMENT)
    except Exception as exc:
        return NOT_REPLACEABLE, f"{name}.{URL_ATTRIBUTE} takes no assignment: {exc!r}"
    replaced = getattr(httprequest, URL_ATTRIBUTE, None)
    if replaced != REPLACEMENT:
        return NOT_REPLACEABLE, (
            f"{name}.{URL_ATTRIBUTE} was assigned {REPLACEMENT!r} and reads back "
            f"{replaced!r} (it arrived as {arrived!r}); a page view would record the "
            "address the request arrived on"
        )
    return None, None


def main(website_visitor, http, out=sys.stdout) -> int:
    if not patched(website_visitor):
        print("visitor-url: not applied", file=out)
        return 1
    mismatch = signature_mismatch(website_visitor)
    if mismatch is not None:
        print(f"visitor-url: signature mismatch ({mismatch})", file=out)
        return 1
    verdict, sentence = url_swap(http)
    if verdict is not None:
        print(f"visitor-url: {verdict} ({sentence})", file=out)
        return 1
    print("visitor-url: applied", file=out)
    return 0


if __name__ == "__main__":
    import odoo.http
    from odoo.addons.website.models import website_visitor

    sys.exit(main(website_visitor, odoo.http))
