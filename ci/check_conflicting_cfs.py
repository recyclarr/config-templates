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
from pathlib import Path

GUIDES = Path(sys.argv[1])
REPO = Path(sys.argv[2])

_spec = importlib.util.spec_from_file_location(
    "gen", REPO / "scripts" / "generate-template.py"
)
gen = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves cls.__module__ via sys.modules.
sys.modules["gen"] = gen
_spec.loader.exec_module(gen)

GROUP_RE = re.compile(r"^(?P<pre>[^-]*)- trash_id:\s*(?P<id>[a-f0-9]{32})")
NODE_RE = re.compile(r"^(?P<pre>[^a-z]*)(?P<node>select|exclude):\s*$")
BARE_RE = re.compile(r"^(?P<pre>[^-]*)-\s*(?P<id>[a-f0-9]{32})")
PROFILE_RE = re.compile(r"^\s*- trash_id:\s*([a-f0-9]{32})\s*#")

exit_code = 0


def error(file: Path, line: int, message: str) -> None:
    global exit_code
    rel = file.relative_to(REPO).as_posix()
    print(f"::error file={rel},line={line},title=Conflicting Custom Formats::{message}")
    exit_code = 1


def depth(pre: str) -> int:
    """How many comment markers precede the list dash."""
    return pre.count("#")


def check_service(service: str) -> None:
    json_paths = gen.load_guides(GUIDES)
    conflict_sets = gen.load_conflicts(GUIDES, json_paths, service)
    if not conflict_sets:
        print(
            "::warning title=Conflicting Custom Formats::"
            f"No conflict sets found for {service}; nothing to check"
        )
        return

    cf_groups = gen.load_cf_groups(GUIDES, json_paths, service)
    names = {
        cf.trash_id: cf.name for g in cf_groups.values() for cf in g.custom_formats
    }

    for path in sorted((REPO / service / "templates").rglob("*.yml")):
        print(f"Processing {path}")
        lines = path.read_text(encoding="utf-8").splitlines()

        profile_id = None
        section = None
        group_id = None
        group_depth = 0
        node = None
        adds: dict[str, dict] = {}
        skips: set[str] = set()
        # group id -> [(line number, cf id)] for select members at block depth
        base_level: dict[str, list[tuple[int, str]]] = {}

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
                    adds[group_id] = {
                        "active": group_depth == 0,
                        "select": set(),
                        "exclude": set(),
                    }
                    base_level[group_id] = []
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
                        adds[group_id][node].add(m.group("id"))
                    if node == "select" and d == group_depth and group_depth > 0:
                        base_level[group_id].append((i, m.group("id")))
                continue

            if section == "skip":
                m = BARE_RE.match(raw)
                if m and depth(m.group("pre")) == 0:
                    skips.add(m.group("id"))
                continue

        if profile_id is None:
            error(path, 1, "No quality profile trash_id found")
            continue

        # Pass A: what this template actually syncs
        effective: set[str] = set()
        for group in cf_groups.values():
            if profile_id not in group.target_profiles.values():
                continue
            if group.trash_id in skips:
                continue
            entry = adds.get(group.trash_id)
            enabled = group.is_default or (entry is not None and entry["active"])
            if not enabled:
                continue
            base = {c.trash_id for c in group.custom_formats if c.required or c.default}
            if entry is not None:
                base = (base - entry["exclude"]) | entry["select"]
            effective |= base

        for cs in conflict_sets:
            clash = sorted(effective & cs)
            if len(clash) > 1:
                labels = ", ".join(f"{names.get(t, t)} ({t})" for t in clash)
                error(
                    path,
                    1,
                    f"Effective CF set enables conflicting formats: {labels}",
                )

        # Pass B: what one uncomment of a commented block would activate
        for gid, entries in base_level.items():
            for cs in conflict_sets:
                clash = [(ln, t) for ln, t in entries if t in cs]
                if len(clash) > 1:
                    labels = ", ".join(f"{names.get(t, t)} ({t})" for _, t in clash)
                    gname = cf_groups[gid].name if gid in cf_groups else gid
                    error(
                        path,
                        clash[1][0],
                        f"Group '{gname}': uncommenting this block would enable "
                        f"conflicting formats: {labels}",
                    )


for svc in gen.SERVICES:
    check_service(svc)

sys.exit(exit_code)
