#!/usr/bin/env python3
"""
Generate Recyclarr config templates from TRaSH Guides profile data.

Usage:
    ./generate-template.py radarr --list                 # list available profiles
    ./generate-template.py radarr uhd-bluray-web -n      # dry-run single profile
    ./generate-template.py radarr uhd-bluray-web         # write single template
    ./generate-template.py radarr --all                  # generate all templates
    ./generate-template.py radarr --all --overwrite      # regenerate all templates
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CFGroup:
    """A CF group from TRaSH Guides."""

    trash_id: str
    name: str
    is_default: bool = False
    target_profiles: dict[str, str] = field(default_factory=dict)  # name -> trash_id


@dataclass
class QualityProfile:
    """A quality profile from TRaSH Guides."""

    trash_id: str
    name: str
    file_stem: str = ""  # JSON filename without extension
    trash_url: str = ""
    trash_description: str = ""
    items: list[dict] = field(default_factory=list)

    def allows_2160p(self) -> bool:
        """Check if profile allows any 2160p quality."""
        for item in self.items:
            if item.get("allowed", False):
                name = item.get("name", "")
                if "2160p" in name:
                    return True
                # Check nested items
                for sub in item.get("items", []):
                    if isinstance(sub, str) and "2160p" in sub:
                        return True
        return False


class GuideResources:
    """Loads and provides access to TRaSH Guides resources."""

    def __init__(self, guides_path: Path):
        self.guides_path = guides_path
        self._paths: dict[str, dict[str, list[str]]] = {}
        self._profiles: dict[
            str, dict[str, QualityProfile]
        ] = {}  # service -> {id: profile}
        self._cf_groups: dict[str, dict[str, CFGroup]] = {}  # service -> {id: group}
        self._profile_groups: dict[str, list[dict]] = {}  # service -> groups list
        self._load_metadata()

    def _load_metadata(self):
        """Load resource paths from metadata.json."""
        metadata_file = self.guides_path / "metadata.json"
        if not metadata_file.exists():
            raise FileNotFoundError(f"metadata.json not found in {self.guides_path}")

        with open(metadata_file) as f:
            data = json.load(f)

        self._paths = data.get("json_paths", {})

    def _iter_json_files(self, service: str, resource_key: str):
        """Iterate over JSON files for a resource type."""
        for rel_path in self._paths.get(service, {}).get(resource_key, []):
            resource_dir = self.guides_path / rel_path
            if resource_dir.exists():
                yield from resource_dir.glob("*.json")

    def _ensure_profiles_loaded(self, service: str):
        """Load profiles for service if not already loaded."""
        if service in self._profiles:
            return

        self._profiles[service] = {}
        for json_file in self._iter_json_files(service, "quality_profiles"):
            with open(json_file) as f:
                data = json.load(f)

            profile = QualityProfile(
                trash_id=data.get("trash_id", ""),
                name=data.get("name", ""),
                file_stem=json_file.stem,
                trash_url=data.get("trash_url", ""),
                trash_description=data.get("trash_description", ""),
                items=data.get("items", []),
            )
            self._profiles[service][profile.file_stem] = profile

    def _ensure_cf_groups_loaded(self, service: str):
        """Load CF groups for service if not already loaded."""
        if service in self._cf_groups:
            return

        self._cf_groups[service] = {}
        for json_file in self._iter_json_files(service, "custom_format_groups"):
            with open(json_file) as f:
                data = json.load(f)

            default_val = data.get("default", "")
            is_default = isinstance(default_val, str) and default_val.lower() == "true"

            group = CFGroup(
                trash_id=data.get("trash_id", ""),
                name=data.get("name", ""),
                is_default=is_default,
                target_profiles={
                    name: tid
                    for name, tid in data.get("quality_profiles", {})
                    .get("include", {})
                    .items()
                },
            )
            self._cf_groups[service][group.trash_id] = group

    def _ensure_profile_groups_loaded(self, service: str):
        """Load profile groups for service if not already loaded."""
        if service in self._profile_groups:
            return

        self._profile_groups[service] = []
        for rel_path in self._paths.get(service, {}).get("quality_profile_groups", []):
            groups_file = self.guides_path / rel_path / "groups.json"
            if groups_file.exists():
                with open(groups_file) as f:
                    self._profile_groups[service] = json.load(f)

    def get_profile(self, service: str, identifier: str) -> QualityProfile | None:
        """Get profile by file_stem (primary), trash_id, or name."""
        self._ensure_profiles_loaded(service)

        profiles = self._profiles.get(service, {})

        # Try direct file_stem lookup (primary)
        if identifier in profiles:
            return profiles[identifier]

        # Try trash_id or name lookup (fallback)
        for profile in profiles.values():
            if profile.trash_id == identifier or profile.name == identifier:
                return profile

        return None

    def get_all_profiles(self, service: str) -> list[QualityProfile]:
        """Get all profiles for a service."""
        self._ensure_profiles_loaded(service)
        return list(self._profiles.get(service, {}).values())

    def get_cf_groups_for_profile(
        self, service: str, profile_trash_id: str
    ) -> tuple[list[CFGroup], list[CFGroup]]:
        """
        Get CF groups targeting a profile.

        Returns (default_groups, optional_groups).
        """
        self._ensure_cf_groups_loaded(service)

        default_groups = []
        optional_groups = []

        for group in self._cf_groups.get(service, {}).values():
            if profile_trash_id in group.target_profiles.values():
                if group.is_default:
                    default_groups.append(group)
                else:
                    optional_groups.append(group)

        # Sort by name for consistent output
        default_groups.sort(key=lambda g: g.name)
        optional_groups.sort(key=lambda g: g.name)

        return default_groups, optional_groups

    def get_profile_group_name(self, service: str, profile_trash_id: str) -> str | None:
        """Get the group name (Standard, Anime, SQP, etc.) for a profile."""
        self._ensure_profile_groups_loaded(service)

        for group in self._profile_groups.get(service, []):
            profiles = group.get("profiles", {})
            if profile_trash_id in profiles.values():
                return group.get("name")

        return None


def derive_template_id(profile: QualityProfile, group_name: str | None) -> str:
    """Derive a kebab-case template ID from profile name."""
    name = profile.name

    # Remove bracketed prefixes like [French MULTi.VO], [SQP]
    name = re.sub(r"\[.*?\]\s*", "", name)

    # Convert to kebab-case
    # Replace spaces, underscores, dots with hyphens
    name = re.sub(r"[\s_\.]+", "-", name)

    # Remove parentheses and their content or convert to suffix
    # e.g., "SQP-1 (2160p)" -> "sqp-1-2160p"
    name = re.sub(r"\(([^)]+)\)", r"-\1", name)

    # Remove any remaining special characters
    name = re.sub(r"[^a-zA-Z0-9-]", "", name)

    # Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)

    # Strip leading/trailing hyphens and lowercase
    name = name.strip("-").lower()

    # Add group prefix for non-standard groups
    if group_name and group_name.lower() not in ["standard"]:
        prefix = group_name.lower()
        if not name.startswith(prefix):
            name = f"{prefix}-{name}"

    return name


def derive_output_path(service: str, template_id: str, group_name: str | None) -> str:
    """Derive the output file path for a template."""
    # SQP templates go in a subdirectory
    if group_name and group_name.lower() == "sqp":
        return f"{service}/templates/sqp/{template_id}.yml"

    return f"{service}/templates/{template_id}.yml"


def infer_quality_definition(
    service: str, profile: QualityProfile, group_name: str | None
) -> str:
    """Infer the quality definition type for a profile."""
    if service == "sonarr":
        if group_name and group_name.lower() == "anime":
            return "anime"
        return "series"

    # radarr
    if group_name:
        group_lower = group_name.lower()
        if group_lower == "anime":
            return "anime"
        if group_lower == "sqp":
            # SQP profiles: sqp-uhd if allows 2160p, sqp-streaming otherwise
            if profile.allows_2160p():
                return "sqp-uhd"
            return "sqp-streaming"

    return "movie"


def generate_yaml(
    service: str,
    profile: QualityProfile,
    quality_def: str,
    optional_groups: list[CFGroup],
    template_id: str,
) -> str:
    """Generate the YAML template content."""
    lines = []

    # Header
    lines.append(f"# TRaSH Guides: {profile.name}")
    if profile.trash_url:
        lines.append(f"# {profile.trash_url}")
    lines.append("")

    # Instance block
    lines.append(f"{service}:")
    lines.append(f"  {template_id}:")
    if service == "radarr":
        lines.append("    base_url: Put your Radarr URL here")
    else:
        lines.append("    base_url: Put your Sonarr URL here")
    lines.append("    api_key: Put your API key here")
    lines.append("")

    # Quality definition
    lines.append("    quality_definition:")
    lines.append(f"      type: {quality_def}")
    lines.append("")

    # Quality profile
    lines.append("    quality_profiles:")
    lines.append(f"      - trash_id: {profile.trash_id}  # {profile.name}")
    lines.append("        reset_unmatched_scores:")
    lines.append("          enabled: true")

    # Optional CF groups (commented)
    if optional_groups:
        lines.append("")
        lines.append("    custom_format_groups:")
        lines.append("      add:")
        for group in optional_groups:
            lines.append(f"        # - trash_id: {group.trash_id}  # {group.name}")

    lines.append("")
    return "\n".join(lines)


def update_templates_json(
    templates_json_path: Path, service: str, template_id: str, template_path: str
) -> bool:
    """
    Update templates.json with the new template entry.

    Returns True if entry was added/updated, False if already exists unchanged.
    """
    if templates_json_path.exists():
        with open(templates_json_path) as f:
            data = json.load(f)
    else:
        data = {}

    if service not in data:
        data[service] = []

    # Check if entry already exists
    for entry in data[service]:
        if entry.get("id") == template_id:
            if entry.get("template") == template_path:
                return False  # Already exists unchanged
            # Update existing entry
            entry["template"] = template_path
            with open(templates_json_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            return True

    # Add new entry
    new_entry = {"template": template_path, "id": template_id}
    data[service].append(new_entry)

    # Sort entries by id for consistency
    data[service].sort(key=lambda e: e.get("id", ""))

    with open(templates_json_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return True


def list_profiles(guides: GuideResources, service: str):
    """List all available profiles for a service."""
    profiles = guides.get_all_profiles(service)

    print(f"Available {service} profiles:\n")
    for profile in sorted(profiles, key=lambda p: p.file_stem):
        group_name = guides.get_profile_group_name(service, profile.trash_id)
        group_label = f"  [{group_name}]" if group_name else ""
        print(f"  {profile.file_stem}{group_label}")


def generate_for_profile(
    guides: GuideResources,
    service: str,
    profile: QualityProfile,
    repo_path: Path,
    dry_run: bool,
    overwrite: bool,
) -> bool:
    """
    Generate template for a single profile.

    Returns True if successful, False if skipped/failed.
    """
    group_name = guides.get_profile_group_name(service, profile.trash_id)
    template_id = derive_template_id(profile, group_name)
    output_path = derive_output_path(service, template_id, group_name)
    quality_def = infer_quality_definition(service, profile, group_name)

    default_groups, optional_groups = guides.get_cf_groups_for_profile(
        service, profile.trash_id
    )

    yaml_content = generate_yaml(
        service, profile, quality_def, optional_groups, template_id
    )

    if dry_run:
        print(f"# Template ID: {template_id}")
        print(f"# Output path: {output_path}")
        print(f"# Quality definition: {quality_def}")
        print(f"# Profile group: {group_name or 'Unknown'}")
        print(f"# Default CF groups (auto-sync): {len(default_groups)}")
        for g in default_groups:
            print(f"#   - {g.name}")
        print(f"# Optional CF groups: {len(optional_groups)}")
        print()
        print(yaml_content)
        return True

    templates_json = repo_path / "templates.json"
    output_file = repo_path / output_path

    if output_file.exists() and not overwrite:
        # Still update templates.json even if we skip writing the file
        update_templates_json(templates_json, service, template_id, output_path)
        print(f"Skipped (exists): {output_file}")
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        f.write(yaml_content)
    print(f"Wrote: {output_file}")

    update_templates_json(templates_json, service, template_id, output_path)

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate Recyclarr config templates from TRaSH Guides",
        usage="%(prog)s SERVICE [PROFILE] [options]",
    )
    parser.add_argument(
        "service",
        choices=["radarr", "sonarr"],
        help="Service type",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        help="Profile name (JSON filename without extension)",
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
        help="Output YAML to stdout instead of writing file",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing YAML file if present",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available profiles for the service",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate templates for all profiles in the service",
    )

    args = parser.parse_args()

    # Validate paths
    if not args.guides.exists():
        print(f"Error: Guides repo not found: {args.guides}", file=sys.stderr)
        sys.exit(1)

    # Load guide resources
    try:
        guides = GuideResources(args.guides)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    service = args.service

    # Handle --list mode
    if args.list:
        list_profiles(guides, service)
        return

    # Handle --all mode
    if args.all:
        profiles = guides.get_all_profiles(service)
        success = 0
        skipped = 0
        for profile in sorted(profiles, key=lambda p: p.file_stem):
            if generate_for_profile(
                guides, service, profile, args.repo, args.dry_run, args.overwrite
            ):
                success += 1
            else:
                skipped += 1
            if args.dry_run:
                print("---")  # Separator between profiles in dry-run
        if not args.dry_run:
            print(f"\nGenerated {success} templates, skipped {skipped}")
        return

    # Profile is required for non-list/non-all mode
    if not args.profile:
        parser.error("profile is required (or use --list/--all)")

    # Find profile
    profile = guides.get_profile(service, args.profile)

    if not profile:
        print(f"Error: Profile not found: {args.profile}", file=sys.stderr)
        print(f"Use --list to see available {service} profiles", file=sys.stderr)
        sys.exit(1)

    if not generate_for_profile(
        guides, service, profile, args.repo, args.dry_run, args.overwrite
    ):
        if not args.dry_run:
            print("Use --overwrite to replace existing files", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
