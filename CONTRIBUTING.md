# Contributing

Guide for contributing to Recyclarr config templates.

## Overview

This repository contains configuration templates for
[Recyclarr](https://github.com/recyclarr/recyclarr), providing ready-to-use configurations that sync
TRaSH Guides recommendations to Radarr/Sonarr.

## Template System

Templates are self-contained YAML files that reference quality profiles and custom format groups
from TRaSH Guides.

- `templates.json` maps user-facing template IDs to template files.
- `radarr/templates/` contains Radarr templates.
- `sonarr/templates/` contains Sonarr templates.

```txt
radarr/
  templates/
    sqp/               # Storage-optimized profiles

sonarr/
  templates/
```

## File Requirements

### Naming Convention

Templates: `{resolution}-{source}-{language-variant}.yml`

- Resolution: `hd` (1080p), `uhd` (2160p)
- Source: `bluray-web`, `remux-web`, `web`
- Language variants: `french-vostfr`, `french-multi-vf`, `french-multi-vo`, `german`
- SQP templates: `sqp-{1-5}` for size-quality balanced profiles

### Header Format

Each template must start with the schema for its Recyclarr major version and link to the matching
TRaSH Guides documentation:

```yaml
# yaml-language-server: $schema=https://schemas.recyclarr.dev/v8/config-schema.json
################################################################################
## TRaSH Guides: {Template Name}
##
## https://trash-guides.info/{Guide Path}
################################################################################
```

## Local Testing

Install [Python 3](https://www.python.org/downloads/) and
[yamllint](https://yamllint.readthedocs.io/en/stable/quickstart.html#installing-yamllint), then run:

```bash
yamllint .
```

On Windows, set `PYTHONUTF8=1` to avoid false line-length errors on files with unicode characters.
See [yamllint#530](https://github.com/adrienverge/yamllint/issues/530#issuecomment-1402452147).

## CI Checks

PRs are validated by:

- `yaml-lint.yml` - YAML syntax
- `check-paths.yml` - Paths in `templates.json` exist
- `check-trash-ids.yml` - Trash IDs and CF conflicts are valid against TRaSH-Guides

## Commit Conventions

Commits with `feat:` or `fix:` trigger Discord notifications. Choose types carefully.

### Type Selection

- `feat:` - New templates or registry entries
- `fix:` - Modifications to existing templates
- `docs:` - Markdown files, LICENSE
- `ci:` - Workflow files
- `chore:` - Everything else

### Scopes

- `(radarr)` - Changes under `radarr/`
- `(sonarr)` - Changes under `sonarr/`
- `(config)` - Changes to `templates.json`

### Breaking Changes

Add `!` suffix for breaking changes:

- Template ID renames or removals
- Schema changes requiring user config updates

Example: `feat(radarr)!: rename hd-bluray-web template`

## Branching Strategy

`master` contains templates for the current Recyclarr release. Version branches isolate changes
that require an unreleased Recyclarr major version.

### Branch Structure

- `master`: Templates for the current release
- `v{major}`: Temporary development branch for an incompatible upcoming major release

### How Recyclarr Selects Branches

Recyclarr automatically selects the appropriate branch:

1. Tries `v{major}` matching its version
2. Falls back to `master`, then `main`

Users can override with explicit `reference` in `settings.yml`.

### Which Branch to Target

- Target `master` unless a version branch exists for the change's required Recyclarr major.
- Target that version branch for changes incompatible with the current release.

### Support Policy

Template maintainers are not expected to backport updates or maintain multiple versions. Users on
older Recyclarr versions experiencing template drift should upgrade.

### Version Branch Lifecycle

Create `v{new}` from `master` when development first requires incompatible templates. After that
Recyclarr major version is released, merge the version branch into `master` and delete it.
