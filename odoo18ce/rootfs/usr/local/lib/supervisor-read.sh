#!/usr/bin/env bash
# ==============================================================================
# A Supervisor read that waits for its value (issues #119, #108).
#
# At boot a bashio read can come back empty for a moment: the Supervisor has
# not answered yet, or the DHCP lease behind `network.ipv4_address` has not
# arrived. bashio then writes that empty answer to its file cache under
# /tmp/.bashio, and every later read in this container returns it. One bad
# moment becomes the whole start.
#
# `woow::supervisor.read` runs the read again until it returns something or
# a budget runs out, flushing the cache keys behind it after every answer
# that is not a value — so the Supervisor is really asked again, and so an
# exhausted budget leaves nothing empty in the cache for the next reader.
# "Not a value" is the empty string, jq's `null`, and `0.0.0.0`: the
# Supervisor's own placeholder for a container whose network it has not
# loaded yet (supervisor/docker/app.py, NO_ADDDRESS). The value goes to
# stdout; an exhausted budget is exit 1 with nothing printed, and the
# caller decides what an empty value means and says how long was waited.
# When the budget runs out and the last attempt wrote an error, that error
# is logged, so "the Supervisor said nothing" and "the Supervisor could not
# be asked" (no token, no socket, an API error) read differently.
#
# What this does not bound is one read that hangs: bashio's curl has no
# --max-time, so a Supervisor that accepts the connection and never
# answers holds the read, as it held the single read before this helper.
#
# Usage:
#   woow::supervisor.read BUDGET POLL "KEY..." COMMAND [ARG...]
#     BUDGET   seconds to keep trying (decided on #108: 30)
#     POLL     seconds between attempts (decided on #108: 2)
#     KEY...   bashio cache keys to flush between attempts, space-separated:
#              the filtered key and the info key it is derived from
#     COMMAND  the bashio read, with its arguments
#
# Sourced, not executed: `. /usr/local/lib/supervisor-read.sh`.
# ==============================================================================

woow::supervisor.is_value() {
    case "$1" in
        ''|null|0.0.0.0) return 1 ;;
        *) return 0 ;;
    esac
}

# The clock the budget is measured on. bash's SECONDS counts whole seconds;
# a test replaces this function with a counter its `sleep` stub advances.
woow::supervisor.now() {
    printf '%s' "${SECONDS}"
}

woow::supervisor.read() {
    local budget=$1 poll=$2 keys=$3
    shift 3
    local started value='' key error
    started="$(woow::supervisor.now)"
    error="$(mktemp)"
    while :; do
        value="$("$@" 2>"${error}" || true)"
        if woow::supervisor.is_value "${value}"; then
            rm -f "${error}"
            printf '%s' "${value}"
            return 0
        fi
        # In a subshell: bashio's flush ends the shell on a filesystem error,
        # and that must not end the service script it was called from.
        for key in ${keys}; do
            ( bashio::cache.flush "${key}" ) || true
        done
        # Whole seconds, so "past the budget" rather than "at it": the wait
        # is then never shorter than asked, at most a poll longer.
        if [ $(( $(woow::supervisor.now) - started )) -gt "${budget}" ]; then
            break
        fi
        sleep "${poll}"
    done
    if [ -s "${error}" ]; then
        bashio::log.warning "Supervisor read $1 failed on its last attempt: $(tail -n 1 "${error}")"
    fi
    rm -f "${error}"
    return 1
}

# ------------------------------------------------------------------------------
# Hand a value from cont-init to the services (issue #108, ADR 0006).
#
# s6-overlay reads /run/s6/container_environment/NAME into the environment
# of every `with-contenv` script that starts later, so a value settled once
# in cont-init is the value the maintenance bootstrap sees, and neither side
# derives it twice. The Static tier points WOOW_CONTAINER_ENV_DIR elsewhere.
#
#   woow::supervisor.publish NAME VALUE
# ------------------------------------------------------------------------------
woow::supervisor.publish() {
    local dir="${WOOW_CONTAINER_ENV_DIR:-/run/s6/container_environment}"
    mkdir -p "${dir}"
    printf '%s' "$2" > "${dir}/$1"
}

# ------------------------------------------------------------------------------
# The host's LAN IPv4 address for the Canonical URL, settled once per start.
#
# Waits for `bashio::network.ipv4_address` with the budget decided on #108
# (30 s, 2 s), prints what it got — possibly nothing — and publishes that
# same value as WOOW_LAN_IPV4 for the bootstrap, so a start ends with one
# LAN address on both sides, or none on both. An address that never comes
# is one warning here; the caller's own "no Canonical URL" line follows.
# ------------------------------------------------------------------------------
woow::supervisor.lan_ipv4_settle() {
    local budget=30 poll=2 value='' status=0
    value="$(woow::supervisor.read "${budget}" "${poll}" \
        "network.interface.default.info.ipv4.address network.interface.default.info" \
        bashio::network.ipv4_address)" || status=$?
    if [ -z "${value}" ]; then
        bashio::log.warning "The Supervisor reported no host LAN address after waiting at least ${budget} seconds; this start has no Canonical URL from it"
    fi
    woow::supervisor.publish WOOW_LAN_IPV4 "${value}"
    printf '%s' "${value}"
    return "${status}"
}
