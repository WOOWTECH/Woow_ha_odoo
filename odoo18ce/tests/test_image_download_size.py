#!/usr/bin/env python3
"""Unit tests for the Release download-size table (issue #155).

The script the Release workflow runs to answer "how much does this update
cost a host that already runs the previous version". Every manifest here
is recorded JSON under `fixtures/manifests`, read through a fake fetch, so
the tests never reach a registry:

* `woow-ha-odoo-{amd64,aarch64}-0.4.{4,5}.json` are the real published
  manifests. Between 0.4.4 and 0.4.5 amd64 shared every big layer and
  aarch64 shared none, which is the evidence that opened the issue — so
  the shared-layer case, the all-new case and the >100 MiB warning are all
  real data rather than invented numbers.
* `buildkit-v0.33.0-index.json` is a real OCI index, attestation entries
  and all, for the manifest-list case.
"""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT.parent / ".github/actions/download-size/download_size.py"
MANIFESTS = Path(__file__).resolve().parent / "fixtures/manifests"

IMAGE_BASE = "ghcr.io/woowtech/woow-ha-odoo"
BUILDKIT = "docker.io/moby/buildkit"


def load_module(path: Path, name: str):
    """The way `test_rewrite_apply.py:43` loads a script by path."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


size = load_module(SCRIPT, "download_size")


def recorded(name: str) -> dict:
    return json.loads((MANIFESTS / f"{name}.json").read_text(encoding="utf-8"))


def fetcher(manifests: dict):
    """A fetch that serves recorded JSON and 404s everything else."""
    def fetch(ref: str) -> dict:
        if ref not in manifests:
            raise size.ManifestUnavailable(f"{ref}: not found")
        return manifests[ref]
    return fetch


def published(*versions: str) -> dict:
    """The real manifests for these versions, keyed by image reference."""
    return {
        f"{IMAGE_BASE}-{arch}:{version}": recorded(f"woow-ha-odoo-{arch}-{version}")
        for arch in ("amd64", "aarch64")
        for version in versions
    }


AMD64_LATEST = f"{IMAGE_BASE}-amd64:0.4.5"


def new_refs(version: str) -> list:
    return [f"{IMAGE_BASE}-{arch}:{version}" for arch in ("amd64", "aarch64")]


def cell(table: str, row_label: str, column: int) -> str:
    """One cell of the rendered table, by its row label and column number."""
    for line in table.splitlines():
        if line.startswith(f"| {row_label} |"):
            return [part.strip() for part in line.strip("|").split("|")][column]
    raise AssertionError(f"no row {row_label!r} in:\n{table}")


# --- the layer arithmetic -------------------------------------------------

def test_shared_layers_cost_only_what_changed() -> None:
    """0.4.4 -> 0.4.5 on amd64 hit the cache: everything big was reused."""
    table, annotations = size.report(
        [AMD64_LATEST], ["0.4.4"], fetcher(published("0.4.5", "0.4.4")))
    assert cell(table, "0.4.4", 1) == "0.1 MiB", table
    assert not annotations, "0.1 MiB is nowhere near the warning threshold"


def test_all_new_layers_cost_the_whole_image() -> None:
    """A rebuild that misses the cache changes every digest, so nothing is reused.

    Standing in for it: the recorded aarch64 0.4.4 manifest as the amd64
    base. It shares no layer with amd64 0.4.5, which is what a full
    cache miss looks like.
    """
    manifests = published("0.4.5")
    manifests[f"{IMAGE_BASE}-amd64:0.4.4"] = recorded("woow-ha-odoo-aarch64-0.4.4")
    new = manifests[AMD64_LATEST]
    assert not ({layer["digest"] for layer in new["layers"]}
                & {layer["digest"] for layer
                   in manifests[f"{IMAGE_BASE}-amd64:0.4.4"]["layers"]})

    table, annotations = size.report([AMD64_LATEST], ["0.4.4"], fetcher(manifests))
    whole = sum(layer["size"] for layer in new["layers"]) / size.MIB
    assert cell(table, "0.4.4", 1) == f"{whole:.1f} MiB", table
    assert annotations, "a whole-image download is well over the threshold"


def test_a_base_missing_everywhere_is_skipped_with_a_note() -> None:
    table, _ = size.report(
        new_refs("0.4.5"), ["0.4.4", "0.4.3"], fetcher(published("0.4.5", "0.4.4")))
    assert "| 0.4.3 |" not in table, table
    assert "_0.4.3: no published image; skipped._" in table, table


def test_a_base_missing_on_one_arch_keeps_its_row_blank_there() -> None:
    manifests = published("0.4.5", "0.4.4")
    del manifests[f"{IMAGE_BASE}-aarch64:0.4.4"]
    table, _ = size.report(new_refs("0.4.5"), ["0.4.4"], fetcher(manifests))
    assert cell(table, "0.4.4", 1) == "0.1 MiB", table
    assert cell(table, "0.4.4", 2) == size.MISSING_CELL, table
    assert "_0.4.4: no image for aarch64; that column is blank._" in table, table


def test_with_no_earlier_image_it_prints_the_full_size() -> None:
    manifests = published("0.4.5")
    table, annotations = size.report(new_refs("0.4.5"), [], fetcher(manifests))
    whole = sum(layer["size"] for layer
                in manifests[f"{IMAGE_BASE}-amd64:0.4.5"]["layers"]) / size.MIB
    assert cell(table, size.NO_EARLIER, 1) == f"{whole:.1f} MiB", table
    assert "No earlier image" in table, table
    assert not annotations, "a first image has no previous Release to warn about"


def test_an_index_is_resolved_to_the_single_platform_manifest() -> None:
    """A manifest list, attestation entries and all, resolves by platform."""
    index = recorded("buildkit-v0.33.0-index")
    amd64 = next(entry["digest"] for entry in index["manifests"]
                 if entry.get("platform", {}).get("architecture") == "amd64")
    manifest = recorded("buildkit-v0.33.0-amd64")
    fetch = fetcher({f"{BUILDKIT}-amd64:v0.33.0": index,
                     f"{BUILDKIT}-amd64@{amd64}": manifest})

    assert size.layers(f"{BUILDKIT}-amd64:v0.33.0", "amd64", fetch) == [
        (layer["digest"], layer["size"]) for layer in manifest["layers"]]


def test_an_index_without_this_platform_is_unavailable() -> None:
    fetch = fetcher({f"{BUILDKIT}-aarch64:v0.33.0": {"manifests": [
        {"digest": "sha256:deadbeef", "platform": {"os": "linux", "architecture": "amd64"}},
        {"digest": "sha256:cafe", "platform": {"os": "unknown", "architecture": "unknown"}},
    ]}})
    with pytest.raises(size.ManifestUnavailable, match="no linux/arm64 manifest"):
        size.layers(f"{BUILDKIT}-aarch64:v0.33.0", "aarch64", fetch)


# --- the warning ----------------------------------------------------------

def test_over_the_threshold_the_previous_release_gets_a_warning() -> None:
    _, annotations = size.report(
        new_refs("0.4.5"), ["0.4.4"], fetcher(published("0.4.5", "0.4.4")))
    assert len(annotations) == 1, annotations
    assert annotations[0].startswith("::warning::"), annotations
    assert "aarch64" in annotations[0] and "over 100 MiB" in annotations[0], annotations


def test_only_the_previous_release_is_warned_about() -> None:
    """The older rows are information; the budget is about the last hop.

    Here the previous Release costs 0.1 MiB and the one before it the
    whole image, and only the first row is judged.
    """
    manifests = published("0.4.5", "0.4.4")
    manifests[f"{IMAGE_BASE}-amd64:0.4.3"] = recorded("woow-ha-odoo-aarch64-0.4.4")
    table, annotations = size.report(
        [AMD64_LATEST], ["0.4.4", "0.4.3"], fetcher(manifests))
    assert cell(table, "0.4.3", 1).endswith("MiB") and cell(table, "0.4.3", 1) != "0.1 MiB"
    assert annotations == [], annotations


# --- choosing the bases ---------------------------------------------------

def test_the_last_three_releases_by_semver_become_the_bases() -> None:
    tags = ["v0.4.1", "v0.4.5", "v0.4.0", "v0.4.4", "v0.4.2", "v0.4.3"]
    assert size.select_bases(tags, (0, 4, 6)) == ["0.4.5", "0.4.4", "0.4.3"]


def test_versions_without_images_and_the_new_version_are_not_bases() -> None:
    tags = ["v0.4.6", "v0.4.5", "v0.3.9", "v0.2.0", "not-a-version", "v0.4.0"]
    assert size.select_bases(tags, (0, 4, 6)) == ["0.4.5", "0.4.0"]


def test_an_images_only_rerun_of_a_published_version_is_not_its_own_base() -> None:
    assert size.select_bases(["v0.4.5", "v0.4.4"], (0, 4, 5)) == ["0.4.4"]


# --- the command line -----------------------------------------------------

def test_the_cli_writes_the_table_and_prints_the_warning(tmp_path, capsys) -> None:
    output = tmp_path / "download-size.md"
    code = size.main(
        new_refs("0.4.5") + ["--release-tag", "v0.4.4", "--release-tag", "v0.3.9",
                             "--output", str(output)],
        fetch=fetcher(published("0.4.5", "0.4.4")))
    assert code == 0
    table = output.read_text(encoding="utf-8")
    assert size.HEADING in table and "| 0.4.4 |" in table, table
    assert "::warning::" in capsys.readouterr().out
    assert "| From | amd64 | aarch64 |" in table, table


def test_the_cli_reports_an_unreadable_new_image_as_an_error(tmp_path, capsys) -> None:
    code = size.main(new_refs("0.4.6"), fetch=fetcher(published("0.4.5")))
    assert code == 1
    assert "::error::download size:" in capsys.readouterr().out


def test_the_architecture_comes_from_the_image_name() -> None:
    assert size.arch_of(f"{IMAGE_BASE}-aarch64:0.4.5") == "aarch64"
    with pytest.raises(ValueError, match="expected one of"):
        size.arch_of("ghcr.io/woowtech/woow-ha-odoo:0.4.5")
