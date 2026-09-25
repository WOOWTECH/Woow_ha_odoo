#!/usr/bin/env python3
"""Shared-layer parity run: groups F, A, B, C and D of the parity plan (#143).

The menu crawler (`e2e_menu_action_adapter.py`) opens every menu and only
reads. This run does what a person does on a screen -- copy, download,
upload, fill a form, chat -- once on the Public origin and once inside the
Home Assistant panel, and writes one `odoo-parity-evidence/v1` record per
check (item x screen). Each record holds both surfaces and a verdict; a
conservation report (parity plan section 12) says whether the run is
complete.

Two kinds of screen per item: `generic`, the item on an ordinary screen, and
the module-specific screens the parity plan section 10 names for it
(`MODULE_SCREENS`). A check the run cannot do is recorded `NOT-RUN` with
what blocks it, so a skipped screen is visible instead of missing.

The pure parts are tested in the static tier by
test_e2e_parity_shared_layers.py; the Live part is in
e2e_parity_shared_layers_live.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from e2e_menu_action_adapter import CLIENT, EVIDENCE_SCHEMA, SIGNALS, RunInfo, Surface

VERDICTS = ("PARITY", "GAP", "APPROVED-DIVERGENCE", "STRUCTURAL")
NOT_RUN = "NOT-RUN"
SEVERITIES = ("blocker", "important", "minor", "none")


@dataclass(frozen=True)
class Item:
    id: str
    group: str
    layer: str
    root_cause: tuple[str, ...]
    title: str


def _items(group: str, layer: str, rows: Sequence[tuple[str, str, str]]) -> list[Item]:
    return [Item(item, group, layer, tuple(rc.split("/")) if rc else (), title) for item, rc, title in rows]


def _rc(text: str) -> str:
    """`RC-1/11` -> `RC-1/RC-11`, the way the plan's tables abbreviate them."""
    parts = text.split("/")
    return "/".join(part if part.startswith(("RC-", "AD-")) else "RC-" + part for part in parts)


# Parity plan section 6. Group E is run by e2e_parity_outbound.py (#145).
CATALOG: Mapping[str, Item] = {item.id: item for item in [
    *_items("F", "L0/L2", [
        ("U-F1", "RC-3", "iframe allow capability list"),
        ("U-F2", "RC-13", "HA keyboard shortcut conflicts"),
        ("U-F3", "RC-13", "HA theme and size"),
        ("U-F4", "RC-13", "Supervisor limits"),
        ("U-F5", "RC-3", "downloads"),
    ]),
    *_items("A", "L0/L1", [
        ("U-A1", "RC-1", "no route escape"),
        ("U-A2", "RC-2", "no doubled prefix"),
        ("U-A3", _rc("RC-1/11"), "assets all 200"),
        ("U-A4", "RC-11", "route prefix whitelist completeness"),
        ("U-A5", "RC-14", "content-type rewrite"),
        ("U-A6", "RC-12", "shim injection paths"),
        ("U-A7", "RC-5", "compression and cache"),
        ("U-A8", "RC-13", "large upload limit"),
        ("U-A9", _rc("RC-5/13"), "long request"),
        ("U-A10", "RC-1", "error pages"),
    ]),
    *_items("B", "L2", [
        ("U-B1", "RC-4", "log in, log out, log in again"),
        ("U-B2", "RC-4", "cookie attributes"),
        ("U-B3", "RC-15", "reload and deep link"),
        ("U-B4", "RC-1", "back and forward"),
        ("U-B5", _rc("RC-4/7"), "two tabs"),
        ("U-B6", "RC-13", "host session timeout recovery"),
        ("U-B7", "RC-9", "permissions"),
        ("U-B8", "AD-6", "anonymous boundary"),
    ]),
    *_items("C", "L3", [
        ("U-C1", "RC-1", "all view types"),
        ("U-C2", "RC-1", "control panel"),
        ("U-C3", _rc("RC-1/3"), "form widgets"),
        ("U-C4", "RC-3", "copy to clipboard"),
        ("U-C5", "RC-9", "URL field values"),
        ("U-C6", _rc("RC-1/12"), "HTML editor"),
        ("U-C7", _rc("RC-1/3"), "binary upload, download, preview"),
        ("U-C8", "RC-3", "drag and drop upload"),
        ("U-C9", _rc("RC-1/8"), "chatter"),
        ("U-C10", _rc("RC-1/14"), "dialogs"),
        ("U-C11", "RC-1", "systray"),
        ("U-C12", "RC-1", "app launcher and menu tree"),
        ("U-C13", "RC-1", "breadcrumbs"),
        ("U-C14", _rc("RC-3/13"), "command palette"),
        ("U-C15", "RC-3", "keyboard and focus"),
        ("U-C16", "RC-1", "record operations"),
        ("U-C17", "RC-1", "action and gear menus"),
        ("U-C18", "RC-3", "export"),
        ("U-C19", _rc("RC-1/3"), "import"),
        ("U-C20", _rc("RC-3/9"), "print report"),
        ("U-C21", "RC-1", "notification toasts"),
        ("U-C22", "RC-1", "translation editing"),
        ("U-C23", "RC-15", "open in a new tab"),
        ("U-C24", "RC-3", "fullscreen"),
        ("U-C25", "RC-3", "camera and barcode scan"),
        ("U-C26", _rc("RC-7/8"), "live messages (bus)"),
        ("U-C27", "RC-6", "service worker features"),
    ]),
    *_items("D", "L4", [
        ("U-D1", "RC-1", "website layout"),
        ("U-D2", _rc("RC-1/12/14"), "website editor"),
        ("U-D3", "RC-1", "page lifecycle"),
        ("U-D4", "RC-1", "portal tiles and lists"),
        ("U-D5", _rc("RC-9/10"), "portal access link"),
        ("U-D6", _rc("RC-1/10"), "front-end form"),
        ("U-D7", "RC-10", "anonymous front end"),
        ("U-D8", "RC-9", "SEO outputs"),
    ]),
    *_items("E", "L5", [
        ("U-E1", "RC-9", "web.base.url survives an Ingress login"),
        ("U-E2", "RC-9", "links in outgoing mail"),
        ("U-E3", "RC-9", "share link fields"),
        ("U-E4", "RC-9", "links and QR codes in reports"),
        ("U-E5", "RC-9", "absolute attachment URLs"),
        ("U-E6", "RC-10", "external callback entries"),
        ("U-E7", "RC-9", "URLs in exported files"),
    ]),
]}

# Issue #143's comment: parity plan section 10 screens a generic run misses.
MODULE_SCREENS: tuple[tuple[str, str, str], ...] = (
    ("U-C24", "mrp", "MRP work center"),
    ("U-C24", "hr_attendance", "attendance kiosk mode"),
    ("U-C25", "point_of_sale", "POS product scan"),
    ("U-C25", "mrp", "MRP work order scan"),
    ("U-C25", "hr_attendance", "attendance kiosk badge scan"),
    ("U-C25", "event", "event registration desk"),
    ("U-C4", "survey", "survey share dialog"),
    ("U-C26", "im_livechat", "live chat operator view"),
    ("U-D5", "sale_management", "quotation portal link"),
    ("U-D6", "event", "event registration"),
    ("U-D6", "hr_recruitment", "job application"),
    ("U-D6", "survey", "survey fill"),
    ("U-D7", "website_sale", "/shop"),
    ("U-D7", "hr_recruitment", "/jobs"),
    ("U-D7", "event", "/event"),
    ("U-B2", "website_sale", "/shop/cart"),
    ("U-F5", "point_of_sale", "POS receipt print"),
)


def planned_checks() -> list[tuple[str, str, str]]:
    """Every item of groups F, A, B, C, D once on a generic screen, then each module screen."""
    return [(item, "shared", "generic") for item, entry in CATALOG.items() if entry.group != "E"] + list(MODULE_SCREENS)


def check_identity(item: str, module: str, screen: str) -> str:
    return "check:%s|%s|%s" % (item, module, screen)


@dataclass(frozen=True)
class Outcome:
    """What one surface did for one check."""

    available: bool
    result: str
    signals: Mapping[str, int] = field(default_factory=dict)
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_block(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "result": self.result,
            "signals": {name: int(self.signals.get(name, 0)) for name in SIGNALS},
            "details": dict(self.details),
        }


def judge(public: Outcome, ingress: Outcome) -> tuple[str, str, list[str]]:
    """Section 1.1 for one check: the same result and no signals on either side."""
    reasons: list[str] = []
    blocker = False
    for name, outcome in (("public", public), ("ingress", ingress)):
        if not outcome.available:
            reasons.append("%s unavailable: %s" % (name, outcome.result))
            blocker = True
    for name, outcome in (("public", public), ("ingress", ingress)):
        for signal in SIGNALS:
            count = int(outcome.signals.get(signal, 0))
            if count:
                reasons.append("%s %s=%d" % (name, signal, count))
                blocker = blocker or signal == "route_escape"
    if public.available and ingress.available and public.result != ingress.result:
        reasons.append("result: public=%s ingress=%s" % (public.result, ingress.result))
    if not reasons:
        return "PARITY", "none", []
    return "GAP", ("blocker" if blocker else "important"), reasons


def check_record(
    run: RunInfo,
    item: str,
    *,
    module: str,
    screen: str,
    public: Outcome | None,
    ingress: Outcome | None,
    verdict: str | None = None,
    severity: str | None = None,
    notes: str = "",
    public_path: str | None = None,
    blocked_by: str | None = None,
    route: str | None = None,
    model: str | None = None,
    artifacts: Sequence[str] = (),
) -> dict[str, Any]:
    """One check as an `odoo-parity-evidence/v1` record with both surfaces."""
    entry = CATALOG[item]
    if verdict is None:
        if public is None or ingress is None:
            raise ValueError("%s: a check without both outcomes needs a verdict" % item)
        verdict, severity, reasons = judge(public, ingress)
        notes = "; ".join(filter(None, [notes, *reasons]))
    if verdict not in VERDICTS + (NOT_RUN,):
        raise ValueError("unknown verdict %r" % verdict)
    if verdict == "STRUCTURAL" and not public_path:
        raise ValueError("%s: a STRUCTURAL verdict must name the Public origin path that carries it" % item)
    if verdict == NOT_RUN:
        if not blocked_by:
            raise ValueError("%s: a NOT-RUN check must name what blocks it (blocked_by)" % item)
        severity = None
    elif severity not in SEVERITIES:
        raise ValueError("%s: severity must be one of %s" % (item, ", ".join(SEVERITIES)))
    record: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "run_id": run.run_id,
        "target": run.target,
        "database": run.database,
        "client": run.client or CLIENT,
        "layer": entry.layer,
        "item": item,
        "root_cause": list(entry.root_cause),
        "module": module,
        "screen": {"route": route, "model": model, "view": None, "name": screen},
        "control_identity": check_identity(item, module, screen),
        "public": public and public.as_block(),
        "ingress": ingress and ingress.as_block(),
        "verdict": verdict,
        "severity": severity,
        "artifacts": list(artifacts),
        "notes": notes,
    }
    if public_path:
        record["public_path"] = public_path
    if blocked_by:
        record["blocked_by"] = blocked_by
    return record


# --- U-F1 -------------------------------------------------------------------

# The browser grants these only to a secure context (https or localhost).
_SECURE_ONLY = ("clipboard-write", "camera", "microphone")
_POLICY_FEATURES = ("clipboard-write", "fullscreen", "camera", "microphone")


def capability_upper_bound(
    frame_attrs: Mapping[str, Any], allowed_features: Iterable[str], *, secure_context: bool,
) -> dict[str, dict[str, Any]]:
    """The U-F1 list: what the Ingress frame may do, and what stops the rest.

    It bounds U-C4, U-C24, U-C25 and U-F5: a feature the frame's policy or
    sandbox withholds cannot be fixed inside Odoo; one withheld only for an
    insecure context comes back on an https entrance.
    """
    allowed = set(allowed_features)
    bound: dict[str, dict[str, Any]] = {}
    for feature in _POLICY_FEATURES:
        policy = feature in allowed
        limit = None
        if not policy:
            limit = "iframe policy"
        elif feature in _SECURE_ONLY and not secure_context:
            limit = "insecure context"
        bound[feature] = {"policy": policy, "usable": limit is None, "limit": limit}
    sandbox = frame_attrs.get("sandbox")
    downloads = sandbox is None or "allow-downloads" in str(sandbox).split()
    bound["downloads"] = {"policy": downloads, "usable": downloads, "limit": None if downloads else "iframe sandbox"}
    return bound


# --- U-B2 -------------------------------------------------------------------


def session_cookie_problems(
    cookie: Mapping[str, Any] | None, *, surface: Surface, ingress_prefix: str | None, https: bool,
) -> list[str]:
    """How `session_id` differs from the attributes the plan's U-B2 expects."""
    if not cookie:
        return ["no session_id cookie"]
    if surface is Surface.HA_INGRESS:
        expected = {"path": "%s/" % ingress_prefix, "secure": https}
    else:
        expected = {"path": "/", "secure": True}
    expected.update(httpOnly=True, sameSite="Lax")
    labels = {"path": "Path", "secure": "Secure", "httpOnly": "HttpOnly", "sameSite": "SameSite"}
    return [
        "%s=%s (expected %s)" % (labels[key], cookie.get(key), value)
        for key, value in expected.items()
        if cookie.get(key) != value
    ]


# --- Section 12 -------------------------------------------------------------


def attach_issues(records: Iterable[Mapping[str, Any]], issues: Mapping[str, int]) -> list[dict[str, Any]]:
    """Record the issue filed for each GAP, keyed by control identity."""
    out = []
    known = set()
    for record in records:
        record = dict(record)
        number = issues.get(record["control_identity"])
        if number is not None:
            if record["verdict"] != "GAP":
                raise ValueError("%s is not a GAP (%s)" % (record["control_identity"], record["verdict"]))
            record["issue"] = "#%d" % number
            known.add(record["control_identity"])
        out.append(record)
    unknown = set(issues) - known
    if unknown:
        raise ValueError("no record for %s" % ", ".join(sorted(unknown)))
    return out


def conservation(records: Iterable[Mapping[str, Any]], plan: Iterable[tuple[str, str, str]]) -> dict[str, Any]:
    """Observed = PARITY + GAP + APPROVED-DIVERGENCE + STRUCTURAL (+ NOT-RUN).

    The run qualifies only with no remainder: nothing planned is missing,
    nothing is unclassified or left NOT-RUN, every GAP has an issue and
    every STRUCTURAL names its Public origin path.
    """
    records = list(records)
    counts = {verdict: 0 for verdict in VERDICTS + (NOT_RUN,)}
    unclassified, gaps_without_issue, structural_without_path, not_run = [], [], [], []
    for record in records:
        verdict, identity = record.get("verdict"), record["control_identity"]
        if verdict not in counts:
            unclassified.append(identity)
            continue
        counts[verdict] += 1
        if verdict == "GAP" and not record.get("issue"):
            gaps_without_issue.append(identity)
        if verdict == "STRUCTURAL" and not record.get("public_path"):
            structural_without_path.append(identity)
        if verdict == NOT_RUN:
            not_run.append(identity)
    seen = [record["control_identity"] for record in records]
    planned = [check_identity(*check) for check in plan]
    report = {
        "observed": len(records),
        "counts": counts,
        "missing": sorted(set(planned) - set(seen)),
        "unplanned": sorted(set(seen) - set(planned)),
        "duplicates": sorted({identity for identity in seen if seen.count(identity) > 1}),
        "unclassified": unclassified,
        "gaps_without_issue": gaps_without_issue,
        "structural_without_path": structural_without_path,
        "not_run": not_run,
    }
    report["balanced"] = sum(counts.values()) + len(unclassified) == len(records)
    report["qualified"] = report["balanced"] and not any(
        report[key] for key in ("missing", "unplanned", "duplicates", "unclassified",
                                "gaps_without_issue", "structural_without_path", "not_run")
    )
    return report
