# Contributing

Helpful information for contributing to the config templates repo.

## YAML Lint: Local Testing

In order to test locally, you first must install [Python 3] and [yamllint].

On Windows, you must set an environment variable: `PYTHONUTF8=1`. This is required otherwise you'll
see a bunch of `line-lenth` lint errors because the French YAML files use unicode characters. See
[this issue][line-length-bug] for more information.

To execute YAML lint locally, `cd` to the root of the repo and run:

```bash
yamllint .
```

[Python 3]: https://www.python.org/downloads/
[yamllint]: https://yamllint.readthedocs.io/en/stable/quickstart.html#installing-yamllint
[line-length-bug]: https://github.com/adrienverge/yamllint/issues/530#issuecomment-1402452147
