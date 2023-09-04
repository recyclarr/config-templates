# Recyclarr Configuration Templates

This is the repository for pre-made Configuration for the [Recyclarr] command line tool. These
pre-made YAML files are referred to as "templates" because it is expected to serve as a starting
point to which users may optionally customize and branch out from.

[Recyclarr]: https://github.com/recyclarr/recyclarr

## Getting Started

If you are interested in using one of the configuration templates, see the tips below.

1. If you haven't installed Recyclarr yet, do that first. You can [read the docs][1] for more info.
1. Use the `config create` command to create one or more templates locally that you can edit and
   use. The [CLI Reference][3] can help you understand exactly how to run this command.
1. Each template typically has a [`base_url` and `api_key` properties][4] that you are *required* to
   assign real values.
1. Refer to the [Configuration YAML Reference][2] for details on the different parts of the template
   if you are interested in making changes or understanding more about it.

[1]: https://recyclarr.dev/wiki/
[2]: https://recyclarr.dev/wiki/yaml/config-reference/
[3]: https://recyclarr.dev/wiki/cli/config/create/
[4]: https://recyclarr.dev/wiki/yaml/config-reference/basic/

## Contributing

See the [CONTRIBUTING.md](CONTRIBUTING.md) file if you're interested in contributing to the
templates!
