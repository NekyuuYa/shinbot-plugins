# ShinBot Plugins

Community and optional plugin monorepo for ShinBot.

This repository is intended for plugins that are useful outside the ShinBot core
repository, but do not yet need their own standalone repository.

## Layout

```text
.
├── plugins/                  # Individual ShinBot plugins
├── libs/                     # Shared helper packages for plugins
├── tests/                    # Cross-plugin tests and test utilities
└── .github/workflows/        # Repository CI
```

Plugin packages should keep the ShinBot naming convention:

```text
plugins/
└── shinbot_plugin_example/
    ├── pyproject.toml
    ├── README.md
    ├── shinbot_plugin_example/
    │   └── __init__.py
    └── tests/
```

Each plugin exposes a `setup(plg)` entry point from its package.

## When to Split a Plugin Out

Keep plugins in this monorepo while they are small, experimental, or maintained
by the same team. Split a plugin into its own repository when it needs an
independent release cadence, separate maintainers, heavy dependencies, or a
standalone user community.

## Development

Install development dependencies:

```bash
uv sync --group dev
```

Run checks:

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

Individual plugins may also define their own `pyproject.toml` and test commands.
