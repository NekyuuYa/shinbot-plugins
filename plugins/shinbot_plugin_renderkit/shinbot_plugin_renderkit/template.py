"""Jinja2 template helpers for RenderKit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template


def render_template_text(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
) -> str:
    """Render a Jinja2 template to an HTML string.

    Args:
        template: Template name, template path, or raw template text.
        data: Template variables.
        template_dirs: Directories used to resolve template names.

    Returns:
        Rendered HTML text.
    """
    context = dict(data or {})
    if template_dirs:
        loader = FileSystemLoader([str(Path(directory)) for directory in template_dirs])
        environment = Environment(
            autoescape=True,
            loader=loader,
            undefined=StrictUndefined,
        )
        return environment.get_template(str(template)).render(context)

    path = Path(template)
    if path.is_file():
        source = path.read_text(encoding="utf-8")
    else:
        source = str(template)
    return Template(source, autoescape=True, undefined=StrictUndefined).render(context)
