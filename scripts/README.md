# Template Generation Script

`generate-template.py` reads TRaSH Guides quality profile and CF group JSON data to produce
Recyclarr config templates. Each template gives users a starting point with sensible defaults and
commented-out options they can toggle.

## CF Group Rendering

The script classifies CF groups into three categories based on their metadata. The rendering
approach for each category is designed to present user choices clearly in the template YAML, which
is a separate concern from how Recyclarr processes the groups at runtime.

### Optional groups

Groups where `default` is `false` at the group level. Rendered under `add:`, fully commented out.
Users uncomment to opt in.

```yaml
custom_format_groups:
  add:
    # - trash_id: abc123  # [Optional] Some Group
```

If the group contains CFs that are neither `required` nor `default` (i.e. the user must choose which
to include), a `select:` block is added showing those CFs:

```yaml
custom_format_groups:
  add:
    # - trash_id: abc123  # [Optional] Some Group
    #   select:
    #     - def456  # CF One
    #     - ghi789  # CF Two
```

### Default groups

Groups where `default` is `true` at the group level and no CFs within the group define `default:
true`. These are automatically enabled for their target profiles. Rendered under `skip:`, commented
out. Users uncomment to opt out.

```yaml
custom_format_groups:
  skip:
    # - abc123  # [Required] Some Group
```

### Default groups with user choices

Groups that are enabled by default but contain mutually exclusive CFs where the user is expected to
choose one. Detected when a `default: true` group has at least one CF with `default: true` at the CF
level.

These are rendered under `add:`, **uncommented**, with an explicit `select:` block. CFs marked
`default: true` are uncommented (active); others are commented out (available as alternatives).

```yaml
custom_format_groups:
  add:
    - trash_id: abc123  # [Required] Golden Rule HD
      select:
        - def456  # x265 (HD)
        # - ghi789  # x265 (no HDR/DV)
```

This rendering differs from how Recyclarr would handle the group implicitly (it would just apply the
`default: true` CF without user intervention). The template deliberately surfaces the choice so
users can see and swap between alternatives. The template is a presentation layer; it does not need
to mirror Recyclarr's runtime behavior.

Currently only the four Golden Rule groups (HD and UHD, for both Radarr and Sonarr) match this
pattern.

## Design Decisions

### Template rendering is a presentation concern, not a runtime one (2026-02-28)

Recyclarr automatically applies default CF groups and their `default: true` CFs without any YAML
configuration. The template generation script does not need to mirror that behavior. Its job is to
present all meaningful user choices explicitly, even when the defaults would produce the correct
result without intervention.

This distinction matters for groups like Golden Rule, where two mutually exclusive CFs exist and the
user is expected to pick one. Recyclarr silently applies the `default: true` CF; a user editing YAML
by hand would never know the alternative exists. The script renders these as explicit `add:` entries
with `select:` blocks so the choice is visible. The guide data's `default: true` at the CF level is
the detection signal for this; no other groups currently use it.

This was a deliberate decision over the simpler approach of putting all `default: true` groups under
`skip:` uniformly. The trade-off is that the script now has three rendering paths instead of two,
but the added complexity is justified by the user-facing clarity it provides.
