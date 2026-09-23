#!/usr/bin/env python3
"""Static-tier contracts for the Supervisor read helper (issues #119, #108).

A bashio read at boot can come back empty for a moment — the Supervisor has
not answered yet, or a DHCP lease has not arrived — and bashio caches that
empty answer in a file for the container's lifetime. `supervisor-read.sh`
retries the read for a bounded time, flushing the cache keys behind it
between attempts, so one bad moment is not the whole start.

The helper is a bash function, so it is driven by bash: sourced into a shell
whose `bashio::*` functions are stubs, and observed through what it prints,
what it returns and which cache keys it flushed.
"""
import subprocess
import time
from pathlib import Path

import pytest

from conftest import require_tool

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "rootfs/usr/local/lib/supervisor-read.sh"

# The stubs stand in for bashio. `bashio::cache.flush` records the key on
# stderr, prefixed so the test can pick those lines out of any other stderr.
STUBS = r"""
bashio::log.debug() { :; }
bashio::log.trace() { :; }
bashio::cache.flush() { printf 'FLUSH %s\n' "$1" >&2; }
# A read that answers after N empty attempts. The command substitution the
# helper wraps the read in is a subshell, so the count lives in a file.
COUNTER="$(mktemp)"; printf '0' > "${COUNTER}"
read_after() {
    local after=$1 value=$2 n
    n=$(( $(cat "${COUNTER}") + 1 )); printf '%s' "${n}" > "${COUNTER}"
    if [ "${n}" -ge "${after}" ]; then printf '%s' "${value}"; fi
    return 0
}
"""


def run_helper(script: str) -> subprocess.CompletedProcess:
    bash = require_tool("bash")
    posix_helper = HELPER.as_posix()
    return subprocess.run(
        [bash, "-c", f'source "{posix_helper}"\n{STUBS}\n{script}'],
        capture_output=True, text=True, timeout=60,
    )


def flushed(result: subprocess.CompletedProcess) -> list[str]:
    return [line[len("FLUSH "):] for line in result.stderr.splitlines()
            if line.startswith("FLUSH ")]


def test_a_value_on_the_first_read_is_returned_at_once_without_a_flush() -> None:
    started = time.monotonic()
    result = run_helper(
        'woow::supervisor.read 30 2 "addons.self.ip_address addons.self.info" '
        'read_after 1 172.30.33.4; echo " rc=$?"'
    )
    assert result.stdout == "172.30.33.4 rc=0\n", result.stderr
    assert flushed(result) == []
    assert time.monotonic() - started < 2, "no poll interval is spent on a value that is there"


def test_a_read_that_answers_after_empties_is_retried_with_the_cache_flushed() -> None:
    result = run_helper(
        'woow::supervisor.read 30 0.2 "addons.self.ip_address addons.self.info" '
        'read_after 3 172.30.33.4; echo " rc=$? attempts=$(cat "${COUNTER}")"'
    )
    assert result.stdout == "172.30.33.4 rc=0 attempts=3\n", result.stderr
    # Both keys, before each of the two retries, the filtered key first so a
    # flush interrupted between the two never leaves a stale filtered value
    # in front of a fresh info.
    assert flushed(result) == ["addons.self.ip_address", "addons.self.info"] * 2


def test_an_exhausted_budget_prints_nothing_and_fails() -> None:
    started = time.monotonic()
    result = run_helper(
        'woow::supervisor.read 1 0.2 "network.interface.default.info.ipv4.address" '
        'read_after 999 never; echo "rc=$? attempts=$(cat "${COUNTER}")"'
    )
    elapsed = time.monotonic() - started
    stdout = result.stdout.strip()
    assert stdout.startswith("rc=1 "), result.stderr
    fields = dict(part.split("=") for part in stdout.split())
    assert 2 <= int(fields["attempts"]) <= 12, "bounded by the clock, not by a count"
    assert 1 <= elapsed < 4, "the budget holds: one second asked for, not much more spent"
    assert flushed(result)[0] == "network.interface.default.info.ipv4.address"


def test_the_helper_is_readable_in_the_image() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "chmod a+r /usr/local/lib/supervisor-read.sh" in dockerfile


def test_the_helper_is_in_the_shellcheck_gate() -> None:
    ci = (ROOT.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'rootfs/usr/local/lib/supervisor-read.sh"' in ci.split("shellcheck -s bash", 1)[0]
