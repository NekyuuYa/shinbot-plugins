"""Rendering backends for RenderKit."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from .models import RenderOptions

logger = logging.getLogger(__name__)


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
