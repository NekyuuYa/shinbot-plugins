"""High-level RenderKit APIs."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .backends import (
    CairoSvgRenderBackend,
    FfmpegGifBackend,
    PlaywrightRenderBackend,
    TypstCliRenderBackend,
)
from .models import (
    GifRenderOptions,
    RenderBackend,
    RenderKitCapabilities,
    RenderOptions,
    RenderResult,
    SvgRenderBackend,
    SvgRenderOptions,
    TypstRenderBackend,
    TypstRenderOptions,
)
from .template import render_template_text

_DEFAULT_BACKEND: RenderBackend | None = None
_DEFAULT_BACKEND_LOCK = threading.RLock()
_DEFAULT_SVG_BACKEND: SvgRenderBackend | None = None
_DEFAULT_SVG_BACKEND_LOCK = threading.RLock()
_DEFAULT_TYPST_BACKEND: TypstRenderBackend | None = None
_DEFAULT_TYPST_BACKEND_LOCK = threading.RLock()
_DEFAULT_GIF_BACKEND: FfmpegGifBackend | None = None
_DEFAULT_GIF_BACKEND_LOCK = threading.RLock()


def probe_renderkit_capabilities(
    *,
    chromium_executable_path: str | None = None,
    typst_executable_path: str = "typst",
) -> RenderKitCapabilities:
    """Return backend availability for the current process environment.

    The probe is intentionally shallow: it checks Python dependencies and
    configured executable visibility without launching a browser or compiling a
    document.
    """
    return RenderKitCapabilities(
        html=PlaywrightRenderBackend.is_available(executable_path=chromium_executable_path),
        svg=CairoSvgRenderBackend.is_available(),
        typst=TypstCliRenderBackend.is_available(executable_path=typst_executable_path),
        gif=FfmpegGifBackend.is_available(),
    )


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


def configure_default_svg_backend(backend: SvgRenderBackend | None) -> None:
    """Set the process-local default SVG backend used when callers do not pass one."""
    global _DEFAULT_SVG_BACKEND
    with _DEFAULT_SVG_BACKEND_LOCK:
        _DEFAULT_SVG_BACKEND = backend


def get_default_svg_backend() -> SvgRenderBackend:
    """Return the lazily-created default SVG render backend."""
    global _DEFAULT_SVG_BACKEND
    with _DEFAULT_SVG_BACKEND_LOCK:
        if _DEFAULT_SVG_BACKEND is None:
            _DEFAULT_SVG_BACKEND = CairoSvgRenderBackend()
        return _DEFAULT_SVG_BACKEND


async def close_default_svg_backend() -> None:
    """Close and clear the default SVG backend when it owns resources."""
    global _DEFAULT_SVG_BACKEND
    with _DEFAULT_SVG_BACKEND_LOCK:
        backend = _DEFAULT_SVG_BACKEND
    close = getattr(backend, "close", None)
    try:
        if close is not None:
            await close()
    finally:
        with _DEFAULT_SVG_BACKEND_LOCK:
            if _DEFAULT_SVG_BACKEND is backend:
                _DEFAULT_SVG_BACKEND = None


def configure_default_typst_backend(backend: TypstRenderBackend | None) -> None:
    """Set the process-local default Typst backend used when callers do not pass one."""
    global _DEFAULT_TYPST_BACKEND
    with _DEFAULT_TYPST_BACKEND_LOCK:
        _DEFAULT_TYPST_BACKEND = backend


def get_default_typst_backend() -> TypstRenderBackend:
    """Return the lazily-created default Typst render backend."""
    global _DEFAULT_TYPST_BACKEND
    with _DEFAULT_TYPST_BACKEND_LOCK:
        if _DEFAULT_TYPST_BACKEND is None:
            _DEFAULT_TYPST_BACKEND = TypstCliRenderBackend()
        return _DEFAULT_TYPST_BACKEND


async def close_default_typst_backend() -> None:
    """Close and clear the default Typst backend when it owns resources."""
    global _DEFAULT_TYPST_BACKEND
    with _DEFAULT_TYPST_BACKEND_LOCK:
        backend = _DEFAULT_TYPST_BACKEND
    close = getattr(backend, "close", None)
    try:
        if close is not None:
            await close()
    finally:
        with _DEFAULT_TYPST_BACKEND_LOCK:
            if _DEFAULT_TYPST_BACKEND is backend:
                _DEFAULT_TYPST_BACKEND = None




def configure_default_gif_backend(backend: FfmpegGifBackend | None) -> None:
    """Set the process-local default GIF backend used when callers do not pass one."""
    global _DEFAULT_GIF_BACKEND
    with _DEFAULT_GIF_BACKEND_LOCK:
        _DEFAULT_GIF_BACKEND = backend


def get_default_gif_backend() -> FfmpegGifBackend:
    """Return the lazily-created default GIF render backend."""
    global _DEFAULT_GIF_BACKEND
    with _DEFAULT_GIF_BACKEND_LOCK:
        if _DEFAULT_GIF_BACKEND is None:
            _DEFAULT_GIF_BACKEND = FfmpegGifBackend()
        return _DEFAULT_GIF_BACKEND


async def close_default_gif_backend() -> None:
    """Close and clear the default GIF backend when it owns resources."""
    global _DEFAULT_GIF_BACKEND
    with _DEFAULT_GIF_BACKEND_LOCK:
        backend = _DEFAULT_GIF_BACKEND
    close = getattr(backend, "close", None)
    try:
        if close is not None:
            await close()
    finally:
        with _DEFAULT_GIF_BACKEND_LOCK:
            if _DEFAULT_GIF_BACKEND is backend:
                _DEFAULT_GIF_BACKEND = None


async def render_frames_to_gif(
    frames: Sequence[bytes],
    *,
    options: GifRenderOptions | None = None,
    backend: FfmpegGifBackend | None = None,
) -> bytes:
    """Compose an animated GIF from raw image *frames* using ffmpeg.

    Uses palettegen + paletteuse for high-quality 256-color output.

    Args:
        frames: Raw PNG/JPEG image bytes, one per frame, in order.
        options: GIF rendering options (fps, dither, etc.).
        backend: Optional GIF backend override.
    """
    active_options = options or GifRenderOptions()
    active_options.validate()
    active_backend = backend or get_default_gif_backend()
    return await active_backend.render_frames_to_gif(frames, options=active_options)



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


async def render_svg_to_bytes(
    svg: str,
    *,
    options: SvgRenderOptions | None = None,
    backend: SvgRenderBackend | None = None,
) -> bytes:
    """Render SVG markup into image bytes.

    Args:
        svg: SVG document or fragment markup.
        options: SVG rendering options.
        backend: Optional SVG backend override.
    """
    active_options = options or SvgRenderOptions()
    active_options.validate()
    active_backend = backend or get_default_svg_backend()
    return await active_backend.render_svg_to_bytes(svg, active_options)


async def render_typst_to_bytes(
    source: str,
    *,
    options: TypstRenderOptions | None = None,
    backend: TypstRenderBackend | None = None,
) -> bytes:
    """Render Typst source into image bytes.

    Args:
        source: Typst source text.
        options: Typst rendering options.
        backend: Optional Typst backend override.
    """
    active_options = options or TypstRenderOptions()
    active_options.validate()
    active_backend = backend or get_default_typst_backend()
    return await active_backend.render_typst_to_bytes(source, active_options)


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


async def render_svg_to_file(
    svg: str,
    *,
    output_dir: str | Path,
    options: SvgRenderOptions | None = None,
    backend: SvgRenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render SVG markup into an image file.

    Args:
        svg: SVG document or fragment markup.
        output_dir: Directory where the image file is written.
        options: SVG rendering options.
        backend: Optional SVG backend override.
        cache: Reuse an existing file when the request hash matches.
        filename: Optional explicit filename. If omitted, a stable hash is used.
    """
    active_options = options or SvgRenderOptions()
    active_options.validate()
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _resolve_svg_filename(
        svg,
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

    image_bytes = await render_svg_to_bytes(
        svg,
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


async def render_typst_to_file(
    source: str,
    *,
    output_dir: str | Path,
    options: TypstRenderOptions | None = None,
    backend: TypstRenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render Typst source into an image file.

    Args:
        source: Typst source text.
        output_dir: Directory where the image file is written.
        options: Typst rendering options.
        backend: Optional Typst backend override.
        cache: Reuse an existing file when the request hash matches.
        filename: Optional explicit filename. If omitted, a stable hash is used.
    """
    active_options = options or TypstRenderOptions()
    active_options.validate()
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / _resolve_typst_filename(
        source,
        options=active_options,
        filename=filename,
    )
    if cache and target_path.is_file():
        width, height = _png_dimensions(target_path.read_bytes())
        _validate_typst_dimensions(width, height, active_options)
        return RenderResult(
            path=target_path,
            mime_type=active_options.mime_type,
            width=width,
            height=height,
            cached=True,
        )

    image_bytes = await render_typst_to_bytes(
        source,
        options=active_options,
        backend=backend,
    )
    width, height = _png_dimensions(image_bytes)
    _validate_typst_dimensions(width, height, active_options)
    target_path.write_bytes(image_bytes)
    return RenderResult(
        path=target_path,
        mime_type=active_options.mime_type,
        width=width,
        height=height,
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


async def render_svg_template_to_bytes(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    options: SvgRenderOptions | None = None,
    backend: SvgRenderBackend | None = None,
) -> bytes:
    """Render a Jinja2 SVG template into image bytes."""
    svg = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_svg_to_bytes(svg, options=options, backend=backend)


async def render_typst_template_to_bytes(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    options: TypstRenderOptions | None = None,
    backend: TypstRenderBackend | None = None,
) -> bytes:
    """Render a Jinja2 Typst template into image bytes."""
    source = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_typst_to_bytes(source, options=options, backend=backend)


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


async def render_svg_template_to_file(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    output_dir: str | Path,
    options: SvgRenderOptions | None = None,
    backend: SvgRenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render a Jinja2 SVG template into an image file."""
    svg = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_svg_to_file(
        svg,
        output_dir=output_dir,
        options=options,
        backend=backend,
        cache=cache,
        filename=filename,
    )


async def render_typst_template_to_file(
    template: str | Path,
    *,
    data: Mapping[str, Any] | None = None,
    template_dirs: Sequence[str | Path] | None = None,
    output_dir: str | Path,
    options: TypstRenderOptions | None = None,
    backend: TypstRenderBackend | None = None,
    cache: bool = True,
    filename: str | None = None,
) -> RenderResult:
    """Render a Jinja2 Typst template into an image file."""
    source = render_template_text(template, data=data, template_dirs=template_dirs)
    return await render_typst_to_file(
        source,
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


def _resolve_svg_filename(
    svg: str,
    *,
    options: SvgRenderOptions,
    filename: str | None,
) -> str:
    if filename is not None:
        return filename
    payload = {
        "svg": svg,
        "options": {
            "width": options.width,
            "height": options.height,
            "image_format": options.image_format,
            "scale": options.scale,
            "background_color": options.background_color,
            "unsafe": options.unsafe,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"render-svg-{digest}{options.suffix}"


def _resolve_typst_filename(
    source: str,
    *,
    options: TypstRenderOptions,
    filename: str | None,
) -> str:
    if filename is not None:
        return filename
    payload = {
        "source": source,
        "options": {
            "image_format": options.image_format,
            "page": options.page,
            "ppi": options.ppi,
            "root": str(options.root) if options.root is not None else None,
            "max_width": options.max_width,
            "max_height": options.max_height,
            "font_paths": [str(item) for item in options.font_paths],
            "package_path": (
                str(options.package_path) if options.package_path is not None else None
            ),
            "package_cache_path": (
                str(options.package_cache_path)
                if options.package_cache_path is not None
                else None
            ),
            "ignore_system_fonts": options.ignore_system_fonts,
            "inputs": options.inputs or {},
            "jobs": options.jobs,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:24]
    return f"render-typst-{digest}{options.suffix}"


def _png_dimensions(image_bytes: bytes) -> tuple[int, int]:
    if (
        len(image_bytes) < 24
        or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        or image_bytes[12:16] != b"IHDR"
    ):
        raise ValueError("Image bytes are not a PNG document.")
    return (
        int.from_bytes(image_bytes[16:20], "big"),
        int.from_bytes(image_bytes[20:24], "big"),
    )


def _validate_typst_dimensions(
    width: int,
    height: int,
    options: TypstRenderOptions,
) -> None:
    if width > options.max_width or height > options.max_height:
        raise ValueError(
            "Typst output dimensions exceed configured limits: "
            f"{width}x{height} > {options.max_width}x{options.max_height}."
        )
