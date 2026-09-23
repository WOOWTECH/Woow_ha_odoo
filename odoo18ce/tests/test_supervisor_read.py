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
from pathlib import Path

import pytest

from conftest import require_bash

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "rootfs/usr/local/lib/supervisor-read.sh"

# The stubs stand in for bashio. `bashio::cache.flush` records the key on
# stderr, prefixed so the test can pick those lines out of any other stderr.
STUBS = r"""
bashio::log.debug() { :; }
bashio::log.trace() { :; }
bashio::log.warning() { printf 'WARN %s\n' "$1" >&2; }
bashio::cache.flush() { printf 'FLUSH %s\n' "$1" >&2; }
# No real waiting, and no real clock: `sleep` advances a counter that the
# helper's clock reads, so a 30-second budget is a matter of counting and
# the test does not depend on how fast this host forks a subshell.
SLEPT="$(mktemp)"; printf '0' > "${SLEPT}"
sleep() { printf '%s' $(( $(cat "${SLEPT}") + $1 )) > "${SLEPT}"; }
woow::supervisor.now() { cat "${SLEPT}"; }
# A read the Supervisor API refuses: bashio logs the refusal and returns
# non-zero with nothing on stdout.
refused() { printf 'Failed to get addon info from Supervisor API\n' >&2; return 1; }
# A read that answers after N empty attempts. The command substitution the
# helper wraps the read in is a subshell, so the count lives in a file.
COUNTER="$(mktemp)"; printf '0' > "${COUNTER}"
read_after() {
    local after=$1 value=$2 n
    n=$(( $(cat "${COUNTER}") + 1 )); printf '%s' "${n}" > "${COUNTER}"
    if [ "${n}" -ge "${after}" ]; then printf '%s' "${value}"; fi
    return 0
}
# A read that answers with a placeholder until the N-th attempt: what the
# Supervisor says for a container whose network it has not seen yet.
placeholder_until() {
    local until=$1 placeholder=$2 value=$3 n
    n=$(( $(cat "${COUNTER}") + 1 )); printf '%s' "${n}" > "${COUNTER}"
    if [ "${n}" -ge "${until}" ]; then printf '%s' "${value}"; else printf '%s' "${placeholder}"; fi
}
# The LAN address read, answering after N empty attempts, and the directory
# s6 hands services their environment from, both under the test's control.
bashio::network.ipv4_address() { read_after "${LAN_AFTER:-1}" 192.0.2.10/24; }
export WOOW_CONTAINER_ENV_DIR; WOOW_CONTAINER_ENV_DIR="$(mktemp -d)"
"""


def run_helper(script: str) -> subprocess.CompletedProcess:
    bash = require_bash()
    posix_helper = HELPER.as_posix()
    return subprocess.run(
        [bash, "-c", f'source "{posix_helper}"\n{STUBS}\n{script}'],
        capture_output=True, text=True, timeout=60,
    )


def flushed(result: subprocess.CompletedProcess) -> list[str]:
    return [line[len("FLUSH "):] for line in result.stderr.splitlines()
            if line.startswith("FLUSH ")]


def test_a_value_on_the_first_read_is_returned_at_once_without_a_flush() -> None:
    result = run_helper(
        'woow::supervisor.read 30 2 "addons.self.ip_address addons.self.info" '
        'read_after 1 172.30.33.4; echo " rc=$?"'
    )
    assert result.stdout == "172.30.33.4 rc=0\n", result.stderr
    assert flushed(result) == []


def test_a_read_that_answers_after_empties_is_retried_with_the_cache_flushed() -> None:
    result = run_helper(
        'woow::supervisor.read 30 2 "addons.self.ip_address addons.self.info" '
        'read_after 3 172.30.33.4; echo " rc=$? attempts=$(cat "${COUNTER}") slept=$(cat "${SLEPT}")"'
    )
    assert result.stdout == "172.30.33.4 rc=0 attempts=3 slept=4\n", result.stderr
    # Both keys, before each of the two retries, the filtered key first so a
    # flush interrupted between the two never leaves a stale filtered value
    # in front of a fresh info.
    assert flushed(result) == ["addons.self.ip_address", "addons.self.info"] * 2


def test_an_exhausted_budget_prints_nothing_fails_and_leaves_no_empty_answer_cached() -> None:
    result = run_helper(
        'woow::supervisor.read 30 2 "network.interface.default.info.ipv4.address" '
        'read_after 999 never; echo "rc=$? attempts=$(cat "${COUNTER}") slept=$(cat "${SLEPT}")"'
    )
    stdout = result.stdout.strip()
    assert stdout.startswith("rc=1 "), result.stderr
    fields = dict(part.split("=") for part in stdout.split())
    attempts, waited = int(fields["attempts"]), int(fields["slept"])
    assert attempts == 17, "one read every two seconds until the clock is past thirty"
    assert waited == 32, "never shorter than the budget, at most one poll longer"
    # The last empty answer is flushed too: nothing this helper gave up on
    # is left in bashio's cache for the next reader in this container.
    assert flushed(result) == ["network.interface.default.info.ipv4.address"] * attempts
    assert "WARN" not in result.stderr, "an answer that never came is not an error to log"


def test_a_read_the_supervisor_refuses_is_named_when_the_budget_runs_out() -> None:
    result = run_helper(
        'woow::supervisor.read 30 2 "addons.self.ip_address addons.self.info" '
        'refused; echo "rc=$?"'
    )
    assert result.stdout.strip() == "rc=1"
    warnings = [l for l in result.stderr.splitlines() if l.startswith("WARN ")]
    assert len(warnings) == 1, result.stderr
    assert "refused" in warnings[0] and "Failed to get addon info from Supervisor API" in warnings[0]


@pytest.mark.parametrize("placeholder", ["0.0.0.0", "null"])
def test_the_supervisor_placeholder_address_counts_as_not_yet(placeholder) -> None:
    # supervisor/docker/app.py answers `0.0.0.0` for a container whose
    # network it has not loaded; a jq `// empty` on a missing key is `null`.
    result = run_helper(
        'woow::supervisor.read 30 2 "addons.self.ip_address addons.self.info" '
        f'placeholder_until 3 {placeholder} 172.30.33.4; echo " rc=$? attempts=$(cat "${{COUNTER}}")"'
    )
    assert result.stdout == "172.30.33.4 rc=0 attempts=3\n", result.stderr
    assert flushed(result) == ["addons.self.ip_address", "addons.self.info"] * 2


def test_the_helper_is_readable_in_the_image() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "chmod a+r /usr/local/lib/supervisor-read.sh" in dockerfile


def test_the_helper_is_in_the_shellcheck_gate() -> None:
    ci = (ROOT.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'rootfs/usr/local/lib/supervisor-read.sh"' in ci.split("shellcheck -s bash", 1)[0]


# --- the LAN address, settled once per start ----------------------------------
# cont-init settles the host's LAN address for the Canonical URL and publishes
# it to the container environment; the maintenance bootstrap reads it from
# there (issue #108, ADR 0006: one value per start, derived once).

def published(result: subprocess.CompletedProcess) -> str | None:
    for line in result.stdout.splitlines():
        if line.startswith("PUBLISHED="):
            return line[len("PUBLISHED="):]
    return None


SETTLE = (
    'value="$(woow::supervisor.lan_ipv4_settle)"; rc=$?; '
    'echo; echo "value=${value} rc=${rc} attempts=$(cat "${COUNTER}") slept=$(cat "${SLEPT}")"; '
    'f="${WOOW_CONTAINER_ENV_DIR}/WOOW_LAN_IPV4"; '
    'if [ -e "$f" ]; then echo "PUBLISHED=$(cat "$f")"; else echo "PUBLISHED=<none>"; fi'
)


def test_a_lan_address_that_arrives_late_is_settled_once_and_published() -> None:
    result = run_helper("LAN_AFTER=3; " + SETTLE)
    assert "value=192.0.2.10/24 rc=0 attempts=3 slept=4" in result.stdout, result.stderr
    assert published(result) == "192.0.2.10/24"
    assert flushed(result) == [
        "network.interface.default.info.ipv4.address", "network.interface.default.info",
    ] * 2
    assert "WARN" not in result.stderr


def test_a_lan_address_that_never_arrives_is_one_warning_and_an_empty_publication() -> None:
    result = run_helper("LAN_AFTER=999; " + SETTLE)
    assert "value= rc=1 attempts=17 slept=32" in result.stdout, result.stderr
    assert published(result) == "", "published empty, so the bootstrap does not ask again"
    warnings = [l for l in result.stderr.splitlines() if l.startswith("WARN ")]
    assert len(warnings) == 1 and "30 seconds" in warnings[0] and "LAN" in warnings[0], result.stderr


def test_a_lan_address_on_the_first_read_costs_no_wait() -> None:
    result = run_helper("LAN_AFTER=1; " + SETTLE)
    assert "value=192.0.2.10/24 rc=0 attempts=1 slept=0" in result.stdout, result.stderr
    assert published(result) == "192.0.2.10/24"
    assert flushed(result) == [] and "WARN" not in result.stderr
