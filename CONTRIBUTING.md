# Contributing

## Setup

```bash
uv sync --group dev
uv run pre-commit install
```

`pre-commit install` registers the git hook that applies the repo's formatter locally before you commit.

## Working on xpectral-utils locally

`xpectral-quant` imports shared helpers (`rate_limiter`, `s3`, `cache`, `logger`)
from `xpectral-utils`. If you're making changes to a local checkout of
`xpectral-utils` (expected at `../xpectral-utils`) and want this repo to pick
them up, install it into the venv directly instead of editing `pyproject.toml`:

```bash
uv pip install -e "../xpectral-utils[s3,cache]"
```

The extras pull in `boto3` (for `xpectral_utils.s3`) and `diskcache` (for
`xpectral_utils.cache`). This keeps `pyproject.toml` and `uv.lock` pointed at
the published version for everyone else. The editable install only affects your
local venv, so a future `uv sync` will remove it again. Reinstall with the
command above whenever that happens.
