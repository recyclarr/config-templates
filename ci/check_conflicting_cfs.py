#!/usr/bin/env python3
"""Assert no template can enable two mutually exclusive custom formats.

Usage: check_conflicting_cfs.py <path-to-trash-guides> <path-to-config-repo>

The TRaSH Guides publish conflicts.json, naming sets of custom formats that
must not be enabled together. Recyclarr does not read that file, so these
checks live here instead.

Pass A: each template's effective CF set holds at most one member of any
        conflict set, where the effective set is
        required + (default - exclude) + select.
Pass B: within a commented-out group block, at most one member of a conflict
        set sits at the block's own comment level, so uncommenting the block
        cannot activate several at once.

Both are assertions about the committed text. Neither simulates what a user
might do after editing a template.
"""

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

GROUP_RE = re.compile(r"^(?P<pre>[^-]*)- trash_id:\s*(?P<id>[a-f0-9]{32})")
NODE_RE = re.compile(r"^(?P<pre>[^a-z]*)(?P<node>select|exclude):\s*$")
BARE_RE = re.compile(r"^(?P<pre>[^-]*)-\s*(?P<id>[a-f0-9]{32})")
PROFILE_RE = re.compile(r"^\s*- trash_id:\s*([a-f0-9]{32})\s*#")


@dataclass
class AddEntry:
    active: bool
    select: set[str] = field(default_factory=set)
    exclude: set[str] = field(default_factory=set)


@dataclass
class CommentedEntry:
    line: int
    select: dict[str, int] = field(default_factory=dict)
    exclude: dict[str, int] = field(default_factory=dict)


def error(repo: Path, file: Path, line: int, message: str) -> None:
    rel = file.relative_to(repo).as_posix()
    print(f"::error file={rel},line={line},title=Conflicting Custom Formats::{message}")


def depth(pre: str) -> int:
    """How many comment markers precede the list dash."""
    return pre.count("#")


def check_service(guides: Path, repo: Path, gen, service: str) -> bool:
    json_paths = gen.load_guides(guides)
    conflict_sets = gen.load_conflicts(guides, json_paths, service)
    if not conflict_sets:
        print(
            "::warning title=Conflicting Custom Formats::"
            f"No conflict sets found for {service}; nothing to check"
        )
        return True

    cf_groups = gen.load_cf_groups(guides, json_paths, service)
    names = {
        cf.trash_id: cf.name for g in cf_groups.values() for cf in g.custom_formats
    }

    valid = True
    for path in sorted((repo / service / "templates").rglob("*.yml")):
        print(f"Processing {path}")
        lines = path.read_text(encoding="utf-8").splitlines()

        profile_id = None
        section = None
        group_id = None
        group_depth = 0
        node = None
        adds: dict[str, AddEntry] = {}
        skips: set[str] = set()
        commented: dict[str, CommentedEntry] = {}

        for i, raw in enumerate(lines, start=1):
            stripped = raw.strip()

            if stripped.startswith("quality_profiles:"):
                section, group_id, node = "profiles", None, None
                continue
            if stripped in ("add:", "# add:"):
                section, group_id, node = "add", None, None
                continue
            if stripped in ("skip:", "# skip:"):
                section, group_id, node = "skip", None, None
                continue
            if stripped.startswith("custom_format_groups:"):
                section, group_id, node = None, None, None
                continue

            if section == "profiles" and profile_id is None:
                m = PROFILE_RE.match(raw)
                if m:
                    profile_id = m.group(1)
                continue

            if section == "add":
                m = GROUP_RE.match(raw)
                if m:
                    group_id = m.group("id")
                    group_depth = depth(m.group("pre"))
                    adds[group_id] = AddEntry(active=group_depth == 0)
                    if group_depth > 0:
                        commented[group_id] = CommentedEntry(line=i)
                    node = None
                    continue
                m = NODE_RE.match(raw)
                if m and group_id:
                    node = m.group("node")
                    continue
                m = BARE_RE.match(raw)
                if m and group_id and node:
                    d = depth(m.group("pre"))
                    if d == 0:
                        getattr(adds[group_id], node).add(m.group("id"))
                    if d == group_depth and group_id in commented:
                        getattr(commented[group_id], node)[m.group("id")] = i
                continue

            if section == "skip":
                m = BARE_RE.match(raw)
                if m and depth(m.group("pre")) == 0:
                    skips.add(m.group("id"))
                continue

        if profile_id is None:
            error(repo, path, 1, "No quality profile trash_id found")
            valid = False
            continue

        # Pass A: what this template actually syncs
        effective: set[str] = set()
        for group in cf_groups.values():
            if profile_id not in group.target_profiles.values():
                continue
            if group.trash_id in skips:
                continue
            entry = adds.get(group.trash_id)
            enabled = group.is_default or (entry is not None and entry.active)
            if not enabled:
                continue
            base = {c.trash_id for c in group.custom_formats if c.required or c.default}
            if entry is not None:
                base = (base - entry.exclude) | entry.select
            effective |= base

        for cs in conflict_sets:
            clash = sorted(effective & cs)
            if len(clash) > 1:
                labels = ", ".join(f"{names.get(t, t)} ({t})" for t in clash)
                error(
                    repo,
                    path,
                    1,
                    f"Effective CF set enables conflicting formats: {labels}",
                )
                valid = False

        # Pass B: what one uncomment of a commented block would activate
        for gid, entry in commented.items():
            group = cf_groups.get(gid)
            if group is None:
                continue
            base = {
                cf.trash_id for cf in group.custom_formats if cf.required or cf.default
            }
            effective = (base - entry.exclude.keys()) | entry.select.keys()
            for cs in conflict_sets:
                clash = sorted(effective & cs)
                if len(clash) > 1:
                    labels = ", ".join(f"{names.get(t, t)} ({t})" for t in clash)
                    lines = [
                        entry.select.get(t) or entry.exclude.get(t)
                        for t in clash
                        if t in entry.select or t in entry.exclude
                    ]
                    error(
                        repo,
                        path,
                        lines[-1] if lines else entry.line,
                        f"Group '{group.name}': uncommenting this block would enable "
                        f"conflicting formats: {labels}",
                    )
                    valid = False

    return valid


def load_generator(repo: Path):
    spec = importlib.util.spec_from_file_location(
        "template_generator", repo / "scripts" / "generate-template.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load template generator")
    gen = importlib.util.module_from_spec(spec)
    # @dataclass resolves the module through sys.modules while it executes.
    sys.modules[spec.name] = gen
    spec.loader.exec_module(gen)
    return gen


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: check_conflicting_cfs.py "
            "<path-to-trash-guides> <path-to-config-repo>",
            file=sys.stderr,
        )
        return 2

    guides, repo = map(Path, argv)
    gen = load_generator(repo)
    results = [check_service(guides, repo, gen, svc) for svc in gen.SERVICES]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
