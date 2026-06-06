"""High-level RenderKit APIs."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .backends import PlaywrightRenderBackend
from .models import RenderBackend, RenderOptions, RenderResult
from .template import render_template_text

_DEFAULT_BACKEND: RenderBackend | None = None
_DEFAULT_BACKEND_LOCK = threading.RLock()


def configure_default_backend(backend: RenderBackend | None) -> None:
    """Set the process-local default backend used when callers do not pass one."""
    global _DEFAULT_BACKEND
    with _DEFAULT_BACKEND_LOCK:
        _DEFAULT_BACKEND = backend


def get_default_backend() -> RenderBackend:
    """Return the lazily-created default render backend."""
    global _DEFAULT_BACKEND
    with _DEFAULT_BACKEND_LOCK:
        if _DEFAULT_BACKEND is None:
            _DEFAULT_BACKEND = PlaywrightRenderBackend()
        return _DEFAULT_BACKEND


async def close_default_backend() -> None:
    """Close and clear the default backend when it owns resources."""
    global _DEFAULT_BACKEND
    with _DEFAULT_BACKEND_LOCK:
        backend = _DEFAULT_BACKEND
    close = getattr(backend, "close", None)
    if close is not None:
        await close()
    with _DEFAULT_BACKEND_LOCK:
        if _DEFAULT_BACKEND is backend:
            _DEFAULT_BACKEND = None


async def render_html_to_bytes(
    html: str,
    *,
    options: RenderOptions | None = None,
    backend: RenderBackend | None = None,
) -> bytes:
    """Render HTML/CSS into image bytes.

    Args:
        html: Full HTML document or fragment.
        options: Rendering options.
        backend: Optional backend override.
    """
    active_options = options or RenderOptions()
    active_options.validate()
    active_backend = backend or get_default_backend()
    return await active_backend.render_html_to_bytes(html, active_options)


async def render_html_to_file(
    html: str,
    *,
    output_dir: str | Path,
    options: RenderOptions | None = None,
    backend: RenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render HTML/CSS into an image file.

    Args:
        html: Full HTML document or fragment.
        output_dir: Directory where the image file is written.
        options: Rendering options.
        backend: Optional backend override.
        cache: Reuse an existing file when the request hash matches.
        filename: Optional explicit filename. If omitted, a stable hash is used.
    """
    active_options = options or RenderOptions()
    active_options.validate()
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _resolve_filename(
        html,
        options=active_options,
        filename=filename,
    )
    if cache and target_path.is_file():
        return RenderResult(
            path=target_path,
            mime_type=active_options.mime_type,
            width=active_options.width,
            height=active_options.height,
            cached=True,
        )

    image_bytes = await render_html_to_bytes(
        html,
        options=active_options,
        backend=backend,
    )
    target_path.write_bytes(image_bytes)
    return RenderResult(
        path=target_path,
        mime_type=active_options.mime_type,
        width=active_options.width,
        height=active_options.height,
        cached=False,
    )


async def render_template_to_bytes(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    options: RenderOptions | None = None,
    backend: RenderBackend | None = None,
) -> bytes:
    """Render a Jinja2 HTML template into image bytes."""
    html = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_html_to_bytes(html, options=options, backend=backend)


async def render_template_to_file(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    output_dir: str | Path,
    options: RenderOptions | None = None,
    backend: RenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render a Jinja2 HTML template into an image file."""
    html = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_html_to_file(
        html,
        output_dir=output_dir,
        options=options,
        backend=backend,
        cache=cache,
        filename=filename,
    )


def _resolve_filename(
    html: str,
    *,
    options: RenderOptions,
    filename: str | None,
) -> str:
    if filename is not None:
        return filename
    payload = {
        "html": html,
        "options": {
            "width": options.width,
            "height": options.height,
            "image_format": options.image_format,
            "device_scale_factor": options.device_scale_factor,
            "full_page": options.full_page,
            "selector": options.selector,
            "transparent_background": options.transparent_background,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"render-{digest}{options.suffix}"
