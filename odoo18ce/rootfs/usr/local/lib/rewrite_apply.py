#!/usr/bin/env python3
"""The Rewrite scan's apply path: findings become the nginx include file
(issue #93, ADR 0005 and ADR 0008).

`rewrite_scan.py` (issue #92) says which bundles a host serves and whether
they moved. This module is the half that acts on that: it reads the bytes,
classifies them with `literal_rewrite_gate.py`, writes the Generated
rewrites, validates the candidate with `nginx -t` and reloads the running
nginx. It is the risky half -- both historical breakages (0.3.10 and
0.3.34) were rewrite rules and `services.d/nginx/finish` halts the
container -- so every step here is written to leave the last good file in
place when anything is not certain.

Four refusals, in the order a round meets them:

- **An incomplete scan is never applied.** The include file is the union
  over databases, so a database that could not be read makes the union
  *smaller*: the generated text genuinely differs, the byte comparison
  passes it through, and a Generated rewrite that was working is removed.
  The operator then gets a Prefix escape caused by a failed read. A bundle
  whose bytes are missing from the filestore fails its database for the
  same reason (`read_bundles`).
- **An unchanged generation is not written.** `generate_include` is
  byte-stable, so equal text means equal rules, and nginx is not reloaded
  for a file that did not move.
- **A candidate that nginx does not accept is not moved into place.** The
  candidate is validated the way the Static tier validates a rendered
  gateway (`test_dual_gateway.py`): a temporary `nginx.conf` whose include
  line points at the candidate, listeners moved to unix sockets, then
  `nginx -t -c`. `nginx -t` opens listener sockets and the running nginx
  holds 8069, 8072 and 5691, so validating with the real listeners would
  fail on every host that is actually serving.
- **`literal_rewrite_auto = false` freezes application.** The scan runs and
  reports, and the include file is not touched. Rules already in place stay
  live: the option stops new rules, it does not roll back.

The state (`rewrite_scan.save_state`) is written here, and only after a
complete scan that was applied or that needed no change. A state written
from a scan that was not applied would make the next round believe the
include file already holds those rules. While application is off nothing
is written and the cheap "nothing changed" skip is not taken either, so the
report keeps saying what would be rewritten instead of going silent.

Only `validate`, `reload_nginx` and the file moves reach out of the
process; the rest is pure over strings, so the Static tier drives all four
refusals with a fake runner and a temporary filestore.

The module must import with the standard library alone, plus PyYAML for the
exception list, which ADR 0008 puts in the image.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import itertools
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, Iterable, Mapping

# The two modules ship beside this one. They are imported by name rather
# than by path so the Static tier, which loads all three out of the
# repository, gets one copy of each and one set of dataclasses.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import literal_rewrite_gate as gate     # noqa: E402  (after the path fix above)
import rewrite_scan as scan             # noqa: E402

#: The rendered gateway configuration, the one the running nginx loaded.
#: Read, never written: the Generated rewrites go in the include file.
NGINX_CONF_PATH = "/etc/nginx/nginx.conf"
#: Where the nginx master writes its pid (`nginx.conf.template:2`).
NGINX_PID_PATH = "/var/run/nginx.pid"
#: The exception list shipped in the image, which ADR 0005 keeps applying.
EXCEPTIONS_PATH = str(_HERE / "literal_rewrite_exceptions.yaml")

NGINX_BINARY = "nginx"
#: A `nginx -t` or a reload that never returns would stall every later
#: round of the five-minute loop, so both are bounded.
NGINX_TIMEOUT_SECONDS = 30

#: What a round did. `applied` and `unchanged` are the two states in which
#: the include file on disk agrees with the bundles that were read, and the
#: only two after which the state is written.
STATUS_APPLIED = "applied"
STATUS_UNCHANGED = "unchanged"
STATUS_UP_TO_DATE = "up to date"
STATUS_OFF = "application off"
STATUS_INCOMPLETE = "incomplete"
STATUS_INVALID = "invalid"

#: The statuses a round is allowed to end on without the operator having to
#: act. The CLI's exit status follows this.
HEALTHY_STATUSES = (STATUS_APPLIED, STATUS_UNCHANGED, STATUS_UP_TO_DATE, STATUS_OFF)

#: How a process is run. An argument everywhere, so the Static tier can
#: watch what would have been run without running it.
Runner = Callable[..., "subprocess.CompletedProcess"]


# --- the bytes ----------------------------------------------------------------

@dataclass(frozen=True)
class BundleRead:
    """The bundle bytes, and the scan result as reading them leaves it."""

    result: "scan.ScanResult"
    texts: Mapping[tuple[str, str], str] = field(default_factory=dict)
    missing: tuple = ()      # rows whose file could not be read


def read_bundles(result, filestore: str = scan.FILESTORE_DIR) -> BundleRead:
    """Read every readable bundle; a file that is gone fails its database.

    `rewrite_scan` reads rows, not bytes, so a bundle listed in
    `ir_attachment` whose filestore file is missing is met here first. It is
    the same danger as a failed database and gets the same answer: the union
    would be short by exactly the rules that bundle earns, and applying it
    would delete rules that were working. The measurement behind ADR 0007
    found 0 missing files of 20, so refusing the round costs little.

    A row `rewrite_scan` had to skip -- content kept in the database rather
    than the filestore (`ir_attachment.location = db`) -- fails its database
    here for the same reason. `rewrite_scan` reports that database as `ok`
    with the skips recorded, because a skip is reportable there; here it is
    a bundle nobody scanned, and an all-clear read off a short union is
    exactly what deletes a working rule.

    A database that already failed, or that serves no bundles, is carried
    through untouched.
    """
    texts: dict[tuple[str, str], str] = {}
    missing: list = []
    scans: list = []
    for database in result.databases:
        if database.status != scan.STATUS_OK:
            scans.append(database)
            continue
        errors: list[str] = [
            f"{row.url}: unsupported storage (ir_attachment.location = db), "
            "nothing to read"
            for row in database.skipped
        ]
        for row in database.rows:
            path = scan.bundle_path(row, filestore)
            try:
                # `errors="replace"` because a bundle is served as bytes and
                # nothing promises it decodes: a mis-decoded character must
                # not raise past a whole database's findings.
                texts[row.key] = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                missing.append(row)
                errors.append(f"{row.url}: {error}")
        if errors:
            # The findings of the bundles that *were* read are dropped with
            # the rest: a partial database is what makes a short union, and
            # the result is refused as a whole anyway.
            for row in database.rows:
                texts.pop(row.key, None)
            joined = "; ".join(errors)
            scans.append(replace(
                database, status=scan.STATUS_FAILED,
                error=f"{database.error}; {joined}" if database.error else joined,
            ))
        else:
            scans.append(database)
    return BundleRead(replace(result, databases=tuple(scans)), texts, tuple(missing))


# --- the text -----------------------------------------------------------------

def shipped_rules(nginx_conf: str) -> dict:
    """The Literal rewrite rules the image ships, from the rendered gateway.

    Read from the running configuration rather than from the template
    because the template is not on the host in rendered form anywhere else,
    and the rules are what nginx actually substitutes.

    The Generated rewrites are deliberately *not* merged in, although
    `nginx.conf` includes them: a generated rule read back as a shipped one
    would cover the finding that earned it, the next generation would drop
    it as covered, the round after that would add it again, and the rules
    would flap. `include_rules` and `merge_rules` exist for the gate's
    outside-in view of a host, which is a different question.
    """
    return gate.rewrite_rules(nginx_conf)


def load_exceptions(path: str | os.PathLike = EXCEPTIONS_PATH) -> set:
    """The approved exception list shipped in the image (ADR 0005)."""
    return gate.load_exceptions(Path(path).read_text(encoding="utf-8"))


def build_include(texts: Mapping[tuple[str, str], str], rules: Mapping, exceptions: Iterable) -> str:
    """The include text for these bundles: the union of their findings.

    The selection is `generate_include`'s alone -- navigation-level literals
    (`FAIL`) that no shipped rule covers and no exception excuses. This
    ticket adds no rule of its own, which is why `rewrite_apply.py` is not
    in `rewrite_scan.ANALYSIS_MODULES`: it cannot change what a scan finds.
    """
    findings: list = []
    for text in texts.values():
        findings.extend(gate.scan_bundle(text))
    return gate.generate_include(findings, rules, exceptions)


def include_prefixes(text: str) -> tuple:
    """The prefixes an include text rewrites, for the log and the report."""
    return tuple(sorted(gate.include_rules(text)))


# --- validation ---------------------------------------------------------------

# A listener line in the rendered configuration. Matched rather than listed
# literally so a template that gains or moves a listener does not need this
# file changed with it.
_LISTEN = re.compile(r"^(?P<indent>[ \t]*)listen\s+(?P<address>[^\s;]+)(?P<options>[^;]*);", re.M)
_PID = re.compile(r"^pid\s+[^;]+;", re.M)


def render_test_config(nginx_conf: str, candidate: str | os.PathLike, work_dir: str | os.PathLike) -> str:
    """A configuration that loads `candidate` instead of the live include file.

    `nginx -t` against the live configuration cannot validate a candidate:
    the include path in the template is fixed text
    (`nginx.conf.template:342`), so it would validate the file already in
    place. The Static tier already renders around that
    (`test_dual_gateway.py:324-325`) and this is the same move.

    Every listener becomes a unix socket inside `work_dir`. `nginx -t` opens
    listener sockets (`test_dual_gateway.py:329-337`) and the running nginx
    holds 8069, 8072 and 5691, so a test that kept the real listeners would
    pass in CI, where nothing is serving, and fail on every host that is.
    """
    work_dir = Path(work_dir)
    include = f"include {scan.GENERATED_REWRITES_PATH};"
    if nginx_conf.count(include) != 1:
        raise ValueError(
            f"expected exactly one {include!r} in the rendered configuration, "
            f"found {nginx_conf.count(include)}"
        )
    config = nginx_conf.replace(include, f"include {candidate};")

    numbers = itertools.count(1)

    def socket(match: "re.Match[str]") -> str:
        return (
            f"{match.group('indent')}listen "
            f"unix:{work_dir}/listen-{next(numbers)}.sock{match.group('options')};"
        )

    config = _LISTEN.sub(socket, config)
    if next(numbers) == 1:
        raise ValueError("the rendered configuration has no listener to move")
    # The running master owns the real pid file; a test run must not be able
    # to touch it whatever a future nginx does with it in test mode.
    # Both replacements are callables, so a path is inserted as it is: a
    # plain string would have its backslashes read as group references.
    config = _PID.sub(lambda match: f"pid {work_dir}/nginx.pid;", config)
    return config


def validate(
    candidate: str | os.PathLike,
    nginx_conf: str,
    work_dir: str | os.PathLike,
    runner: Runner = subprocess.run,
) -> tuple[bool, str]:
    """Does nginx accept this candidate? The message is masked either way."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    config = work_dir / "nginx.conf"
    try:
        config.write_text(
            render_test_config(nginx_conf, candidate, work_dir), encoding="utf-8"
        )
        finished = runner(
            [NGINX_BINARY, "-t", "-p", str(work_dir), "-c", str(config)],
            capture_output=True, text=True, timeout=NGINX_TIMEOUT_SECONDS,
        )
    except Exception as error:      # noqa: BLE001 - a failure to validate is a failure
        return False, gate.mask(f"the candidate could not be validated: {error}")
    output = (finished.stderr or finished.stdout or "").strip()
    return finished.returncode == 0, gate.mask(output)


# --- the running nginx --------------------------------------------------------

def nginx_master(pid_path: str | os.PathLike = NGINX_PID_PATH) -> int | None:
    """The pid of the running nginx master, or None when none is running.

    At start the Rewrite scan can easily win the race against the nginx
    service, which waits for Odoo's HTTP port first (`services.d/nginx/run`).
    Then the file is written and validated and there is simply nobody to
    reload; nginx loads it when it starts.

    Only POSIX asks the process whether it is alive: `os.kill` on Windows
    terminates rather than probes, and the Static tier is run on developer
    machines as well as in CI.
    """
    try:
        pid = int(Path(pid_path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if os.name != "posix":
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def reload_nginx(runner: Runner = subprocess.run) -> tuple[bool, str]:
    """Send `nginx -s reload` to the running master."""
    try:
        finished = runner(
            [NGINX_BINARY, "-s", "reload"],
            capture_output=True, text=True, timeout=NGINX_TIMEOUT_SECONDS,
        )
    except Exception as error:      # noqa: BLE001 - reported, never raised
        return False, gate.mask(f"the reload could not be run: {error}")
    output = (finished.stderr or finished.stdout or "").strip()
    return finished.returncode == 0, gate.mask(output)


# --- applying -----------------------------------------------------------------

@dataclass(frozen=True)
class ApplyResult:
    """What one round did, and whether its state may be kept."""

    status: str
    detail: str = ""
    include_text: str = ""
    prefixes: tuple = ()
    wrote: bool = False
    reloaded: bool = False
    state_saved: bool = False
    scan: "scan.ScanResult | None" = None
    verdict: "scan.ScanVerdict | None" = None

    @property
    def healthy(self) -> bool:
        return self.status in HEALTHY_STATUSES

    @property
    def agrees_with_disk(self) -> bool:
        """Does the include file now hold the rules these bundles earn?

        The one condition under which the state may be written: anything
        else would let the next round believe a generation that was never
        applied is already in place.
        """
        return self.status in (STATUS_APPLIED, STATUS_UNCHANGED)


def apply_include(
    text: str,
    nginx_conf: str,
    *,
    include_path: str | os.PathLike = scan.GENERATED_REWRITES_PATH,
    pid_path: str | os.PathLike = NGINX_PID_PATH,
    work_dir: str | os.PathLike | None = None,
    runner: Runner = subprocess.run,
    running: Callable[[], bool] | None = None,
) -> ApplyResult:
    """Write, validate and move the include file, then reload nginx.

    The candidate is written beside the file it may replace, because
    `os.replace` is atomic only inside one filesystem and the include file
    lives on the /data volume.
    """
    include = Path(include_path)
    prefixes = include_prefixes(text)
    try:
        current = include.read_text(encoding="utf-8")
    except OSError:
        # No file at all counts as different: `10-odoo-config.sh:257-267`
        # creates it empty, so an absent one means somebody removed it and
        # nginx is refusing to start until it is back.
        current = None

    if current == text:
        return ApplyResult(
            STATUS_UNCHANGED,
            f"the file already holds these {len(prefixes)} prefixes; "
            "nothing written, nginx not reloaded",
            include_text=text, prefixes=prefixes,
        )

    candidate = include.with_name(include.name + ".candidate")
    candidate.write_text(text, encoding="utf-8")
    # cont-init runs under `umask 077`, and nginx reads this file as the
    # user it drops to, so the mode is set here as it is for the real file.
    os.chmod(candidate, 0o644)

    if work_dir is None:
        with tempfile.TemporaryDirectory(prefix="rewrite-apply-") as temporary:
            accepted, message = validate(candidate, nginx_conf, temporary, runner)
    else:
        accepted, message = validate(candidate, nginx_conf, work_dir, runner)

    if not accepted:
        candidate.unlink(missing_ok=True)
        return ApplyResult(
            STATUS_INVALID,
            f"nginx refused the candidate, so {include} stays as it is: {message}",
            include_text=text, prefixes=prefixes,
        )

    os.replace(candidate, include)

    alive = nginx_master(pid_path) is not None if running is None else running()
    if not alive:
        return ApplyResult(
            STATUS_APPLIED,
            f"{len(prefixes)} prefixes written to {include}; "
            "nginx is not running yet, so it was not reloaded",
            include_text=text, prefixes=prefixes, wrote=True,
        )

    reloaded, reload_message = reload_nginx(runner)
    detail = f"{len(prefixes)} prefixes written to {include}"
    if not reloaded:
        # The file is valid and in place, so nginx loads it at its next
        # start whatever happened here; saying so is better than pretending
        # the rules are live.
        return ApplyResult(
            STATUS_APPLIED,
            f"{detail}, but the reload failed and the rules are not live yet: "
            f"{reload_message}",
            include_text=text, prefixes=prefixes, wrote=True,
        )
    return ApplyResult(
        STATUS_APPLIED, f"{detail} and nginx was reloaded",
        include_text=text, prefixes=prefixes, wrote=True, reloaded=True,
    )


def _incomplete(result) -> str:
    """Why nothing was applied, with the database that failed named."""
    reason = result.error or (
        "databases that could not be read: " + ", ".join(
            f"{database.database} ({database.error})" if database.error else database.database
            for database in result.databases
            if database.status == scan.STATUS_FAILED
        )
    )
    return (
        "nothing written and nginx not reloaded, because the scan is "
        f"incomplete: {reason}"
    )


def apply_round(
    result,
    *,
    auto: bool = True,
    previous_state=None,
    force: bool = False,
    filestore: str = scan.FILESTORE_DIR,
    include_path: str | os.PathLike = scan.GENERATED_REWRITES_PATH,
    nginx_conf_path: str | os.PathLike = NGINX_CONF_PATH,
    exceptions_path: str | os.PathLike = EXCEPTIONS_PATH,
    state_path: str | os.PathLike | None = scan.STATE_PATH,
    pid_path: str | os.PathLike = NGINX_PID_PATH,
    version: str | None = None,
    runner: Runner = subprocess.run,
    running: Callable[[], bool] | None = None,
) -> ApplyResult:
    """One whole round over a scan result: read, generate, apply, remember.

    Completeness is tested twice, and the first test comes before the
    verdict: the verdict compares the previous state with a union that is
    short by the bundles nobody read, so a failed database reads there as a
    removal that never happened. The second test is after the bytes are
    read, because a bundle whose file is missing fails its database too and
    that is only visible once somebody tries to open it.

    Between the two sits the skip, which is why the bytes are read after the
    verdict and not before: reading and classifying them is the four seconds
    a round costs (ADR 0007), and the whole point of the state is not to pay
    it when nothing moved.
    """
    if not result.complete:
        return ApplyResult(
            STATUS_INCOMPLETE, _incomplete(result), scan=result,
        )

    verdict = scan.scan_state(result.rows, previous_state, version=version)
    # The skip is an optimisation for a host whose rules are already in
    # place, and it is taken only while application is on. With the option
    # off nothing is ever applied, so a skip there would silence exactly the
    # report the option exists to keep.
    if auto and not force and not verdict.rescan:
        return ApplyResult(
            STATUS_UP_TO_DATE,
            f"no pass was due ({verdict.reason}); the include file is untouched",
            scan=result, verdict=verdict,
        )

    read = read_bundles(result, filestore)
    if not read.result.complete:
        return ApplyResult(
            STATUS_INCOMPLETE, _incomplete(read.result), scan=read.result, verdict=verdict,
        )

    nginx_conf = Path(nginx_conf_path).read_text(encoding="utf-8")
    text = build_include(read.texts, shipped_rules(nginx_conf), load_exceptions(exceptions_path))
    prefixes = include_prefixes(text)

    if not auto:
        return ApplyResult(
            STATUS_OFF,
            f"literal_rewrite_auto is false: application is off and "
            f"{include_path} is not touched. The scan found {len(prefixes)} "
            "prefixes that would be rewritten; rules already in place stay live",
            include_text=text, prefixes=prefixes, scan=read.result, verdict=verdict,
        )

    outcome = apply_include(
        text, nginx_conf,
        include_path=include_path, pid_path=pid_path, runner=runner, running=running,
    )
    outcome = replace(outcome, scan=read.result, verdict=verdict)

    if outcome.agrees_with_disk and state_path is not None:
        # Only now: the file on disk holds the rules these bundles earn, so
        # "this is what was served when the include file was last built" is
        # true. A state written from a refused or frozen round would make
        # the next one skip the pass that would have fixed it.
        scan.save_state(state_path, scan.state_from_rows(read.result.rows, version))
        outcome = replace(outcome, state_saved=True)
    return outcome


# --- the command --------------------------------------------------------------

def report(outcome: ApplyResult, state_note: str, out=print) -> None:
    """One round in the add-on log, Ingress tokens masked."""
    def line(text: str = "") -> None:
        out(gate.mask(text))

    line(f"Rewrite scan (apply): {outcome.status}")
    line(f"  {outcome.detail}")
    line(f"  state: {state_note}" + (" (written)" if outcome.state_saved else ""))
    if outcome.scan is not None:
        for database in outcome.scan.databases:
            header = f"  {database.database}: {database.status}"
            line(f"{header} -- {database.error}" if database.error else header)
    if outcome.prefixes:
        line(f"  prefixes: {' '.join(outcome.prefixes)}")


def main(argv=None, run_query=None, out=print) -> int:
    parser = argparse.ArgumentParser(
        prog="odoo-rewrite-apply",
        description="Run one Rewrite scan round and apply its findings as the "
                    "Generated rewrite include file.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--auto", dest="auto", action="store_true", default=True,
                       help="apply the findings (the default)")
    group.add_argument("--no-auto", dest="auto", action="store_false",
                       help="scan and report, but never touch the include file")
    parser.add_argument("--force", action="store_true",
                        help="scan even when the state says nothing changed")
    parser.add_argument("--state", default=scan.STATE_PATH,
                        help="the state kept by the last applied pass")
    parser.add_argument("--include", default=scan.GENERATED_REWRITES_PATH,
                        help="the Generated rewrite include file")
    parser.add_argument("--nginx-conf", default=NGINX_CONF_PATH,
                        help="the rendered gateway configuration to validate against")
    parser.add_argument("--filestore", default=scan.FILESTORE_DIR,
                        help="the filestore's parent directory")
    parser.add_argument("--exceptions", default=EXCEPTIONS_PATH,
                        help="the approved exception list")
    arguments = parser.parse_args(argv)

    loaded = scan.load_state(arguments.state, arguments.include)
    state_note = loaded.reason or f"{arguments.state}, {len(loaded.state.bundles)} bundles"
    result = scan.scan_databases(run_query or scan.psql_query)
    outcome = apply_round(
        result,
        auto=arguments.auto,
        previous_state=loaded.state,
        force=arguments.force,
        filestore=arguments.filestore,
        include_path=arguments.include,
        nginx_conf_path=arguments.nginx_conf,
        exceptions_path=arguments.exceptions,
        state_path=arguments.state,
    )
    report(outcome, state_note, out)
    return 0 if outcome.healthy else 1


if __name__ == "__main__":
    sys.exit(main())
