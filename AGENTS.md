# AGENTS.md

Guidance for AI agents working with this repository.

## Overview

- Configuration templates for [Recyclarr](https://github.com/recyclarr/recyclarr), a CLI tool that
  syncs TRaSH Guides recommendations to Radarr/Sonarr
- Templates provide ready-to-use configurations users can customize
- Issue tracking via Linear (internal only)

## Branching

`master` contains templates for the current Recyclarr release. A `v{major}` branch exists only while
an incompatible upcoming major version is in development.

- **Before any work**: Verify checked-out branch matches intent
- Target `master` unless the required version branch exists
- Merge a released version branch into `master`, then delete it

See `CONTRIBUTING.md` for full branching policy.

## TRaSH Guides Integration

TRaSH Guides is the authoritative source. When discrepancies exist between templates and guides,
defer to guides.

### Guide Resources

Located in TRaSH-Guides repo under `docs/json/{radarr,sonarr}/`:

- `quality-profiles/*.json` - Quality profile definitions with `formatItems`
- `cf-groups/*.json` - CF group definitions with profile targeting
- `cf/*.json` - Individual custom format definitions

### Guide-Backed Resources

Templates can reference guide resources by `trash_id`:

- `quality_profiles.trash_id` - Syncs profile definition AND `formatItems` (CFs with scores)
- `custom_format_groups.trash_id` - Syncs CF groups; users customize via `exclude` node

### CF Group Structure

CF groups define:

- `custom_formats[]` - CFs in the group with `required`/`default` flags
- `quality_profiles.include` - Map of profile names to trash_ids this group applies to

To find groups for a profile: search `cf-groups/` for the profile's trash_id.

## Structure

Templates are self-contained and reference guide resources directly. `templates.json` maps
user-facing IDs to template files.

```txt
radarr/
  templates/
    sqp/               # Storage-optimized profiles

sonarr/
  templates/
```

### Naming Conventions

Templates: `{resolution}-{source}-{language-variant}.yml`

- Resolution: `hd` (1080p), `uhd` (2160p)
- Source: `bluray-web`, `remux-web`, `web`
- Language variants: `french-vostfr`, `french-multi-vf`, `french-multi-vo`, `german`
- SQP templates: `sqp-{1-5}` for size-quality balanced profiles

## Constraints

- Templates MUST reference the schema for their Recyclarr major version
- Template headers MUST include documentation links

## Commits & PRs

Commits with `feat:` or `fix:` trigger Discord notifications via `notify.yml`. Choose types
carefully.

### Type Selection

- `feat:` - New files in `*/templates/**` or new entries in `templates.json`
- `fix:` - Modifications to existing template files
- `docs:` - `*.md`, `LICENSE`
- `ci:` - `.github/workflows/**`
- `chore:` - Everything else (default)

### Scopes

- `radarr/**` - `(radarr)`
- `sonarr/**` - `(sonarr)`
- `templates.json` - `(config)`

### Breaking Changes (!)

- Template ID renames/removals
- Schema changes requiring user config updates

### CI Checks

- `yaml-lint.yml` - YAML syntax (all pushes/PRs)
- `check-paths.yml` - Paths in `templates.json` exist
- `check-trash-ids.yml` - Trash IDs and CF conflicts valid against TRaSH-Guides (PRs only)

## Skills

Load skills before specialized tasks:

- `template-conversion` - Converting templates to use guide-backed profiles and CF groups
