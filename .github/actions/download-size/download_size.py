#!/usr/bin/env python3
"""What a host downloads when it updates to this Release (issue #155).

A host that pulls a new add-on version only downloads the layers it does
not already have. This reads the new image's manifest and each comparison
base's manifest straight from the registry and reports, per architecture,
the compressed size of the layers the base does not carry: the bytes an
existing host actually has to fetch.

It runs in a Release step that may fail without failing the Release, and
writes a markdown table the Release notes append. Manifests come from
`docker buildx imagetools inspect --raw`, which reads a public package
anonymously; the fetch is a parameter everywhere below, so the unit test
feeds recorded manifest JSON and never touches a network.

  download_size.py ghcr.io/woowtech/woow-ha-odoo-amd64:0.4.6 \
      ghcr.io/woowtech/woow-ha-odoo-aarch64:0.4.6 \
      --release-tag v0.4.5 --release-tag v0.4.4 --output download-size.md
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# The two architectures the add-on publishes, and the OCI platform each one
# is called by in a manifest index.
PLATFORMS = {
    "amd64": ("linux", "amd64"),
    "aarch64": ("linux", "arm64"),
}

MIB = 1024 * 1024
DEFAULT_LIMIT = 3
# Over this, updating from the previous Release gets a ::warning:: — never a
# failure. The images are pushed by the time this runs, so there is nothing
# left to stop; a number nobody likes is not a reason to withhold the tag.
DEFAULT_WARN_MIB = 100.0
# 0.3.x and older were released without images, so they are not bases.
MIN_BASE_VERSION = (0, 4, 0)

HEADING = "**Download when updating from…**"
NO_EARLIER = "(no earlier image)"
MISSING_CELL = "—"

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class ManifestUnavailable(Exception):
    """A manifest could not be read: no such tag, or nothing usable in it."""


def parse_version(tag: str):
    """(major, minor, patch) for a release tag, or None if it is not one."""
    match = VERSION_RE.match(tag.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def as_tag(version: tuple) -> str:
    return ".".join(str(part) for part in version)


def require_version(tag: str) -> tuple:
    """`parse_version`, for somewhere a tag that is not a version is an error."""
    parsed = parse_version(tag)
    if parsed is None:
        raise ValueError(f"{tag!r} is not an x.y.z version")
    return parsed


def select_bases(tags, new_version, limit=DEFAULT_LIMIT, minimum=MIN_BASE_VERSION):
    """The last `limit` published versions below `new_version`, newest first.

    Fed the tag names of every GitHub Release. Anything that is not an
    x.y.z tag, anything before the first version with images, and the new
    version itself (an images-only run may rebuild a published version)
    are all dropped.
    """
    kept = set()
    for tag in tags:
        version = parse_version(tag)
        if version is None or version < minimum:
            continue
        if new_version is not None and version >= new_version:
            continue
        kept.add(version)
    return [as_tag(version) for version in sorted(kept, reverse=True)[:limit]]


def split_ref(ref: str):
    """An image reference as (repository, tag)."""
    repository, separator, tag = ref.rpartition(":")
    if not separator or "/" in tag:
        raise ValueError(f"{ref!r} is not a name:tag image reference")
    return repository, tag


def arch_of(ref: str) -> str:
    """The architecture an image reference names by its `-<arch>` suffix."""
    name = split_ref(ref)[0].rsplit("/", 1)[-1]
    arch = name.rsplit("-", 1)[-1]
    if arch not in PLATFORMS:
        raise ValueError(
            f"{ref!r}: the image name ends in {arch!r}; expected one of "
            + ", ".join(sorted(PLATFORMS))
        )
    return arch


def imagetools_fetch(ref: str) -> dict:
    """The raw manifest of `ref`, read from the registry."""
    process = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", ref],
        capture_output=True, text=True, check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip().splitlines()
        raise ManifestUnavailable(f"{ref}: {detail[-1] if detail else 'not found'}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise ManifestUnavailable(f"{ref}: the manifest is not JSON ({error})") from error


def layers(ref: str, arch: str, fetch):
    """[(digest, compressed size)] of the single-platform manifest for `arch`.

    An index (a manifest list) is resolved to the one manifest for this
    architecture first. Attestation entries carry the platform
    `unknown/unknown`, so they never match.
    """
    document = fetch(ref)
    if document.get("manifests"):
        repository = split_ref(ref)[0]
        wanted = PLATFORMS[arch]
        for entry in document["manifests"]:
            platform = entry.get("platform") or {}
            if (platform.get("os"), platform.get("architecture")) == wanted:
                document = fetch(f"{repository}@{entry['digest']}")
                break
        else:
            raise ManifestUnavailable(
                f"{ref}: the index carries no {wanted[0]}/{wanted[1]} manifest"
            )
    entries = document.get("layers")
    if not entries:
        raise ManifestUnavailable(f"{ref}: the manifest carries no layers")
    return [(entry["digest"], int(entry["size"])) for entry in entries]


def render(arches, rows, notes) -> str:
    """The markdown table, one row per base and one column per architecture."""
    lines = [HEADING, ""]
    lines.append("| From | " + " | ".join(arches) + " |")
    lines.append("| --- |" + " ---: |" * len(arches))
    for label, cells in rows:
        values = [
            MISSING_CELL if cells[arch] is None else f"{cells[arch]:.1f} MiB"
            for arch in arches
        ]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    if notes:
        lines.append("")
        lines.extend(f"_{note}_" for note in notes)
    return "\n".join(lines) + "\n"


def report(new_refs, bases, fetch, warn_mib=DEFAULT_WARN_MIB):
    """(markdown table, workflow annotations) for these images and bases.

    `bases` are versions, newest first; the first is the previous Release,
    and the warning is about that hop and no other -- if its image cannot
    be read the run says so instead of judging an older base in its place.
    A base whose image is missing everywhere is skipped with a note; one
    missing on a single architecture keeps its row with that cell blank.

    With no bases at all -- nothing published yet that had images -- the
    table shows the full download. Bases that were named and then could
    not be read are a different thing: what the update costs is unknown,
    not the whole image, so that raises rather than publishing a number
    nobody measured.
    """
    arches = []
    for ref in new_refs:
        arch = arch_of(ref)
        if arch in arches:
            raise ValueError(f"two new images for {arch}; expected one per architecture")
        arches.append(arch)
    new = {arch: layers(ref, arch, fetch) for arch, ref in zip(arches, new_refs)}
    repositories = {arch: split_ref(ref)[0] for arch, ref in zip(arches, new_refs)}

    rows, notes, annotations = [], [], []
    for version in bases:
        cells, missing = {}, []
        for arch in arches:
            try:
                carried = {digest for digest, _ in
                           layers(f"{repositories[arch]}:{version}", arch, fetch)}
            except ManifestUnavailable:
                cells[arch] = None
                missing.append(arch)
                continue
            cells[arch] = sum(size for digest, size in new[arch]
                              if digest not in carried) / MIB
        if len(missing) == len(arches):
            notes.append(f"{version}: no image could be read; skipped.")
            continue
        if missing:
            notes.append(
                f"{version}: no image could be read for {', '.join(missing)}; "
                "that column is blank.")
        rows.append((version, cells))

    if not rows:
        if bases:
            raise ManifestUnavailable(
                "none of the images to compare against (" + ", ".join(bases)
                + ") could be read")
        notes.insert(0, "No earlier image to compare against; this is the full download.")
        rows.append((NO_EARLIER,
                     {arch: sum(size for _, size in new[arch]) / MIB for arch in arches}))
    elif rows[0][0] != bases[0]:
        # The budget is about the hop every host takes, and that row is not
        # in the table; an older base is a different question, not a stand-in.
        annotations.append(
            f"::notice::no image for {bases[0]}, the previous Release, so what "
            "this update costs a host on it was not checked"
        )
    else:
        previous, cells = rows[0]
        for arch in arches:
            if cells[arch] is None:
                # `imagetools inspect` says the same thing about a tag that
                # was never pushed and a registry having a bad minute, so
                # this cannot be reported as a cost of nothing.
                annotations.append(
                    f"::notice::no image for {previous} on {arch}, so what this "
                    "update costs a host on the previous Release was not checked there"
                )
            elif cells[arch] > warn_mib:
                annotations.append(
                    f"::warning::updating from {previous} downloads "
                    f"{cells[arch]:.1f} MiB on {arch}, over {warn_mib:.0f} MiB"
                )
    return render(arches, rows, notes), annotations


def main(argv=None, fetch=imagetools_fetch) -> int:
    parser = argparse.ArgumentParser(
        description="Report what a host downloads when it updates to this version.")
    parser.add_argument("new_ref", nargs="+",
                        help="the new image reference, one per architecture")
    parser.add_argument("--release-tag", action="append", default=[], dest="release_tags",
                        metavar="TAG",
                        help="a published Release tag; the last few become the bases")
    parser.add_argument("--base", action="append", default=[], dest="bases",
                        metavar="VERSION",
                        help="a base version, newest first, instead of selecting them")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"how many bases to select (default {DEFAULT_LIMIT})")
    parser.add_argument("--warn-mib", type=float, default=DEFAULT_WARN_MIB,
                        help="warn when the previous Release costs more than this")
    parser.add_argument("--output", type=Path,
                        help="write the table here instead of to stdout")
    args = parser.parse_args(argv)

    try:
        new_version = parse_version(split_ref(args.new_ref[0])[1])
        bases = ([as_tag(require_version(base)) for base in args.bases] if args.bases
                 else select_bases(args.release_tags, new_version, args.limit))
        table, annotations = report(args.new_ref, bases, fetch, args.warn_mib)
    except (ManifestUnavailable, ValueError) as error:
        # The caller runs this with continue-on-error; saying why is the
        # whole job of a non-zero exit here.
        print(f"::error::download size: {error}")
        return 1
    if args.output:
        args.output.write_text(table, encoding="utf-8")
    else:
        sys.stdout.write(table)
    for annotation in annotations:
        print(annotation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
