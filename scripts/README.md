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

If the group has CFs the user can toggle, they are listed beneath it. See "CF rendering within a
group" below.

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

### Default groups with adjustable CFs

Groups where `default` is `true` at the group level and at least one CF within the group defines
`default: true`. Recyclarr syncs these whether or not they appear in the YAML, so they are rendered
under `add:`, uncommented, to make their CFs adjustable.

```yaml
custom_format_groups:
  add:
    - trash_id: abc123  # [Optional] Golden Rule UHD
      exclude:
        # - def456  # x265 (no HDR/DV)
      select:
        # - ghi789  # x265 (HD)
```

## CF rendering within a group

One rule covers every group under `add:`, matching Recyclarr 8.1.0+ semantics where the effective
set is `required + (default - exclude) + select`:

| CF flag | Rendered as |
| --- | --- |
| `required` | not listed; always included and cannot be excluded |
| `default` | commented under `exclude:`; uncomment to turn OFF |
| neither | commented under `select:`; uncomment to turn ON |

A node with no members is omitted. In an uncommented group the `exclude:` and `select:` keys
themselves stay uncommented, so toggling a CF is one uncomment rather than two. An empty node is
valid: Recyclarr's schema types both as `["null", "array"]` and maps null to an empty list.

Inside a commented (opt-in) group the whole block is commented, so `exclude:` members carry an extra
comment level. Otherwise enabling the group would also strip its defaults.

## Conflicting custom formats

The guides publish `conflicts.json`, naming sets of CFs that must not be enabled together. Recyclarr
does not read this file, so the templates handle it themselves. It is loaded via `metadata.json`
`json_paths.<service>.conflicts` so new sets are picked up without a code change, and it affects
rendering in two ways.

Groups holding two or more members of one set gain a note:

```yaml
- trash_id: abc123  # [Optional] Golden Rule UHD
  # Mutually exclusive: enable only one of the following.
```

And in a commented group whose conflicting members all sit under `select:`, one member stays at the
block's own comment level while the rest are nested one level deeper, so uncommenting the block
enables exactly one:

```yaml
# - trash_id: abc123  # [HDR Formats] SDR
#   # Mutually exclusive: enable only one of the following.
#   select:
#     - def456  # SDR
#     # - ghi789  # SDR (no WEBDL)
```

`ci/check_conflicting_cfs.py` asserts both properties over the committed templates.
