#!/usr/bin/env bash
# ==============================================================================
# slow-link-pull.sh
# Download a Release image from ghcr with resumable transfers and load it into
# the host's Docker, so that `ha apps update <slug>` finds it locally and has
# nothing left to pull (issue #157, parent #153).
#
# Why this exists: the Supervisor's pull is not resumable. When the connection
# drops, Docker discards the partial layer and the whole layer starts again
# from zero, so on a slow or unstable link a large Release never converges.
# `curl -C -` resumes from the last byte, so the download survives the drops.
#
# What it does NOT do: it never runs the update. It prints the `ha apps update`
# command and stops, so that a human chooses the moment the add-on restarts.
#
# Scope of access: it contacts `ghcr.io` and the storage host ghcr redirects
# to, and nothing else. It refuses an image that is not on ghcr.io.
#
# Usage:
#   ./slow-link-pull.sh [--dry-run] [--image <ref>] [<slug>] [<version>]
#
#   <slug>      the add-on slug; default 1b7b4ce7_odoo18ce
#   <version>   an override; default the Supervisor's version_latest
#   --dry-run   fetch and verify the manifest and the config only, skip the
#               layer blobs, the load and the gate
#   --image     the image to pull, without a tag. Default: the Supervisor's
#               answer if it still carries one, otherwise the image the
#               installed add-on container runs.
#
# Exit codes:
#   0   the image is loaded and the gate passed (or the dry run verified)
#   2   usage error
#   3   a required tool is missing
#   4   the Supervisor could not be asked, or its answer is unusable
#   5   the ghcr token request failed
#   6   the manifest could not be fetched, or a media type is not supported
#   7   a size or sha256 check failed and did not recover
#   8   a blob stopped making progress and did not recover
#   9   `docker load` failed
#   10  the gate failed: the loaded image ID is not the config digest
#   11  another run of this script holds the work directory
#
# Validated on: Docker 28.3.3 with the overlay2 storage driver, Supervisor
# 2026.09.2, HA OS. See SLOW_LINK_DEPLOY.md next to this script.
# ==============================================================================
set -euo pipefail

readonly EXIT_USAGE=2
readonly EXIT_TOOL=3
readonly EXIT_SUPERVISOR=4
readonly EXIT_TOKEN=5
readonly EXIT_MEDIA=6
readonly EXIT_DIGEST=7
readonly EXIT_DOWNLOAD=8
readonly EXIT_LOAD=9
readonly EXIT_GATE=10
readonly EXIT_LOCKED=11

readonly DEFAULT_SLUG="1b7b4ce7_odoo18ce"
readonly REGISTRY="ghcr.io"
# `/share` is the add-on-visible path that survives an SSH session drop and a
# reboot, which is the whole point of the work directory. The override exists
# so the Static tier can drive this script without a Supervisor: nothing on a
# real host sets it.
readonly WORK_ROOT="${SLOW_LINK_WORK_ROOT:-/share/slow-link-pull}"

# A new connection often starts fast and then collapses. Give up on a
# connection that stays under 50 KB/s for a minute and open a fresh one,
# which also means a fresh token and a fresh storage redirect.
readonly SPEED_LIMIT=51200
readonly SPEED_TIME=60
# What is bounded is the number of attempts in a row that move no bytes. An
# attempt that reached further into the blob resets the count: on a link
# that never clears 50 KB/s every attempt ends at the stall timeout, and a
# flat budget would give up part-way through a 693 MiB layer that was in
# fact still advancing.
readonly MAX_STALLED=30
# Bytes that arrive and never match are a separate class: a deleted blob is
# re-downloaded from zero, so every such round "makes progress" and would
# never spend the stall budget. This one is never reset.
readonly MAX_BAD_DIGESTS=5
# And so is a server that will not answer a resume with a 206: the blob
# starts again from zero, which is a new download and deserves a new stall
# budget, but not an unlimited number of them.
readonly MAX_RESTARTS=5
# An absolute ceiling on attempts for one blob, so that no combination of
# resets can keep the loop alive for ever.
readonly MAX_ATTEMPTS=500

# The manifest media types this script understands. An index or a manifest
# list is refused rather than guessed at.
readonly ACCEPT_MANIFEST='application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'

DRY_RUN=0
IMAGE_OVERRIDE=""

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*"; }
die() { local code="$1"; shift; printf 'error: %s\n' "$*" >&2; exit "${code}"; }

usage() {
    sed -n '/^# Usage:/,/^# Exit codes:/p' "$0" | sed 's/^# \{0,1\}//; $d'
}

# ---------------------------------------------------------------- arguments

# Options are accepted anywhere: `slow-link-pull.sh <slug> --dry-run` is the
# order a hand reaches for, and taking --dry-run as the version would start a
# full download instead.
POSITIONAL=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        # An empty or option-shaped value is a usage error, not a silent
        # fallback to the automatic answer: this script downloads for hours,
        # and an operator who pinned an image and got a different one would
        # find out at the end.
        --image)
            [ "$#" -ge 2 ] || { usage >&2; die "${EXIT_USAGE}" "--image needs a value"; }
            case "$2" in
                "") usage >&2; die "${EXIT_USAGE}" "--image was given an empty value" ;;
                -*) usage >&2; die "${EXIT_USAGE}" "--image was given the option \`$2\` instead of an image" ;;
            esac
            IMAGE_OVERRIDE="$2"; shift 2 ;;
        --image=*)
            IMAGE_OVERRIDE="${1#--image=}"
            [ -n "${IMAGE_OVERRIDE}" ] || { usage >&2; die "${EXIT_USAGE}" "--image was given an empty value"; }
            shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; while [ "$#" -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
        -*) usage >&2; die "${EXIT_USAGE}" "unknown option: $1" ;;
        *) POSITIONAL+=("$1"); shift ;;
    esac
done

[ "${#POSITIONAL[@]}" -le 2 ] || { usage >&2; die "${EXIT_USAGE}" "too many arguments"; }
SLUG="${POSITIONAL[0]:-${DEFAULT_SLUG}}"
VERSION_OVERRIDE="${POSITIONAL[1]:-}"

# ------------------------------------------------------------ prerequisites

for tool in curl jq sha256sum tar; do
    command -v "${tool}" >/dev/null 2>&1 \
        || die "${EXIT_TOOL}" "${tool} is not installed; use the Advanced SSH & Web Terminal add-on with protection mode off"
done
if [ "${DRY_RUN}" -eq 0 ]; then
    command -v docker >/dev/null 2>&1 \
        || die "${EXIT_TOOL}" "docker is not installed; the official SSH add-on has no docker, use Advanced SSH & Web Terminal with protection mode off"
fi
command -v ha >/dev/null 2>&1 || die "${EXIT_TOOL}" "the ha CLI is not on PATH"

# --------------------------------------------------------- Supervisor facts

# `ha apps` and `ha addons` are the same command; `ha apps` is the spelling
# this script and the runbook use.
ha_json() {
    local out
    out="$(ha "$@" --raw-json 2>/dev/null)" \
        || die "${EXIT_SUPERVISOR}" "\`ha $* --raw-json\` failed"
    printf '%s' "${out}"
}

json_field() {
    local json="$1" path="$2" value
    value="$(printf '%s' "${json}" | jq -r "${path} // empty")" \
        || die "${EXIT_SUPERVISOR}" "could not read ${path} from the Supervisor's answer"
    [ -n "${value}" ] || die "${EXIT_SUPERVISOR}" "the Supervisor's answer has no ${path}"
    printf '%s' "${value}"
}

INFO_JSON="$(ha_json info)"
ARCH="$(json_field "${INFO_JSON}" '.data.arch')"

# The add-on's own record answers two questions: which image, and which
# version. With both given on the command line it answers neither, and asking
# for it anyway would make `--image` unreachable exactly where it is the only
# way in -- `ha apps info <slug>` fails on a host where the add-on was never
# installed, and `ha_json` turns that into exit 4.
APP_JSON=""
if [ -z "${IMAGE_OVERRIDE}" ] || [ -z "${VERSION_OVERRIDE}" ]; then
    APP_JSON="$(ha_json apps info "${SLUG}")"
fi

# An image reference without its tag or digest. Only the last path segment can
# carry a tag, so `ghcr.io:443/woowtech/woow-ha-odoo-amd64` keeps its port. A
# reference with no `/` is not a repository at all -- `sha256:<hex>` is what
# docker answers for a container created from an image ID -- and is handed
# back whole for the caller to refuse, rather than chopped into `sha256`.
strip_tag() {
    local ref="${1%%@*}"
    case "${ref}" in
        */*) ;;
        *) printf '%s' "$1"; return 0 ;;
    esac
    local last="${ref##*/}"
    case "${last}" in
        *:*) printf '%s' "${ref%:*}" ;;
        *)   printf '%s' "${ref}" ;;
    esac
}

# Where the image comes from, in order. The Supervisor used to answer with it,
# and on Supervisor 2026.09.2 the field is gone: `.data.image` is absent
# from `ha apps info`, from `ha addons info`, and from the REST
# `/addons/<slug>/info` and `/store/addons/<slug>` alike (measured on HA OS,
# Supervisor 2026.09.2, 2026-09-28). The installed container is the second
# source and the reliable one here: this script exists for an update that
# failed, so the add-on is installed and its container names the image it
# runs -- the same repository, an older tag. `app_` is the current container
# prefix and `addon_` the older one. `--image` is the third, for a host where
# neither answers.
#
# It answers through two globals rather than stdout, so that the reason a
# lookup failed survives: a command substitution is a subshell, and a reason
# assigned in one is gone by the time the caller reads it. Saying which of
# the three places was empty is the whole value of the message.
RESOLVED_IMAGE=""
RESOLVE_REASON=""
resolve_image() {
    local image name
    if [ -n "${APP_JSON}" ]; then
        image="$(printf '%s' "${APP_JSON}" | jq -r '.data.image // empty' 2>/dev/null)" || image=""
        if [ -n "${image}" ]; then
            RESOLVED_IMAGE="${image}"
            return 0
        fi
    fi
    if ! command -v docker >/dev/null 2>&1; then
        RESOLVE_REASON="docker is not on PATH, so no container could be read (the official SSH add-on has no docker: use Advanced SSH & Web Terminal with protection mode off, or pass --image)"
        return 1
    fi
    for name in "app_${SLUG}" "addon_${SLUG}"; do
        image="$(docker inspect --format '{{.Config.Image}}' "${name}" 2>/dev/null)" || image=""
        [ -n "${image}" ] || continue
        case "${image}" in
            */*)
                RESOLVED_IMAGE="$(strip_tag "${image}")"
                return 0 ;;
        esac
        RESOLVE_REASON="the container ${name} was created from an image ID (${image}) and does not name the repository it came from, so pass --image"
        return 1
    done
    RESOLVE_REASON="no container app_${SLUG} or addon_${SLUG} is installed to read one from"
    return 1
}

if [ -n "${IMAGE_OVERRIDE}" ]; then
    IMAGE="$(strip_tag "${IMAGE_OVERRIDE}")"
elif resolve_image; then
    IMAGE="${RESOLVED_IMAGE}"
else
    die "${EXIT_SUPERVISOR}" \
        "could not work out which image ${SLUG} runs: the Supervisor's answer has no .data.image (Supervisor 2026.09 dropped the field), and ${RESOLVE_REASON}. Pass --image <ref> to name it."
fi

if [ -n "${VERSION_OVERRIDE}" ]; then
    VERSION="${VERSION_OVERRIDE}"
else
    VERSION="$(json_field "${APP_JSON}" '.data.version_latest')"
fi

# config.yaml carries `image: ghcr.io/woowtech/woow-ha-odoo-{arch}`; the
# Supervisor usually answers with {arch} already resolved, but not always.
IMAGE="${IMAGE//\{arch\}/${ARCH}}"

case "${IMAGE}" in
    "${REGISTRY}"/*) ;;
    *) die "${EXIT_SUPERVISOR}" "the image ${IMAGE} is not on ${REGISTRY}; this script only contacts ${REGISTRY}" ;;
esac
REPO="${IMAGE#"${REGISTRY}"/}"

log "add-on ${SLUG}, arch ${ARCH}"
log "image  ${IMAGE}:${VERSION}"

WORK="${WORK_ROOT}/${SLUG}/${VERSION}"
BLOBS="${WORK}/blobs"
LOCK="${WORK}/.lock"
mkdir -p "${BLOBS}"

# One run at a time per work directory. Section 7 of the runbook tells the
# operator to re-run the same command after a dropped SSH session, and in
# tmux the first run is still alive: two `curl -C -` into the same partial
# blob overshoot the size, delete it under each other, and the download
# never converges.
# The lock is under /share, so it outlives a reboot and an OOM kill, and a
# pid on its own would eventually name an unrelated process. The boot id is
# what tells those apart: a lock from an earlier boot is always stale.
BOOT_ID="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
if ! mkdir "${LOCK}" 2>/dev/null; then
    HOLDER="$(cat "${LOCK}/pid" 2>/dev/null || true)"
    HOLDER_BOOT="$(cat "${LOCK}/boot" 2>/dev/null || true)"
    if [ -z "${HOLDER}" ]; then
        # The directory is there but not filled in yet: another run took it
        # a moment ago. Calling that stale would hand both runs the same
        # blobs, which is the whole thing the lock is for.
        die "${EXIT_LOCKED}" "${LOCK} exists but names no pid; another run is starting. If nothing is running, remove ${LOCK}"
    fi
    if [ "${HOLDER_BOOT}" = "${BOOT_ID}" ] && kill -0 "${HOLDER}" 2>/dev/null; then
        die "${EXIT_LOCKED}" "pid ${HOLDER} is already working in ${WORK}; let it finish, kill it, or remove ${LOCK}"
    fi
    log "removing a lock left behind by pid ${HOLDER:-unknown}, which is gone"
    rm -rf "${LOCK}"
    mkdir "${LOCK}" || die "${EXIT_LOCKED}" "could not take the lock in ${WORK}; remove ${LOCK} by hand"
fi
echo "$$" > "${LOCK}/pid"
printf '%s' "${BOOT_ID}" > "${LOCK}/boot"
trap 'rm -rf "${LOCK}"' EXIT

log "work   ${WORK} (kept between runs so a re-run resumes)"

# ------------------------------------------------------------------- ghcr

# A fresh anonymous token for every request. Tokens are short-lived, and a
# resumed download can sit on one connection for a long time.
ghcr_token() {
    local token
    token="$(curl -fsS --connect-timeout 30 --max-time 60 \
        "https://${REGISTRY}/token?service=${REGISTRY}&scope=repository:${REPO}:pull" \
        | jq -r '.token // empty')" || return 1
    [ -n "${token}" ] || return 1
    printf '%s' "${token}"
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

# ---------------------------------------------------------------- manifest

MANIFEST="${WORK}/manifest-oci.json"
HEADERS="${WORK}/manifest.headers"

# The platform an index entry has to match. Home Assistant's arch names are
# not the ones an image index uses.
case "${ARCH}" in
    amd64)   PLATFORM_ARCH="amd64"; PLATFORM_VARIANT="" ;;
    aarch64) PLATFORM_ARCH="arm64"; PLATFORM_VARIANT="" ;;
    armv7)   PLATFORM_ARCH="arm";   PLATFORM_VARIANT="v7" ;;
    armhf)   PLATFORM_ARCH="arm";   PLATFORM_VARIANT="v6" ;;
    i386)    PLATFORM_ARCH="386";   PLATFORM_VARIANT="" ;;
    *) die "${EXIT_SUPERVISOR}" "the Supervisor reports arch ${ARCH}, which this script has no image-index name for" ;;
esac

fetch_manifest() {
    local reference="$1" token
    token="$(ghcr_token)" || die "${EXIT_TOKEN}" "could not get an anonymous ghcr token for ${REPO}"
    curl -fsSL --connect-timeout 30 --max-time 120 \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: ${ACCEPT_MANIFEST}" \
        -D "${HEADERS}" -o "${MANIFEST}" \
        "https://${REGISTRY}/v2/${REPO}/manifests/${reference}" \
        || die "${EXIT_MEDIA}" "could not fetch the manifest of ${IMAGE} at ${reference}"
}

header_value() {
    tr -d '\r' < "${HEADERS}" | awk -v name="$1" 'tolower($1) == name { print $2 }' | tail -1
}

# The body that arrived, against the digest and the length the registry
# states. With no digest given, `Docker-Content-Digest` is the one to trust:
# for a tag it is the tag's own digest.
check_manifest_bytes() {
    local expected_digest="$1" actual_digest actual_size expected_size
    actual_digest="sha256:$(sha256_of "${MANIFEST}")"
    [ -n "${expected_digest}" ] || expected_digest="$(header_value 'docker-content-digest:')"
    if [ -n "${expected_digest}" ] && [ "${expected_digest}" != "${actual_digest}" ]; then
        die "${EXIT_DIGEST}" "the manifest body is ${actual_digest}, expected ${expected_digest}"
    fi
    expected_size="$(header_value 'content-length:')"
    actual_size="$(stat -c '%s' "${MANIFEST}")"
    if [ -n "${expected_size}" ] && [ "${expected_size}" != "${actual_size}" ]; then
        die "${EXIT_DIGEST}" "the manifest is ${actual_size} bytes but Content-Length said ${expected_size}"
    fi
    log "manifest ${actual_digest} (${actual_size} bytes) ok"
}

fetch_manifest "${VERSION}"
check_manifest_bytes ""

MEDIA_TYPE="$(jq -r '.mediaType // empty' "${MANIFEST}")"
if [ "${MEDIA_TYPE}" = "application/vnd.oci.image.index.v1+json" ] \
    || [ "${MEDIA_TYPE}" = "application/vnd.docker.distribution.manifest.list.v2+json" ]; then
    # An index carries one manifest per platform, plus buildx attestation
    # entries whose platform is "unknown". Pick this host's platform by name
    # rather than guessing at the order.
    log "${IMAGE}:${VERSION} is an index; selecting linux/${PLATFORM_ARCH}${PLATFORM_VARIANT:+/${PLATFORM_VARIANT}}"
    SELECTED="$(jq -r --arg arch "${PLATFORM_ARCH}" --arg variant "${PLATFORM_VARIANT}" '
        [ .manifests[]
          | select(.platform.os == "linux")
          | select(.platform.architecture == $arch)
          | select($variant == "" or .platform.variant == $variant)
          | select((.mediaType // "") | test("manifest"))
          | .digest ] | first // empty' "${MANIFEST}")"
    [ -n "${SELECTED}" ] \
        || die "${EXIT_MEDIA}" "the index of ${IMAGE}:${VERSION} has no linux/${PLATFORM_ARCH} manifest"
    fetch_manifest "${SELECTED}"
    check_manifest_bytes "${SELECTED}"
    MEDIA_TYPE="$(jq -r '.mediaType // empty' "${MANIFEST}")"
fi

case "${MEDIA_TYPE}" in
    application/vnd.oci.image.manifest.v1+json|application/vnd.docker.distribution.manifest.v2+json)
        ;;
    application/vnd.oci.image.index.v1+json|application/vnd.docker.distribution.manifest.list.v2+json)
        die "${EXIT_MEDIA}" "the platform entry of ${IMAGE}:${VERSION} is itself an index" ;;
    *)
        die "${EXIT_MEDIA}" "unknown manifest media type: ${MEDIA_TYPE:-<none>}" ;;
esac

CONFIG_MEDIA_TYPE="$(jq -r '.config.mediaType // empty' "${MANIFEST}")"
case "${CONFIG_MEDIA_TYPE}" in
    application/vnd.oci.image.config.v1+json|application/vnd.docker.container.image.v1+json) ;;
    *) die "${EXIT_MEDIA}" "unknown config media type: ${CONFIG_MEDIA_TYPE:-<none>}" ;;
esac

# Layers are a mix of tar+zstd and tar+gzip; `docker load` decompresses both.
while IFS= read -r layer_media_type; do
    case "${layer_media_type}" in
        application/vnd.oci.image.layer.v1.tar+zstd \
        |application/vnd.oci.image.layer.v1.tar+gzip \
        |application/vnd.oci.image.layer.v1.tar \
        |application/vnd.docker.image.rootfs.diff.tar.gzip) ;;
        *) die "${EXIT_MEDIA}" "unknown layer media type: ${layer_media_type:-<none>}" ;;
    esac
done < <(jq -r '.layers[].mediaType // empty' "${MANIFEST}")

CONFIG_DIGEST="$(jq -r '.config.digest' "${MANIFEST}")"
CONFIG_SIZE="$(jq -r '.config.size' "${MANIFEST}")"

what_to_run_next() {
    cat <<INSTRUCTIONS

The image is on this host. Nothing has been updated yet.

Take a backup first if you have not, then run the update yourself:

    ha apps update ${SLUG}

The Supervisor's pull will find ${IMAGE}:${VERSION} locally and download
nothing. It removes the old image afterwards, so the backup is the way back:
see the rollback section of SLOW_LINK_DEPLOY.md before you need it.
INSTRUCTIONS
}

# A re-run after the load already happened — a dropped session, a second
# pair of eyes — must not download 795 MB again to say the same thing. This
# is the gate's own comparison, asked before any blob is fetched.
if [ "${DRY_RUN}" -eq 0 ]; then
    ALREADY_LOADED="$(docker image inspect --format '{{.Id}}' "${IMAGE}:${VERSION}" 2>/dev/null || true)"
    if [ "${ALREADY_LOADED}" = "${CONFIG_DIGEST}" ]; then
        log "${IMAGE}:${VERSION} is already on this host and its image ID is the manifest's config digest"
        rm -rf "${WORK}"
        rmdir "${WORK_ROOT}/${SLUG}" "${WORK_ROOT}" 2>/dev/null || true
        what_to_run_next
        exit 0
    fi
fi

# ------------------------------------------------------------- blob download

# One attempt of one blob: 0 when the bytes are all there, 2 when a resume
# was not answered with a 206 and the partial file was thrown away, 1
# otherwise. Always a fresh token and a fresh ghcr URL: the
# redirect ghcr answers with is a signed storage URL that expires in about
# ten minutes, so a resumed transfer must start at /v2/.../blobs/<digest>
# again. `--fail` matters as much: without it a 403 from the expired signed
# URL would be written into the blob file and only the sha256 would notice.
download_attempt() {
    local digest="$1" size="$2" dest="$3"
    local have=0 token http_code status

    if [ -f "${dest}" ]; then
        have="$(stat -c '%s' "${dest}")"
        if [ "${have}" -gt "${size}" ]; then
            rm -f "${dest}"
            have=0
        fi
    fi
    [ "${have}" -eq "${size}" ] && return 0

    token="$(ghcr_token)" || return 1
    status=0
    http_code="$(curl -sS -L --fail -C - \
        --connect-timeout 30 \
        --speed-limit "${SPEED_LIMIT}" --speed-time "${SPEED_TIME}" \
        -H "Authorization: Bearer ${token}" \
        -o "${dest}" -w '%{http_code}' \
        "https://${REGISTRY}/v2/${REPO}/blobs/${digest}")" || status=$?

    if [ "${have}" -gt 0 ] && [ "${http_code}" != "206" ]; then
        # A resume is only ever accepted as a 206. A 200 means the server
        # ignored the range and would have restarted the blob at byte zero
        # on top of what is already there, so the partial file goes. A
        # transport failure with no response (000) keeps it, because that is
        # the ordinary dropped connection this script is here to resume.
        if [ "${status}" -eq 0 ] || [ "${http_code}" = "200" ] || [ "${http_code}" = "416" ]; then
            log "  the resume was not answered with 206 (HTTP ${http_code}); starting this blob again"
            rm -f "${dest}"
            return 2
        fi
        log "  the resume did not complete (HTTP ${http_code:-000}); keeping the ${have} bytes already here"
        return 1
    fi
    [ "${status}" -eq 0 ] || return 1

    [ "$(stat -c '%s' "${dest}")" -eq "${size}" ] || return 1
    return 0
}

# A whole blob: attempts with backoff, then the sha256. A blob that fails its
# sha256 is deleted and downloaded again, because a truncated or poisoned
# resume is exactly what this script is here to survive.
# Returns 0, or the exit code the last attempt earned: EXIT_DIGEST when the
# bytes arrived but never matched, EXIT_DOWNLOAD when they stopped arriving.
# Those are two different things to tell the operator: one is the link, the
# other is not. A blob that fails its sha256 is deleted and downloaded
# again, because a truncated or poisoned resume is exactly what this script
# is here to survive.
fetch_blob() {
    local digest="$1" size="$2" dest="$3" what="$4"
    local stalled=0 bad_digests=0 restarts=0 attempts=0 high_water=0 delay=5
    local actual before after status
    local last_failure="${EXIT_DOWNLOAD}"

    while [ "${attempts}" -lt "${MAX_ATTEMPTS}" ]; do
        attempts=$((attempts + 1))
        before=0
        if [ -f "${dest}" ]; then before="$(stat -c '%s' "${dest}")"; fi
        if [ "${before}" -gt "${high_water}" ]; then high_water="${before}"; fi

        status=0
        download_attempt "${digest}" "${size}" "${dest}" || status=$?
        if [ "${status}" -eq 0 ]; then
            actual="sha256:$(sha256_of "${dest}")"
            if [ "${actual}" = "${digest}" ]; then
                log "  ${what} ok (${size} bytes)"
                return 0
            fi
            # A fresh start for this blob, bounded by MAX_BAD_DIGESTS
            # rather than by the stall budget: the bytes were arriving, so
            # the link is not what is wrong, and the download that follows
            # deserves the same budget the first one had.
            last_failure="${EXIT_DIGEST}"
            bad_digests=$((bad_digests + 1))
            log "  ${what} is ${actual}, expected ${digest}; deleting and downloading again (${bad_digests}/${MAX_BAD_DIGESTS})"
            rm -f "${dest}"
            high_water=0
            stalled=0
            delay=5
            [ "${bad_digests}" -lt "${MAX_BAD_DIGESTS}" ] || break
        elif [ "${status}" -eq 2 ]; then
            # The blob is back at zero through no fault of the link, so the
            # stall budget starts again with it. Bounded on its own count,
            # or a server that answers every resume this way would keep the
            # loop alive for ever.
            last_failure="${EXIT_DOWNLOAD}"
            restarts=$((restarts + 1))
            high_water=0
            stalled=0
            delay=5
            log "  ${what} starts again from zero (${restarts}/${MAX_RESTARTS})"
            [ "${restarts}" -lt "${MAX_RESTARTS}" ] || break
        else
            after=0
            if [ -f "${dest}" ]; then after="$(stat -c '%s' "${dest}")"; fi
            last_failure="${EXIT_DOWNLOAD}"
            # Progress means further than this blob has ever reached. A
            # server that keeps answering with the same short body would
            # otherwise look like progress on every single attempt.
            if [ "${after}" -gt "${high_water}" ]; then
                high_water="${after}"
                stalled=0
                delay=5
                log "  ${what} is at ${after}/${size} bytes and the connection went; resuming"
            else
                stalled=$((stalled + 1))
                log "  ${what} got no further than ${high_water}/${size} bytes (${stalled}/${MAX_STALLED})"
            fi
        fi

        [ "${stalled}" -lt "${MAX_STALLED}" ] || break
        log "  retrying in ${delay}s"
        sleep "${delay}"
        [ "${delay}" -lt 60 ] && delay=$((delay * 2))
    done
    return "${last_failure}"
}

blob_or_die() {
    local digest="$1" what="$4" status=0
    fetch_blob "$@" || status=$?
    [ "${status}" -eq 0 ] && return 0
    if [ "${status}" -eq "${EXIT_DIGEST}" ]; then
        die "${EXIT_DIGEST}" "${what} never matched ${digest}; the retry budget ran out"
    fi
    die "${EXIT_DOWNLOAD}" "${what} did not finish downloading: a retry budget ran out, see the lines above for which"
}

CONFIG_FILE="${BLOBS}/${CONFIG_DIGEST#sha256:}.json"
log "config ${CONFIG_DIGEST} (${CONFIG_SIZE} bytes)"
blob_or_die "${CONFIG_DIGEST}" "${CONFIG_SIZE}" "${CONFIG_FILE}" "the config blob"

# Digest and size together, in manifest order. Two layers can carry the same
# digest, so the size is never looked up by digest.
LAYER_DIGESTS=()
LAYER_SIZES=()
while read -r digest size; do
    LAYER_DIGESTS+=("${digest}")
    LAYER_SIZES+=("${size}")
done < <(jq -r '.layers[] | "\(.digest) \(.size)"' "${MANIFEST}")

TOTAL_LAYER_BYTES="$(jq -r '[.layers[].size] | add' "${MANIFEST}")"

if [ "${DRY_RUN}" -eq 1 ]; then
    log "dry run: the manifest and the config are verified."
    log "dry run: ${#LAYER_DIGESTS[@]} layers, ${TOTAL_LAYER_BYTES} bytes, not downloaded."
    log "dry run: ${WORK} is kept; run again without --dry-run to finish."
    exit 0
fi

log "${#LAYER_DIGESTS[@]} layers, ${TOTAL_LAYER_BYTES} bytes"
for i in "${!LAYER_DIGESTS[@]}"; do
    digest="${LAYER_DIGESTS[i]}"
    size="${LAYER_SIZES[i]}"
    log "layer $((i + 1))/${#LAYER_DIGESTS[@]} ${digest} (${size} bytes)"
    blob_or_die "${digest}" "${size}" "${BLOBS}/${digest#sha256:}" "layer $((i + 1))"
done

# ------------------------------------------------------------------- load

# The docker-archive manifest: the config, the tag the Supervisor will look
# for, and the layers in manifest order.
ARCHIVE_MANIFEST="${WORK}/manifest.json"
jq -n \
    --arg config "blobs/${CONFIG_DIGEST#sha256:}.json" \
    --arg tag "${IMAGE}:${VERSION}" \
    --slurpfile manifest "${MANIFEST}" \
    '[{Config: $config,
       RepoTags: [$tag],
       Layers: ($manifest[0].layers | map("blobs/" + (.digest | sub("^sha256:"; ""))))}]' \
    > "${ARCHIVE_MANIFEST}"

MEMBERS=("manifest.json" "blobs/${CONFIG_DIGEST#sha256:}.json")
for digest in "${LAYER_DIGESTS[@]}"; do
    MEMBERS+=("blobs/${digest#sha256:}")
done

log "loading ${IMAGE}:${VERSION} into docker"
# Streamed: the archive is never written to /share a second time.
tar -C "${WORK}" -cf - "${MEMBERS[@]}" | docker load \
    || die "${EXIT_LOAD}" "\`docker load\` failed"

# ------------------------------------------------------------------- gate

LOADED_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}:${VERSION}" 2>/dev/null || true)"
if [ "${LOADED_ID}" != "${CONFIG_DIGEST}" ]; then
    die "${EXIT_GATE}" "the loaded image is ${LOADED_ID:-<absent>} but the manifest's config digest is ${CONFIG_DIGEST}; ${WORK} is kept"
fi
log "gate ok: the loaded image ID is the manifest's config digest"

rm -rf "${WORK}"
rmdir "${WORK_ROOT}/${SLUG}" "${WORK_ROOT}" 2>/dev/null || true
log "removed ${WORK}"

what_to_run_next
