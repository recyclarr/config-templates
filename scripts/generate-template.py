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

        for profile in sorted(profiles.values(), key=lambda p: p.file_stem):
            group_name = get_profile_group_name(profile_groups, profile.trash_id)
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
            simple = [g for g in spec.optional_groups if not g.optional_cfs]
            expanded = [g for g in spec.optional_groups if g.optional_cfs]
            simple.sort(key=lambda g: g.name)
            expanded.sort(key=lambda g: g.name)

            lines.extend(
                comment_block(
                    [
                        "These groups are NOT synced by default. Uncomment to"
                        " enable. Use `select:` to choose specific CFs within"
                        " a group.",
                        "To uncomment, remove `# ` (hash + space) so that"
                        " indentation stays aligned. Most editors do this"
                        " automatically with toggle-comment (Ctrl+/).",
                        "https://recyclarr.dev/guide/cf-groups/",
                    ],
                    indent=6,
                )
            )
            lines.append("      add:")

            # Choice groups: uncommented, with select block
            for group in spec.choice_groups:
                lines.append(f"        - trash_id: {group.trash_id}  # {group.name}")
                lines.append("          select:")
                for cf in group.custom_formats:
                    if cf.default:
                        lines.append(f"            - {cf.trash_id}  # {cf.name}")
                    else:
                        lines.append(f"            # - {cf.trash_id}  # {cf.name}")

            # Optional groups: commented out
            for group in simple:
                lines.append(f"        # - trash_id: {group.trash_id}  # {group.name}")
            for group in expanded:
                lines.append(f"        # - trash_id: {group.trash_id}  # {group.name}")
                lines.append("        #   select:")
                for cf in group.optional_cfs:
                    lines.append(f"        #     - {cf.trash_id}  # {cf.name}")

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
