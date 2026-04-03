# Contributing

## Setup

```bash
uv sync --group dev
uv run pre-commit install
```

`pre-commit install` registers the git hook that regenerates `.pyi` stubs automatically on every commit.
