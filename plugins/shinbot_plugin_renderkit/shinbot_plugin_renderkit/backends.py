"""Rendering backends for RenderKit."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import GifRenderOptions, RenderOptions, SvgRenderOptions, TypstRenderOptions

logger = logging.getLogger(__name__)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _executable_available(value: str | None) -> bool:
    if value is None:
        return True
    path = Path(value)
    if path.parent != Path("."):
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(value) is not None


class PlaywrightRenderBackend:
    """Render HTML through a lazily-started reusable Playwright/Chromium browser."""

    def __init__(
        self,
        *,
        executable_path: str | None = None,
        max_concurrency: int = 2,
        launch_args: Sequence[str] | None = None,
    ) -> None:
        """Create a Playwright backend.

        Args:
            executable_path: Optional Chromium executable path.
            max_concurrency: Maximum concurrent page render operations.
            launch_args: Extra Chromium launch arguments.
        """
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive.")
        self._executable_path = executable_path
        self._launch_args = list(launch_args or ["--no-sandbox"])
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._start_lock = asyncio.Lock()
        self._state_condition = asyncio.Condition()
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._contexts: dict[tuple[int, int, float], Any] = {}
        self._active_renders = 0
        self._closing = False
        self._closed = False

    @classmethod
    def is_available(cls, *, executable_path: str | None = None) -> bool:
        """Return whether the Playwright dependency and configured binary are visible."""
        return _module_available("playwright.async_api") and _executable_available(
            executable_path
        )

    async def render_html_to_bytes(self, html: str, options: RenderOptions) -> bytes:
        """Render HTML to image bytes."""
        options.validate()
        async with self._semaphore:
            await self._begin_render()
            context: Any | None = None
            page: Any | None = None
            try:
                context = await self._ensure_context(options)
                page = await context.new_page()
                await page.set_content(html, wait_until="load", timeout=options.timeout_ms)
                if options.selector:
                    locator = page.locator(options.selector).first
                    return await locator.screenshot(
                        type=options.image_format,
                        timeout=options.timeout_ms,
                        omit_background=options.transparent_background,
                    )
                return await page.screenshot(
                    type=options.image_format,
                    full_page=options.full_page,
                    timeout=options.timeout_ms,
                    omit_background=options.transparent_background,
                )
            except Exception:
                if context is not None:
                    await self._evict_context(options, context)
                raise
            finally:
                try:
                    if page is not None:
                        await self._close_resource(page, "page")
                finally:
                    await self._end_render()

    async def close(self) -> None:
        """Close the reusable browser and Playwright driver."""
        async with self._state_condition:
            if self._closed:
                return
            self._closing = True
            await self._state_condition.wait_for(lambda: self._active_renders == 0)

        try:
            async with self._start_lock:
                contexts = list(self._contexts.values())
                browser = self._browser
                playwright = self._playwright
                self._contexts.clear()
                self._browser = None
                self._playwright = None
                for context in contexts:
                    await self._close_resource(context, "context")
                if browser is not None:
                    await self._close_resource(browser, "browser")
                if playwright is not None:
                    await self._close_resource(playwright, "playwright")
        finally:
            async with self._state_condition:
                self._closed = True
                self._closing = False
                self._state_condition.notify_all()

    async def _begin_render(self) -> None:
        async with self._state_condition:
            if self._closed or self._closing:
                raise RuntimeError("Render backend is closed.")
            self._active_renders += 1

    async def _end_render(self) -> None:
        async with self._state_condition:
            self._active_renders -= 1
            if self._active_renders <= 0:
                self._state_condition.notify_all()

    async def _ensure_context(self, options: RenderOptions) -> Any:
        browser = await self._ensure_browser()
        key = self._context_key(options)
        context = self._contexts.get(key)
        if context is not None:
            return context
        async with self._start_lock:
            context = self._contexts.get(key)
            if context is not None:
                return context
            context = await browser.new_context(
                viewport={"width": options.width, "height": options.height},
                device_scale_factor=options.device_scale_factor,
            )
            self._contexts[key] = context
            return context

    async def _evict_context(self, options: RenderOptions, context: Any) -> None:
        key = self._context_key(options)
        async with self._start_lock:
            if self._contexts.get(key) is not context:
                return
            evicted = self._contexts.pop(key)
        await self._close_resource(evicted, "context")

    def _context_key(self, options: RenderOptions) -> tuple[int, int, float]:
        return (options.width, options.height, options.device_scale_factor)

    async def _ensure_browser(self) -> Any:
        if self._closed:
            raise RuntimeError("Render backend is closed.")
        if self._browser is not None and self._browser_connected(self._browser):
            return self._browser
        async with self._start_lock:
            if self._browser is not None and self._browser_connected(self._browser):
                return self._browser
            await self._discard_browser()
            self._playwright = await self._start_playwright()
            launch_options: dict[str, object] = {
                "headless": True,
                "args": self._launch_args,
            }
            if self._executable_path is not None:
                launch_options["executable_path"] = self._executable_path
            self._browser = await self._playwright.chromium.launch(**launch_options)
            return self._browser

    async def _discard_browser(self) -> None:
        contexts = list(self._contexts.values())
        browser = self._browser
        playwright = self._playwright
        self._contexts.clear()
        self._browser = None
        self._playwright = None
        for context in contexts:
            await self._close_resource(context, "context")
        if browser is not None:
            await self._close_resource(browser, "browser")
        if playwright is not None:
            await self._close_resource(playwright, "playwright")

    async def _close_resource(self, resource: Any, label: str) -> None:
        try:
            if label == "playwright":
                await resource.stop()
            else:
                await resource.close()
        except Exception:
            logger.exception("RenderKit failed to close %s resource", label)

    def _browser_connected(self, browser: Any) -> bool:
        is_connected = getattr(browser, "is_connected", None)
        if is_connected is None:
            return True
        return bool(is_connected())

    async def _start_playwright(self) -> Any:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for RenderKit browser rendering. "
                "Install the plugin with the 'browser' extra or provide a custom backend."
            ) from exc
        return await async_playwright().start()


class CairoSvgRenderBackend:
    """Render SVG through CairoSVG in a worker thread."""

    def __init__(self, *, max_concurrency: int = 2) -> None:
        """Create a CairoSVG backend.

        Args:
            max_concurrency: Maximum concurrent SVG raster operations.
        """
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive.")
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @classmethod
    def is_available(cls) -> bool:
        """Return whether the CairoSVG dependency is importable."""
        return _module_available("cairosvg")

    async def render_svg_to_bytes(self, svg: str, options: SvgRenderOptions) -> bytes:
        """Render SVG markup to PNG bytes."""
        options.validate()
        prepared_svg = self._prepare_svg_markup(svg, options)
        try:
            from cairosvg import svg2png
        except ImportError as exc:
            raise RuntimeError(
                "CairoSVG is required for RenderKit SVG rendering. "
                "Install the plugin with the 'svg' extra or provide a custom SVG backend."
            ) from exc

        def render() -> bytes:
            result = svg2png(
                bytestring=prepared_svg.encode("utf-8"),
                output_width=options.width,
                output_height=options.height,
                scale=options.scale,
                background_color=options.background_color,
                unsafe=options.unsafe,
            )
            if not isinstance(result, bytes):
                raise RuntimeError("CairoSVG did not return image bytes.")
            return result

        async with self._semaphore:
            return await asyncio.wait_for(
                asyncio.to_thread(render),
                timeout=options.timeout_ms / 1000,
            )

    def _prepare_svg_markup(self, svg: str, options: SvgRenderOptions) -> str:
        stripped = svg.strip()
        _, first_element = self._split_svg_preamble(stripped)
        if self._element_name(first_element) == "svg":
            return stripped
        content = self._strip_document_preamble(stripped)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{options.width}" height="{options.height}" '
            f'viewBox="0 0 {options.width} {options.height}">'
            f"{content}</svg>"
        )

    def _strip_document_preamble(self, svg: str) -> str:
        preamble, content = self._split_svg_preamble(svg)
        stripped_preamble = self._strip_xml_document_declarations(preamble)
        return f"{stripped_preamble}{content}".strip()

    def _split_svg_preamble(self, svg: str) -> tuple[str, str]:
        index = 0
        while index < len(svg):
            next_index = self._skip_preamble_item(svg, index)
            if next_index == index:
                break
            index = next_index
        return svg[:index], svg[index:].lstrip()

    def _skip_preamble_item(self, svg: str, index: int) -> int:
        index = self._skip_whitespace(svg, index)
        lower = svg[index:].lower()
        if lower.startswith("<?xml"):
            return self._skip_until(svg, index, "?>")
        if lower.startswith("<!--"):
            return self._skip_until(svg, index, "-->")
        if lower.startswith("<?"):
            return self._skip_until(svg, index, "?>")
        if lower.startswith("<!doctype"):
            return self._skip_doctype(svg, index)
        return index

    def _strip_xml_document_declarations(self, preamble: str) -> str:
        index = 0
        kept: list[str] = []
        while index < len(preamble):
            whitespace_end = self._skip_whitespace(preamble, index)
            kept.append(preamble[index:whitespace_end])
            index = whitespace_end
            lower = preamble[index:].lower()
            if lower.startswith("<?xml"):
                index = self._skip_until(preamble, index, "?>")
                continue
            if lower.startswith("<!doctype"):
                index = self._skip_doctype(preamble, index)
                continue
            next_index = self._skip_preamble_item(preamble, index)
            if next_index == index:
                kept.append(preamble[index:])
                break
            kept.append(preamble[index:next_index])
            index = next_index
        return "".join(kept)

    def _element_name(self, markup: str) -> str | None:
        stripped = markup.lstrip()
        if not stripped.startswith("<") or stripped.startswith(("</", "<!", "<?")):
            return None
        index = 1
        while index < len(stripped) and stripped[index] not in " \t\r\n/>":
            index += 1
        name = stripped[1:index].lower()
        return name.rsplit(":", 1)[-1] if name else None

    def _skip_whitespace(self, text: str, index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def _skip_until(self, text: str, index: int, token: str) -> int:
        end = text.find(token, index + len(token))
        return len(text) if end < 0 else end + len(token)

    def _skip_doctype(self, text: str, index: int) -> int:
        quote: str | None = None
        bracket_depth = 0
        cursor = index + len("<!doctype")
        while cursor < len(text):
            char = text[cursor]
            if quote is not None:
                if char == quote:
                    quote = None
            elif char in {'"', "'"}:
                quote = char
            elif char == "[":
                bracket_depth += 1
            elif char == "]" and bracket_depth > 0:
                bracket_depth -= 1
            elif char == ">" and bracket_depth == 0:
                return cursor + 1
            cursor += 1
        return len(text)


class TypstCliRenderBackend:
    """Render Typst source through the Typst CLI."""

    def __init__(
        self,
        *,
        executable_path: str = "typst",
        max_concurrency: int = 2,
    ) -> None:
        """Create a Typst CLI backend.

        Args:
            executable_path: Typst executable path or command name.
            max_concurrency: Maximum concurrent Typst compile operations.
        """
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive.")
        self._executable_path = executable_path
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @classmethod
    def is_available(cls, *, executable_path: str = "typst") -> bool:
        """Return whether the configured Typst executable is visible."""
        return _executable_available(executable_path)

    async def render_typst_to_bytes(self, source: str, options: TypstRenderOptions) -> bytes:
        """Render Typst source to PNG bytes."""
        options.validate()
        command = self._build_command(options)
        async with self._semaphore:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Typst CLI is required for RenderKit Typst rendering. "
                    "Install typst or configure typst_executable_path."
                ) from exc
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(source.encode("utf-8")),
                    timeout=options.timeout_ms / 1000,
                )
            except TimeoutError as exc:
                process.kill()
                try:
                    await asyncio.wait_for(process.communicate(), timeout=5)
                except TimeoutError:
                    await process.wait()
                raise RuntimeError("Typst rendering timed out.") from exc
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Typst rendering failed: {message or process.returncode}")
        if not stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Typst did not return PNG image bytes.")
        return stdout

    def _build_command(self, options: TypstRenderOptions) -> list[str]:
        command = [
            self._executable_path,
            "compile",
            "--format",
            options.image_format,
            "--pages",
            str(options.page),
            "--ppi",
            str(options.ppi),
        ]
        if options.root is not None:
            command.extend(["--root", str(options.root)])
        for font_path in options.font_paths:
            command.extend(["--font-path", str(font_path)])
        if options.package_path is not None:
            command.extend(["--package-path", str(options.package_path)])
        if options.package_cache_path is not None:
            command.extend(["--package-cache-path", str(options.package_cache_path)])
        if options.ignore_system_fonts:
            command.append("--ignore-system-fonts")
        if options.jobs is not None:
            command.extend(["--jobs", str(options.jobs)])
        for key, value in sorted((options.inputs or {}).items()):
            command.extend(["--input", f"{key}={value}"])
        command.extend(["-", "-"])
        return command


class FfmpegGifBackend:
    """Compose animated GIFs from image frame sequences using ffmpeg.

    Uses the palettegen + paletteuse filter chain for high-quality
    256-color output without visible banding.
    """

    def __init__(
        self,
        *,
        executable_path: str = "ffmpeg",
        max_concurrency: int = 2,
    ) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive.")
        self._executable_path = executable_path
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @classmethod
    def is_available(cls, *, executable_path: str = "ffmpeg") -> bool:
        """Return whether the configured ffmpeg executable is visible."""
        return _executable_available(executable_path)

    async def render_frames_to_gif(
        self,
        frames: Sequence[bytes],
        options: GifRenderOptions | None = None,
    ) -> bytes:
        """Compose an animated GIF from raw image *frames* (PNG/JPEG bytes).

        Returns the GIF file as bytes.
        """
        from .models import GifRenderOptions as GifOpts

        opts = options or GifOpts()
        opts.validate()

        async with self._semaphore:
            return await asyncio.to_thread(self._render_sync, frames, opts)

    def _render_sync(
        self,
        frames: Sequence[bytes],
        options: GifRenderOptions,
    ) -> bytes:
        """Blocking composition — runs in a thread via ``asyncio.to_thread``."""
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Write frames as numbered files
            suffix = self._detect_suffix(frames[0]) if frames else ".png"
            for i, raw in enumerate(frames):
                (tmp / f"frame-{i:04d}{suffix}").write_bytes(raw)

            palette = tmp / "palette.png"
            output = tmp / "output.gif"

            loop_flag = "0" if options.loop else "-1"

            # Pass 1: generate optimal palette
            subprocess.run(
                [
                    self._executable_path, "-y",
                    "-framerate", str(options.fps),
                    "-i", str(tmp / f"frame-%04d{suffix}"),
                    "-vf", f"palettegen=stats_mode={options.palette_mode}",
                    str(palette),
                ],
                capture_output=True,
                check=True,
                timeout=options.timeout_ms / 1000,
            )

            # Pass 2: compose GIF with palette
            subprocess.run(
                [
                    self._executable_path, "-y",
                    "-framerate", str(options.fps),
                    "-i", str(tmp / f"frame-%04d{suffix}"),
                    "-i", str(palette),
                    "-lavfi", f"paletteuse=dither={options.dither}",
                    "-loop", loop_flag,
                    str(output),
                ],
                capture_output=True,
                check=True,
                timeout=options.timeout_ms / 1000,
            )

            return output.read_bytes()

    @staticmethod
    def _detect_suffix(data: bytes) -> str:
        """Guess image file extension from magic bytes."""
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if data[:2] == b"\xff\xd8":
            return ".jpg"
        return ".png"
