#!/usr/bin/env python3
"""Merge a pinned Odoo `.deb`'s `Depends` into `odoo-deb-depends.txt` (#156).

The weekly bump bot (`.github/workflows/odoo-bump.yml`) downloads the new Odoo
nightly package to hash it. This folds the same package's `Depends` field into
the committed `odoo18ce/odoo-deb-depends.txt`.

A **merge**, never a regenerate. The committed file carries four things the
`.deb` cannot supply, and a plain rewrite loses them and turns the guard test
`odoo18ce/tests/test_dockerfile_layers.py` red:

* which member of an alternatives group apt resolves on the pinned base image
  -- `python3-lxml-html-clean | python3-lxml` resolves to the *second* name,
  because bookworm has no first one;
* `satisfied-by`, which records that layer (a) installs a metapackage instead;
* `deferred`, a dependency the `.deb` gained that layer (a) does not install;
* `dropped`, one the `.deb` lost that layer (a) still installs.

The last two are why a routine weekly bump re-sends layer (b) and the small
layers under it and not layer (a) as well -- about 380 MiB rather than the
whole image; ADR 0013 holds the measured figures, and its own `.deb`-download
numbers are not the compressed layers a host downloads. Layer (a) is left
alone and apt resolves the difference into layer (b), where a gained
dependency costs a few MiB. Gaining a dependency therefore keeps the static tier
**green** -- `build-amd64` and `build-aarch64` need it, so a red static tier
would cost the bump pull request the image build ADR 0002's human merge rests
on.

One question is deliberately not answered here: which member of an alternatives
group the base image resolves. It lives in `apt-cache policy` inside the base
image, not in the `.deb`, so a group this file cannot resolve is left exactly
as it is and named in the pull request body for a human. Nothing breaks
meanwhile -- a dependency the list misses is installed by apt into layer (b).

Usage:

    odoo_deb_depends.py --list odoo18ce/odoo-deb-depends.txt \\
      --dockerfile odoo18ce/Dockerfile --depends-field - \\
      --deb-version 18.0.20260930 [--date 2026-09-30] [--report report.md]

The merge is unit-tested in `odoo18ce/tests/test_odoo_deb_depends.py`, down to
a no-op against the real field of the currently pinned package.
"""
import argparse
import datetime
import re
import sys
from dataclasses import dataclass, field as field_default

# The note kinds, in the order they are written on a line. `alternatives`,
# `version` and `qualifier` are read out of the `.deb` on every merge; the
# rest are hand-written state carried forward. They are documented at the top
# of odoo-deb-depends.txt and parsed by the guard test.
DERIVED_NOTES = ("alternatives", "version", "qualifier")
NOTE_ORDER = DERIVED_NOTES + ("satisfied-by", "deferred", "dropped")

SOURCE_LINE = re.compile(r"^# source: odoo_(\S+)_all\.deb$", re.M)


def deferred_note(deb_version: str, date: str) -> str:
    return (f"gained by odoo_{deb_version}_all.deb ({date}); apt installs it "
            f"into layer (b), and it is folded into (a) at the next event "
            f"that rebuilds (a)")


def dropped_note(deb_version: str, date: str) -> str:
    return (f"gone from odoo_{deb_version}_all.deb's Depends ({date}); layer "
            f"(a) still installs it, and it is removed at the next event that "
            f"rebuilds (a)")


# ── the Dockerfile's layer (a) ─────────────────────────────────────────────
#
# The same reading as the guard test's, which owns it;
# `test_the_script_reads_layer_a_the_way_the_guard_test_does` holds the two
# equal. The bot needs it for one decision: a name the `.deb` stopped naming
# is removed from the list only when (a) does not install it.


def instructions(dockerfile: str) -> list:
    """The Dockerfile's instructions, continuations joined and comments gone."""
    joined = []
    buf = ""
    for line in dockerfile.splitlines():
        if line.strip().startswith("#"):
            continue
        if line.rstrip().endswith("\\"):
            buf += line.rstrip()[:-1] + " "
            continue
        buf += line
        if buf.strip():
            joined.append(" ".join(buf.split()))
        buf = ""
    if buf.strip():
        joined.append(" ".join(buf.split()))
    return joined


def apt_packages(run: str) -> list:
    """The package names one normalized apt `RUN` installs, flags dropped."""
    words = []
    for found in re.finditer(r"apt-get install (.*?)(?: &&|$)", run):
        words += [word for word in found.group(1).split()
                  if not word.startswith("-")]
    return words


def layer_a_packages(dockerfile: str) -> list:
    """What layer (a) installs. Found by content: it is the RUN with
    `postgresql-16` in it, the way the guard test finds it."""
    for one in instructions(dockerfile):
        if one.startswith("RUN ") and "postgresql-16" in apt_packages(one):
            return apt_packages(one)
    raise ValueError("the Dockerfile has no layer (a): no apt RUN installs "
                     "postgresql-16")


# ── the committed list ─────────────────────────────────────────────────────


def source_version(list_text: str) -> str | None:
    """The `.deb` version the list says it was generated from, or None."""
    found = SOURCE_LINE.search(list_text)
    return found.group(1) if found else None


def read_list(list_text: str) -> tuple:
    """`(prologue, entries, block)` for the committed list.

    `prologue` is the comment header verbatim, `entries` is a list of
    `(name, notes)` in file order, and `block` is the entry lines as they
    stand -- compared against the merged rendering so that a merge which
    changes nothing writes nothing.
    """
    lines = list_text.splitlines(keepends=True)
    first = None
    for at, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#"):
            first = at
            break
    if first is None:
        raise ValueError("odoo-deb-depends.txt names no packages at all")
    prologue = "".join(lines[:first])
    block = "".join(lines[first:])
    entries = []
    for line in lines[first:]:
        if not line.strip() or line.lstrip().startswith("#"):
            raise ValueError(
                "odoo-deb-depends.txt: a comment or blank line below the "
                f"first package line ({line.strip()!r}) cannot be carried "
                "through a merge; comments belong above the list")
        entries.append(read_entry(line.rstrip("\n")))
    return prologue, entries, block


def read_entry(line: str) -> tuple:
    """One list line as `(name, notes)`. The guard test's parser, in short.

    A note is `<kind>: <value>` and several are separated by `; `. A value is
    prose that may contain a semicolon, as long as what follows it does not
    itself open a note -- so a misspelled kind survives into the output and
    the guard test reports it rather than the bot swallowing it.
    """
    name, _, raw = line.partition("  # ")
    notes = {}
    kind = None
    for part in raw.split("; "):
        opener = re.match(r"([a-z][a-z0-9-]*):\s*(.*)$", part)
        if opener:
            kind = opener.group(1)
            notes[kind] = opener.group(2).strip()
        elif kind is not None:
            notes[kind] = (notes[kind] + "; " + part).strip()
        elif part.strip():
            notes[part.strip()] = ""
    return name.strip(), notes


def render_entry(name: str, notes: dict) -> str:
    kinds = ([kind for kind in NOTE_ORDER if kind in notes]
             + [kind for kind in notes if kind not in NOTE_ORDER])
    if not kinds:
        return name
    written = "; ".join(f"{kind}: {notes[kind]}".rstrip() for kind in kinds)
    return f"{name}  # {written}"


def render_block(entries: dict) -> str:
    """The entry lines, sorted the way `LC_ALL=C sort` sorts them."""
    return "".join(
        render_entry(name, entries[name]) + "\n"
        for name in sorted(entries, key=lambda one: one.encode()))


# ── the `.deb`'s field ─────────────────────────────────────────────────────


def split_field(depends: str) -> list:
    """A `Depends` field as its entries, the way the list's own `# source:`
    block documents: split on commas and trimmed."""
    return [one.strip() for one in depends.split(",") if one.strip()]


def read_member(member: str) -> tuple:
    """One member of a `Depends` entry as `(name, version, qualifier)`.

    `python3:any (>= 3.7)` is `("python3", "(>= 3.7)", ":any")`. The image is
    single-arch per build, so the plain name installs and the qualifier is
    recorded; the version is recorded and not enforced -- the base image's
    Debian release decides it.
    """
    text = member.strip()
    version = None
    found = re.search(r"\s*(\([^()]*\))$", text)
    if found:
        version = found.group(1)
        text = text[:found.start()].strip()
    qualifier = None
    if ":" in text:
        text, _, arch = text.partition(":")
        qualifier = ":" + arch
    return text, version, qualifier


def read_group(entry: str) -> tuple:
    """A `Depends` entry as `(spelling, members)`.

    `spelling` is the alternatives group as the `.deb` wrote it, with `|`
    spaced the way the list documents it; `members` are its parsed names.
    """
    members = [one.strip() for one in entry.split("|")]
    return " | ".join(members), [read_member(one) for one in members]


# ── the merge ──────────────────────────────────────────────────────────────


@dataclass
class Undecided:
    """An alternatives group the list cannot resolve, and what it holds.

    `spelling` is the group as the `.deb` wrote it, `members` are the ones
    the list already names -- none, or more than one, either of which leaves
    the question open -- and `resolves_to` are the entries whose
    `alternatives` note overlaps the group, which is what the list resolved
    an earlier spelling of it to.
    """

    spelling: str
    members: list
    resolves_to: list

    def frozen(self) -> set:
        """Every name the list connects to this group. The merge leaves all
        of them exactly as they are."""
        return set(self.members) | set(self.resolves_to)


@dataclass
class Merged:
    """What the merge produced, and what the pull request body reports.

    The four name lists are what the bot *did* to a line, which is the
    distinction the whole merge turns on:

    * `added` -- a line the `.deb` gained, written with a `deferred` note.
    * `marked_dropped` -- a line the `.deb` lost that **keeps** its place,
      because layer (a) still installs it.
    * `deleted` -- a line the `.deb` lost that is **gone**, because layer (a)
      never installed it.
    * `unmarked_dropped` -- a line whose `dropped` note is gone, because the
      `.deb` depends on it again.
    """

    text: str
    changed: bool
    added: list = field_default(default_factory=list)
    deleted: list = field_default(default_factory=list)
    marked_dropped: list = field_default(default_factory=list)
    unmarked_dropped: list = field_default(default_factory=list)
    regrouped: list = field_default(default_factory=list)
    undecided: list = field_default(default_factory=list)


def merge(list_text: str, depends: str, *, dockerfile: str, deb_version: str,
          date: str | None = None) -> Merged:
    """`list_text` with the `.deb`'s `Depends` merged in."""
    date = date or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    prologue, entries, block = read_list(list_text)
    committed = dict(entries)
    installed = set(layer_a_packages(dockerfile))
    done = Merged(text=list_text, changed=False)

    # Normalization: every entry resolved to one name plus its derived notes.
    resolved = {}
    for entry in split_field(depends):
        spelling, members = read_group(entry)
        if len(members) == 1:
            name, version, qualifier = members[0]
            notes = {}
        else:
            known = [one for one in members if one[0] in committed]
            if len(known) != 1:
                # The one call the bot must not make: which member apt
                # resolves is a fact about the base image, not about the
                # `.deb`. Leave every name the list already connects to this
                # group alone, and ask in the pull request body.
                overlap = sorted(
                    name for name, notes in committed.items()
                    if "alternatives" in notes
                    and {one.strip() for one in notes["alternatives"].split("|")}
                    & {one[0] for one in members})
                done.undecided.append(Undecided(
                    spelling=spelling,
                    members=[one[0] for one in known],
                    resolves_to=overlap))
                continue
            name, version, qualifier = known[0]
            notes = {"alternatives": spelling}
        if version:
            notes["version"] = version
        if qualifier:
            notes["qualifier"] = qualifier
        resolved[name] = notes

    frozen = {name
              for group in done.undecided
              for name in group.frozen()}

    merged = {}
    for name, notes in committed.items():
        if name in resolved:
            # Hand-written notes carry forward; the `.deb`-derived ones are
            # taken from the new field. `dropped` is the exception: the `.deb`
            # depends on the name again, so there is nothing left to explain.
            kept = {kind: value for kind, value in notes.items()
                    if kind not in DERIVED_NOTES and kind != "dropped"}
            if "dropped" in notes:
                done.unmarked_dropped.append(name)
            if notes.get("alternatives") != resolved[name].get("alternatives"):
                done.regrouped.append(name)
            merged[name] = {**resolved[name], **kept}
        elif name in frozen or "dropped" in notes:
            merged[name] = notes
        elif (notes.get("satisfied-by") or name) in installed:
            # Taking it out of layer (a) would rebuild the big layer on a
            # routine bump, so the line stays and says why (ADR 0013).
            merged[name] = {**notes, "dropped": dropped_note(deb_version, date)}
            done.marked_dropped.append(name)
        else:
            # Layer (a) never installed it -- a `deferred` entry -- so
            # removing it costs nothing.
            done.deleted.append(name)

    for name, notes in resolved.items():
        if name in committed:
            continue
        merged[name] = {**notes, "deferred": deferred_note(deb_version, date)}
        done.added.append(name)

    block_after = render_block(merged)
    if block_after == block:
        return done
    done.changed = True
    done.text = rewrite_source(prologue, deb_version) + block_after
    return done


def rewrite_source(prologue: str, deb_version: str) -> str:
    """`prologue` with its `# source:` line naming `deb_version`.

    Only a merge that changed the entries rewrites it: the line is provenance
    for the list below it, and a bump that moved no dependency must leave the
    file -- and so the pull request's diff -- alone.
    """
    line = f"# source: odoo_{deb_version}_all.deb"
    if not SOURCE_LINE.search(prologue):
        raise ValueError("odoo-deb-depends.txt has no '# source:' line to "
                         "record the .deb this list came from")
    return SOURCE_LINE.sub(line, prologue, count=1)


# ── the report the pull request body carries ───────────────────────────────


def quoted(what: list) -> str:
    return ", ".join(f"`{one}`" for one in what)


def report(done: Merged) -> str:
    """What changed in the list, as markdown bullets for the PR body."""
    lines = []
    if done.added:
        lines.append(
            "- Added, recorded `deferred`: %s. Layer (a) is not touched; apt "
            "installs these into layer (b), and they are folded into (a) "
            "at the next event that rebuilds it anyway (ADR-0013)."
            % quoted(done.added))
    if done.marked_dropped:
        lines.append(
            "- Recorded `dropped`: %s. Gone from `Depends`, and layer (a) "
            "still installs these -- taking them out would rebuild layer (a) "
            "on a routine bump and every host would download it again, so "
            "they stay until an event rebuilds it anyway (ADR-0013 holds the "
            "measured sizes)." % quoted(done.marked_dropped))
    if done.deleted:
        lines.append(
            "- Removed: %s. Gone from `Depends`, and layer (a) never "
            "installed these, so the lines cost nothing to drop."
            % quoted(done.deleted))
    if done.unmarked_dropped:
        lines.append(
            "- No longer `dropped`: %s. The nightly depends on these again "
            "and layer (a) installs them, so there is nothing left to "
            "explain." % quoted(done.unmarked_dropped))
    if done.regrouped:
        lines.append(
            "- Alternatives group re-recorded as the `.deb` now spells it: "
            "%s. The member this file resolves to is unchanged."
            % quoted(done.regrouped))
    for group in done.undecided:
        if group.resolves_to:
            held = ("this file resolves that group to %s, which the new "
                    "spelling no longer names" % quoted(group.resolves_to))
        elif group.members:
            held = ("this file records %s, and two members of one group "
                    "cannot both be the one apt resolves"
                    % quoted(group.members))
        else:
            held = "this file records none of its members"
        lines.append(
            "- **Left untouched, needs a human**: `%s` -- %s. Which member "
            "apt resolves is a fact about the base image, not about the "
            "`.deb`: `apt-cache policy <name>` inside it answers. Until "
            "someone records the answer, apt resolves the group while it "
            "installs the `.deb`, into layer (b), which costs a few MiB and "
            "nothing else." % (group.spelling, held))
    if not lines:
        lines.append("- Unchanged: the new package's `Depends` normalizes to "
                     "exactly the committed list.")
    return "\n".join(lines) + "\n"


def unmergeable_report(reason: str) -> str:
    """What the pull request body says when the merge could not be done."""
    return (
        "- **Left untouched, needs a human**: the dependency list could not "
        "be merged -- %s. The list is as it was, so layer (a) and the guard "
        "test still agree; what it costs is that a dependency this nightly "
        "moved is resolved by apt into layer (b), which is a few MiB and "
        "nothing else (ADR-0013). Everything else in this pull request is "
        "unaffected.\n" % reason)


# ── the command ────────────────────────────────────────────────────────────


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", required=True, dest="listing",
                        help="path to odoo-deb-depends.txt, rewritten in place")
    parser.add_argument("--dockerfile", required=True,
                        help="path to the Dockerfile, read for layer (a)")
    parser.add_argument("--depends-field", required=True,
                        help="file holding `dpkg-deb -f <deb> Depends`, or - "
                             "for standard input")
    parser.add_argument("--deb-version", required=True,
                        help="the version of the .deb the field came from")
    parser.add_argument("--date", default=None,
                        help="the bump date a deferred or dropped note names "
                             "(default: today, UTC)")
    parser.add_argument("--report", default=None,
                        help="write the pull-request body section here as well")
    args = parser.parse_args(argv[1:])

    if args.depends_field == "-":
        depends = sys.stdin.read()
    else:
        with open(args.depends_field, encoding="utf-8") as handle:
            depends = handle.read()
    with open(args.listing, encoding="utf-8") as handle:
        list_text = handle.read()
    with open(args.dockerfile, encoding="utf-8") as handle:
        dockerfile = handle.read()

    # A list this cannot merge leaves the command successful and the file
    # untouched, and says so where a human will read it. Failing here would
    # fail the step, and the steps after a failed one do not run -- the weekly
    # bump would lose its pull request, and with it the image build ADR 0002's
    # merge decision rests on, over a list whose whole cost is layer (b) size
    # (ADR 0013). The library raises; only the command fails open.
    done, reason = None, None
    try:
        done = merge(list_text, depends, dockerfile=dockerfile,
                     deb_version=args.deb_version, date=args.date)
    except ValueError as unmergeable:
        reason = str(unmergeable)
    body = unmergeable_report(reason) if done is None else report(done)

    if done is not None and done.changed:
        with open(args.listing, "w", encoding="utf-8") as handle:
            handle.write(done.text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(body)
    sys.stdout.write(body)
    if reason is not None:
        print("::warning::the dependency list was left as it is: %s" % reason,
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
