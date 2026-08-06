#!/usr/bin/env python3
"""
Generate Recyclarr config templates from TRaSH Guides profile data.

Processes all services (radarr, sonarr) in a single pass. Template IDs that
collide across services are automatically prefixed with the service name.

Usage:
    ./generate-template.py --list                 # list all available profiles
    ./generate-template.py -n                     # dry-run all templates
    ./generate-template.py                        # generate all templates
    ./generate-template.py --overwrite            # regenerate all templates
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

COMMENT_BLOCK_WIDTH = 80
SERVICES = ("radarr", "sonarr")
EXCLUDED_PROFILE_GROUPS = {"TEST"}


@dataclass
class CustomFormat:
    trash_id: str
    name: str
    required: bool = False
    default: bool = False

    @property
    def is_optional(self) -> bool:
        return not self.required and not self.default


@dataclass
class CFGroup:
    trash_id: str
    name: str
    is_default: bool = False
    target_profiles: dict[str, str] = field(default_factory=dict)
    custom_formats: list[CustomFormat] = field(default_factory=list)

    @property
    def optional_cfs(self) -> list[CustomFormat]:
        return [cf for cf in self.custom_formats if cf.is_optional]

    @property
    def default_cfs(self) -> list[CustomFormat]:
        return [cf for cf in self.custom_formats if cf.default]

    @property
    def has_body(self) -> bool:
        """True when the group has any CF the user can toggle."""
        return bool(self.default_cfs or self.optional_cfs)

    @property
    def has_cf_defaults(self) -> bool:
        return any(cf.default for cf in self.custom_formats)


@dataclass
class QualityProfile:
    trash_id: str
    name: str
    file_stem: str = ""
    trash_url: str = ""

    def is_sqp1(self) -> bool:
        return "SQP-1" in self.name


@dataclass
class TemplateSpec:
    service: str
    profile: QualityProfile
    base_id: str
    template_id: str
    output_path: str
    quality_def: str
    group_name: str | None
    optional_groups: list[CFGroup]
    default_groups: list[CFGroup]
    choice_groups: list[CFGroup]
    conflict_sets: list[frozenset[str]] = field(default_factory=list)


def load_guides(guides_path: Path) -> dict:
    metadata_file = guides_path / "metadata.json"
    if not metadata_file.exists():
        raise FileNotFoundError(f"metadata.json not found in {guides_path}")

    with open(metadata_file) as f:
        return json.load(f).get("json_paths", {})


def load_profiles(
    guides_path: Path, json_paths: dict, service: str
) -> dict[str, QualityProfile]:
    profiles = {}
    for rel_path in json_paths.get(service, {}).get("quality_profiles", []):
        resource_dir = guides_path / rel_path
        if not resource_dir.exists():
            continue
        for json_file in resource_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
            profiles[json_file.stem] = QualityProfile(
                trash_id=data.get("trash_id", ""),
                name=data.get("name", ""),
                file_stem=json_file.stem,
                trash_url=data.get("trash_url", ""),
            )
    return profiles


def load_cf_groups(
    guides_path: Path, json_paths: dict, service: str
) -> dict[str, CFGroup]:
    groups = {}
    for rel_path in json_paths.get(service, {}).get("custom_format_groups", []):
        resource_dir = guides_path / rel_path
        if not resource_dir.exists():
            continue
        for json_file in resource_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
            default_val = data.get("default", "")
            cfs = [
                CustomFormat(
                    trash_id=cf.get("trash_id", ""),
                    name=cf.get("name", ""),
                    required=cf.get("required", False) is True,
                    default=cf.get("default", False) is True,
                )
                for cf in data.get("custom_formats", [])
            ]
            group = CFGroup(
                trash_id=data.get("trash_id", ""),
                name=data.get("name", ""),
                is_default=isinstance(default_val, str)
                and default_val.lower() == "true",
                target_profiles={
                    name: tid
                    for name, tid in data.get("quality_profiles", {})
                    .get("include", {})
                    .items()
                },
                custom_formats=cfs,
            )
            groups[group.trash_id] = group
    return groups


def load_profile_groups(
    guides_path: Path, json_paths: dict, service: str
) -> list[dict]:
    for rel_path in json_paths.get(service, {}).get("quality_profile_groups", []):
        groups_file = guides_path / rel_path / "groups.json"
        if groups_file.exists():
            with open(groups_file) as f:
                return json.load(f)
    return []


def load_conflicts(
    guides_path: Path, json_paths: dict, service: str
) -> list[frozenset[str]]:
    """Load mutually exclusive CF sets from the guides.

    Unlike the other resources, `conflicts` in metadata.json is a list of file
    paths, not directories. A missing entry or file yields no sets, which makes
    every conflict-driven behaviour inert rather than an error.
    """
    sets: list[frozenset[str]] = []
    for rel_path in json_paths.get(service, {}).get("conflicts", []):
        conflicts_file = guides_path / rel_path
        if not conflicts_file.exists():
            continue
        with open(conflicts_file) as f:
            data = json.load(f)
        for entry in data.get("custom_formats", []):
            ids = frozenset(entry)
            if len(ids) >= 2:
                sets.append(ids)
    return sets


def get_profile_group_name(
    profile_groups: list[dict], profile_trash_id: str
) -> str | None:
    for group in profile_groups:
        if profile_trash_id in group.get("profiles", {}).values():
            return group.get("name")
    return None


def get_groups_for_profile(
    cf_groups: dict[str, CFGroup], profile_trash_id: str, *, default: bool
) -> list[CFGroup]:
    result = [
        g
        for g in cf_groups.values()
        if profile_trash_id in g.target_profiles.values() and g.is_default == default
    ]
    result.sort(key=lambda g: g.name)
    return result


def derive_base_id(profile: QualityProfile) -> str:
    return profile.file_stem


def derive_output_path(service: str, base_id: str, group_name: str | None) -> str:
    if group_name and group_name.lower() == "sqp":
        return f"{service}/templates/sqp/{base_id}.yml"
    return f"{service}/templates/{base_id}.yml"


def infer_quality_definition(
    service: str, profile: QualityProfile, group_name: str | None
) -> str:
    if service == "sonarr":
        if group_name and group_name.lower() == "anime":
            return "anime"
        return "series"

    if group_name:
        group_lower = group_name.lower()
        if group_lower == "anime":
            return "anime"
        if group_lower == "sqp":
            if profile.is_sqp1():
                return "sqp-streaming"
            return "sqp-uhd"

    return "movie"


def build_template_specs(guides_path: Path) -> list[TemplateSpec]:
    json_paths = load_guides(guides_path)
    specs: list[TemplateSpec] = []

    for service in SERVICES:
        profiles = load_profiles(guides_path, json_paths, service)
        cf_groups = load_cf_groups(guides_path, json_paths, service)
        profile_groups = load_profile_groups(guides_path, json_paths, service)
        conflict_sets = load_conflicts(guides_path, json_paths, service)

        for profile in sorted(profiles.values(), key=lambda p: p.file_stem):
            group_name = get_profile_group_name(profile_groups, profile.trash_id)
            if group_name in EXCLUDED_PROFILE_GROUPS:
                continue
            base_id = derive_base_id(profile)
            optional = get_groups_for_profile(
                cf_groups, profile.trash_id, default=False
            )
            all_default = get_groups_for_profile(
                cf_groups, profile.trash_id, default=True
            )
            choice = [g for g in all_default if g.has_cf_defaults]
            default = [g for g in all_default if not g.has_cf_defaults]
            quality_def = infer_quality_definition(service, profile, group_name)

            specs.append(
                TemplateSpec(
                    service=service,
                    profile=profile,
                    base_id=base_id,
                    template_id=base_id,  # may be overwritten below
                    output_path="",  # set after disambiguation
                    quality_def=quality_def,
                    group_name=group_name,
                    optional_groups=optional,
                    default_groups=default,
                    choice_groups=choice,
                    conflict_sets=conflict_sets,
                )
            )

    # Disambiguate colliding IDs across services
    id_counts = Counter(s.base_id for s in specs)
    for spec in specs:
        if id_counts[spec.base_id] > 1:
            spec.template_id = f"{spec.service}-{spec.base_id}"
        spec.output_path = derive_output_path(
            spec.service, spec.base_id, spec.group_name
        )

    return specs


def comment_block(paragraphs: list[str], indent: int = 0) -> list[str]:
    """Build a bordered comment block with word-wrapped paragraphs.

    Each string in `paragraphs` becomes a separate paragraph, separated by
    blank comment lines. Text is wrapped to fit within COMMENT_BLOCK_WIDTH
    including the `## ` prefix.

    Returns lines with `indent` spaces prepended, ready to append to output.
    """
    prefix = "## "
    text_width = COMMENT_BLOCK_WIDTH - len(prefix)
    border = "#" * COMMENT_BLOCK_WIDTH
    pad = " " * indent

    lines = [f"{pad}{border}"]
    for i, para in enumerate(paragraphs):
        if i > 0:
            lines.append(f"{pad}##")
        for wrapped in textwrap.wrap(para, width=text_width):
            lines.append(f"{pad}{prefix}{wrapped}")
    lines.append(f"{pad}{border}")
    return lines


def group_has_conflict(group: CFGroup, conflict_sets: list[frozenset[str]]) -> bool:
    """True when the group holds two or more members of one conflict set."""
    ids = {cf.trash_id for cf in group.custom_formats}
    return any(len(ids & cs) >= 2 for cs in conflict_sets)


def masked_select_ids(group: CFGroup, conflict_sets: list[frozenset[str]]) -> set[str]:
    """Optional CFs needing an extra comment level inside a commented block.

    For each conflict set with two or more optional members in this group, the
    first in guide order stays at the block's level and the rest are masked, so
    uncommenting the block activates exactly one.
    """
    order = [cf.trash_id for cf in group.optional_cfs]
    masked: set[str] = set()
    for cs in conflict_sets:
        present = [t for t in order if t in cs]
        if len(present) >= 2:
            masked.update(present[1:])
    return masked


def render_group_entry(
    group: CFGroup,
    conflict_sets: list[frozenset[str]],
    *,
    commented: bool,
) -> list[str]:
    """Render one entry under `add:`.

    Uncommented (a group Recyclarr syncs by default):

        - trash_id: <id>  # <name>
          exclude:
            # - <id>  # <name>      each `default` CF; uncomment to turn OFF
          select:
            # - <id>  # <name>      each optional CF; uncomment to turn ON

    Commented (an opt-in group) is the same text with `# ` after the indent.
    Inside a commented block, `exclude:` members carry an extra `# ` so that
    enabling the group does not also strip its defaults, while `select:`
    members sit at the block's own level so enabling the group includes them,
    which is how opt-in groups already behave.

    Required CFs are never listed: they are always included and cannot be
    excluded.
    """
    indent = " " * 8
    block = "# " if commented else ""
    lines = [f"{indent}{block}- trash_id: {group.trash_id}  # {group.name}"]

    masked = masked_select_ids(group, conflict_sets) if commented else set()
    if group_has_conflict(group, conflict_sets):
        lines.append(
            f"{indent}{block}  "
            "# Mutually exclusive: enable only one of the following."
        )

    for node, cfs in (("exclude", group.default_cfs), ("select", group.optional_cfs)):
        if not cfs:
            continue
        lines.append(f"{indent}{block}  {node}:")
        for cf in cfs:
            if not commented:
                mark = "# "
            elif node == "exclude":
                mark = "# "
            else:
                mark = "# " if cf.trash_id in masked else ""
            lines.append(f"{indent}{block}    {mark}- {cf.trash_id}  # {cf.name}")

    return lines


def generate_yaml(spec: TemplateSpec) -> str:
    lines = []

    # Schema directive (must be line 1 for Red Hat YAML extension)
    lines.append(
        "# yaml-language-server:"
        " $schema=https://schemas.recyclarr.dev/v8/config-schema.json"
    )

    # Header
    header_paras = [f"TRaSH Guides: {spec.profile.name}"]
    if spec.profile.trash_url:
        header_paras.append(spec.profile.trash_url)
    lines.extend(comment_block(header_paras))
    lines.append("")

    # Instance block
    service_label = "Radarr" if spec.service == "radarr" else "Sonarr"
    lines.append(f"{spec.service}:")
    lines.append(f"  {spec.template_id}:")
    lines.append(f"    base_url: Put your {service_label} URL here")
    lines.append("    api_key: Put your API key here")
    lines.append("")

    # Quality definition
    lines.append("    quality_definition:")
    lines.append(f"      type: {spec.quality_def}")
    lines.append("")

    # Quality profile
    lines.append("    quality_profiles:")
    lines.append(f"      - trash_id: {spec.profile.trash_id}  # {spec.profile.name}")
    lines.append("        reset_unmatched_scores:")
    lines.append("          enabled: true")

    # CF groups
    has_optional = bool(spec.optional_groups)
    has_default = bool(spec.default_groups)
    has_choice = bool(spec.choice_groups)
    if has_optional or has_default or has_choice:
        lines.append("")
        lines.append("    custom_format_groups:")

        if has_optional or has_choice:
            simple = [g for g in spec.optional_groups if not g.has_body]
            expanded = [g for g in spec.optional_groups if g.has_body]
            simple.sort(key=lambda g: g.name)
            expanded.sort(key=lambda g: g.name)

            lines.extend(
                comment_block(
                    [
                        "Uncommented groups are synced by default. They are listed"
                        " here so you can adjust which CFs they include. Commented"
                        " groups are NOT synced; uncomment one to enable it.",
                        "Within a group, uncomment a line under `select:` to turn"
                        " an optional CF on, or under `exclude:` to turn a default"
                        " CF off. Required CFs are always included and are not"
                        " listed.",
                        "To uncomment, remove `# ` (hash + space) so that"
                        " indentation stays aligned. Most editors do this"
                        " automatically with toggle-comment (Ctrl+/).",
                        "https://recyclarr.dev/guide/cf-groups/",
                    ],
                    indent=6,
                )
            )
            lines.append("      add:")

            for group in spec.choice_groups:
                lines.extend(
                    render_group_entry(group, spec.conflict_sets, commented=False)
                )
            for group in simple:
                lines.extend(
                    render_group_entry(group, spec.conflict_sets, commented=True)
                )
            for group in expanded:
                lines.extend(
                    render_group_entry(group, spec.conflict_sets, commented=True)
                )

        if has_default:
            lines.append("")
            lines.extend(
                comment_block(
                    [
                        "These groups ARE synced by default. Uncomment to disable.",
                        "https://recyclarr.dev/guide/cf-groups/",
                    ],
                    indent=6,
                )
            )
            lines.append("      skip:")
            for group in spec.default_groups:
                lines.append(f"        # - {group.trash_id}  # {group.name}")

    lines.append("")
    return "\n".join(lines)


def write_templates_json(templates_json_path: Path, specs: list[TemplateSpec]):
    data: dict[str, list[dict]] = {}
    for spec in specs:
        data.setdefault(spec.service, []).append(
            {
                "template": spec.output_path,
                "id": spec.template_id,
            }
        )

    for service in data:
        data[service].sort(key=lambda e: e["id"])

    with open(templates_json_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def list_profiles(guides_path: Path):
    specs = build_template_specs(guides_path)
    current_service = None
    for spec in specs:
        if spec.service != current_service:
            if current_service is not None:
                print()
            current_service = spec.service
            print(f"{spec.service}:")
        group_label = f"  [{spec.group_name}]" if spec.group_name else ""
        prefix = " *" if spec.template_id != spec.base_id else "  "
        print(f"{prefix}{spec.template_id}{group_label}")

    print("\n* = prefixed to avoid cross-service ID collision")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Recyclarr config templates from TRaSH Guides",
    )
    parser.add_argument(
        "--guides",
        type=Path,
        default=Path("../guides"),
        help="Path to TRaSH-Guides repo (default: ../guides)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Path to config-templates repo root (default: .)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Output YAML to stdout instead of writing files",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing template files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles and their template IDs",
    )

    args = parser.parse_args()

    if not args.guides.exists():
        print(f"Error: Guides repo not found: {args.guides}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        list_profiles(args.guides)
        return

    specs = build_template_specs(args.guides)

    if args.dry_run:
        for spec in specs:
            print(f"# Template ID: {spec.template_id}")
            print(f"# Output path: {spec.output_path}")
            print(f"# Quality definition: {spec.quality_def}")
            print(f"# Profile group: {spec.group_name or 'Unknown'}")
            print()
            print(generate_yaml(spec))
            print("---")
        return

    templates_json = args.repo / "templates.json"
    generated = 0
    skipped = 0

    for spec in specs:
        output_file = args.repo / spec.output_path
        if output_file.exists() and not args.overwrite:
            print(f"Skipped (exists): {output_file}")
            skipped += 1
            continue

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(generate_yaml(spec))
        print(f"Wrote: {output_file}")
        generated += 1

    write_templates_json(templates_json, specs)
    print(f"\nGenerated {generated} templates, skipped {skipped}")


if __name__ == "__main__":
    main()
