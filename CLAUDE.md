# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

This repository contains configuration templates for
[Recyclarr](https://github.com/recyclarr/recyclarr), a CLI tool that synchronizes TRaSH Guides
recommendations to Radarr/Sonarr instances. Templates provide ready-to-use configurations that users
can customize.

## Commands

Lint YAML files (requires Python 3 and yamllint installed):

```bash
yamllint .
```

On Windows, set `PYTHONUTF8=1` before running yamllint to handle unicode in French templates.

## Repository Architecture

### Template System

The repository uses a two-tier template system:

- `templates.json` - Maps template IDs to top-level template files (user-facing entry points)
- `includes.json` - Maps include IDs to reusable component files

Top-level templates (`radarr/templates/`, `sonarr/templates/`) reference includes via the `include:`
directive using IDs from `includes.json`.

### Directory Structure

```txt
radarr/
  templates/           # Top-level templates (referenced in templates.json)
  includes/
    custom-formats/    # Custom format definitions
    quality-definitions/
    quality-profiles/
    sqp/               # Special Quality Profiles (storage-optimized)

sonarr/
  templates/           # Top-level templates for Sonarr v4
  includes/
    custom-formats/
    quality-definitions/
    quality-profiles/
```

### Template Anatomy

Each top-level template has:

- A header comment block with update date and documentation links
- Instance definition section requiring `base_url` and `api_key`
- Include references to components from `includes.json`
- Optional custom format overrides with commented-out options

Includes are partial YAML files that define specific configurations (quality profiles, custom
formats, quality definitions).

### Naming Conventions

Templates follow pattern: `{resolution}-{source}-{language-variant}.yml`

- Resolution: `hd` (1080p), `uhd` (2160p)
- Source: `bluray-web`, `remux-web`, `web`
- Language variants: `french-vostfr`, `french-multi-vf`, `french-multi-vo`, `german`
- SQP templates: `sqp-{1-5}` for size-quality balanced profiles

## CI Workflows

- `yaml-lint.yml` - Validates YAML syntax on all pushes/PRs
- `check-paths.yml` - Validates that paths in `templates.json` exist
- `check-trash-ids.yml` - Validates trash IDs against TRaSH-Guides repository (PRs only)
- `check-dates.yml` - Validates `Updated:` dates in template headers (PRs only)

## Template Header Requirements

Templates must include an `Updated:` date in the header comment. When modifying a template, update
this date to the current date in `YYYY-MM-DD` format.

## Conventional Commit Rules

File path-based classification for commit messages:

**Direct path mapping:**

- `ci:` → `.github/workflows/**`
- `chore:` → `.yamllint`, `.gitignore`, `.vscode/**`, `renovate.json5`, `.renovate/**`
- `docs:` → `*.md`, `LICENSE`, `CONTRIBUTING.md`

**Template and include files (inspect changes):**

- `feat:` → New templates/includes, new custom formats, new quality profiles
- `fix:` → Corrections to existing templates/includes (wrong IDs, incorrect scores, broken
  references)
- `refactor:` → Reorganizing templates/includes without changing functionality

**Scopes from paths:**

- `radarr/**` → `(radarr)`
- `sonarr/**` → `(sonarr)`
- `templates.json`, `includes.json` → `(config)`

**Breaking changes (!):**

- Template ID renames or removals
- Include ID renames or removals
- Schema changes requiring user config updates
