"""Tests for RenderKit browser backend lifecycle."""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from shinbot_plugin_renderkit import RenderOptions, SvgRenderOptions, TypstRenderOptions
from shinbot_plugin_renderkit.backends import (
    CairoSvgRenderBackend,
    PlaywrightRenderBackend,
    TypstCliRenderBackend,
)


class _FakePage:
    def __init__(self, tracker: _Tracker) -> None:
        self._tracker = tracker
        self.closed = False

    async def set_content(self, html: str, **_kwargs: Any) -> None:
        if self._tracker.fail_next_set_content:
            self._tracker.fail_next_set_content = False
            raise RuntimeError("set content failed")
        self._tracker.html.append(html)

    async def screenshot(self, **_kwargs: Any) -> bytes:
        if self._tracker.fail_next_screenshot:
            self._tracker.fail_next_screenshot = False
            raise RuntimeError("screenshot failed")
        self._tracker.active_pages += 1
        self._tracker.max_active_pages = max(
            self._tracker.max_active_pages,
            self._tracker.active_pages,
        )
        await asyncio.sleep(0)
        self._tracker.active_pages -= 1
        return b"shot"

    async def close(self) -> None:
        self.closed = True
        self._tracker.page_close_count += 1


class _FakeContext:
    def __init__(self, tracker: _Tracker, key: tuple[int, int, float]) -> None:
        self._tracker = tracker
        self.key = key
        self.closed = False

    async def new_page(self) -> _FakePage:
        if self._tracker.fail_next_new_page:
            self._tracker.fail_next_new_page = False
            raise RuntimeError("context is closed")
        self._tracker.page_count += 1
        return _FakePage(self._tracker)

    async def close(self) -> None:
        self.closed = True
        self._tracker.context_close_count += 1
        if self._tracker.fail_context_close:
            raise RuntimeError("context close failed")


class _FakeBrowser:
    def __init__(self, tracker: _Tracker) -> None:
        self._tracker = tracker
        self.connected = True
        self.closed = False

    def is_connected(self) -> bool:
        return self.connected

    async def new_context(
        self,
        *,
        viewport: dict[str, int],
        device_scale_factor: float,
    ) -> _FakeContext:
        key = (viewport["width"], viewport["height"], device_scale_factor)
        self._tracker.context_keys.append(key)
        return _FakeContext(self._tracker, key)

    async def close(self) -> None:
        self.closed = True
        self.connected = False
        self._tracker.browser_close_count += 1
        if self._tracker.fail_browser_close:
            raise RuntimeError("browser close failed")


class _FakeChromium:
    def __init__(self, tracker: _Tracker) -> None:
        self._tracker = tracker

    async def launch(self, **_kwargs: Any) -> _FakeBrowser:
        self._tracker.launch_count += 1
        browser = _FakeBrowser(self._tracker)
        self._tracker.browsers.append(browser)
        return browser


class _FakePlaywright:
    def __init__(self, tracker: _Tracker) -> None:
        self.chromium = _FakeChromium(tracker)
        self._tracker = tracker

    async def stop(self) -> None:
        self._tracker.playwright_stop_count += 1
        if self._tracker.fail_playwright_stop:
            raise RuntimeError("playwright stop failed")


class _Tracker:
    def __init__(self) -> None:
        self.launch_count = 0
        self.page_count = 0
        self.page_close_count = 0
        self.context_close_count = 0
        self.browser_close_count = 0
        self.playwright_stop_count = 0
        self.active_pages = 0
        self.max_active_pages = 0
        self.context_keys: list[tuple[int, int, float]] = []
        self.browsers: list[_FakeBrowser] = []
        self.html: list[str] = []
        self.fail_next_new_page = False
        self.fail_next_set_content = False
        self.fail_next_screenshot = False
        self.fail_context_close = False
        self.fail_browser_close = False
        self.fail_playwright_stop = False


class _FakePlaywrightBackend(PlaywrightRenderBackend):
    def __init__(self, tracker: _Tracker, *, max_concurrency: int = 2) -> None:
        super().__init__(max_concurrency=max_concurrency)
        self._tracker = tracker

    async def _start_playwright(self) -> _FakePlaywright:
        return _FakePlaywright(self._tracker)


@pytest.mark.asyncio
async def test_playwright_backend_reuses_browser_and_context() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)
    options = RenderOptions(width=320, height=180)

    first = await backend.render_html_to_bytes("<main>one</main>", options)
    second = await backend.render_html_to_bytes("<main>two</main>", options)
    await backend.close()

    assert first == b"shot"
    assert second == b"shot"
    assert tracker.launch_count == 1
    assert tracker.context_keys == [(320, 180, 1.0)]
    assert tracker.page_count == 2
    assert tracker.page_close_count == 2
    assert tracker.context_close_count == 1
    assert tracker.browser_close_count == 1
    assert tracker.playwright_stop_count == 1


@pytest.mark.asyncio
async def test_playwright_backend_uses_separate_context_per_viewport() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)

    await backend.render_html_to_bytes("<main>small</main>", RenderOptions(width=320, height=180))
    await backend.render_html_to_bytes("<main>large</main>", RenderOptions(width=640, height=360))
    await backend.close()

    assert tracker.launch_count == 1
    assert tracker.context_keys == [(320, 180, 1.0), (640, 360, 1.0)]
    assert tracker.context_close_count == 2


@pytest.mark.asyncio
async def test_playwright_backend_restarts_after_browser_disconnect() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)
    options = RenderOptions(width=320, height=180)

    await backend.render_html_to_bytes("<main>one</main>", options)
    tracker.browsers[0].connected = False
    await backend.render_html_to_bytes("<main>two</main>", options)
    await backend.close()

    assert tracker.launch_count == 2
    assert tracker.browser_close_count == 2
    assert tracker.playwright_stop_count == 2


@pytest.mark.asyncio
async def test_playwright_backend_evicts_context_when_new_page_fails() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)
    options = RenderOptions(width=320, height=180)

    await backend.render_html_to_bytes("<main>one</main>", options)
    tracker.fail_next_new_page = True
    with pytest.raises(RuntimeError, match="context is closed"):
        await backend.render_html_to_bytes("<main>fail</main>", options)
    await backend.render_html_to_bytes("<main>two</main>", options)
    await backend.close()

    assert tracker.launch_count == 1
    assert tracker.context_keys == [(320, 180, 1.0), (320, 180, 1.0)]
    assert tracker.context_close_count == 2


@pytest.mark.asyncio
async def test_playwright_backend_evicts_context_when_page_setup_fails() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)
    options = RenderOptions(width=320, height=180)

    await backend.render_html_to_bytes("<main>one</main>", options)
    tracker.fail_next_set_content = True
    with pytest.raises(RuntimeError, match="set content failed"):
        await backend.render_html_to_bytes("<main>fail</main>", options)
    await backend.render_html_to_bytes("<main>two</main>", options)
    await backend.close()

    assert tracker.context_keys == [(320, 180, 1.0), (320, 180, 1.0)]
    assert tracker.context_close_count == 2
    assert tracker.page_close_count == 3


@pytest.mark.asyncio
async def test_playwright_backend_evicts_context_when_screenshot_fails() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)
    options = RenderOptions(width=320, height=180)

    await backend.render_html_to_bytes("<main>one</main>", options)
    tracker.fail_next_screenshot = True
    with pytest.raises(RuntimeError, match="screenshot failed"):
        await backend.render_html_to_bytes("<main>fail</main>", options)
    await backend.render_html_to_bytes("<main>two</main>", options)
    await backend.close()

    assert tracker.context_keys == [(320, 180, 1.0), (320, 180, 1.0)]
    assert tracker.context_close_count == 2
    assert tracker.page_close_count == 3


@pytest.mark.asyncio
async def test_playwright_backend_close_is_idempotent_and_rejects_later_renders() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)

    await backend.render_html_to_bytes("<main>one</main>", RenderOptions())
    await backend.close()
    await backend.close()

    with pytest.raises(RuntimeError, match="closed"):
        await backend.render_html_to_bytes("<main>two</main>", RenderOptions())

    assert tracker.browser_close_count == 1
    assert tracker.playwright_stop_count == 1


@pytest.mark.asyncio
async def test_playwright_backend_close_continues_when_resources_fail_to_close() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker)

    await backend.render_html_to_bytes("<main>one</main>", RenderOptions(width=320, height=180))
    await backend.render_html_to_bytes("<main>two</main>", RenderOptions(width=640, height=360))
    tracker.fail_context_close = True
    tracker.fail_browser_close = True
    tracker.fail_playwright_stop = True

    await backend.close()

    with pytest.raises(RuntimeError, match="closed"):
        await backend.render_html_to_bytes("<main>three</main>", RenderOptions())
    assert tracker.context_close_count == 2
    assert tracker.browser_close_count == 1
    assert tracker.playwright_stop_count == 1


@pytest.mark.asyncio
async def test_playwright_backend_limits_concurrent_pages() -> None:
    tracker = _Tracker()
    backend = _FakePlaywrightBackend(tracker, max_concurrency=1)

    await asyncio.gather(
        backend.render_html_to_bytes("<main>one</main>", RenderOptions()),
        backend.render_html_to_bytes("<main>two</main>", RenderOptions()),
    )
    await backend.close()

    assert tracker.max_active_pages == 1


def test_cairosvg_backend_wraps_svg_fragments() -> None:
    backend = CairoSvgRenderBackend()
    options = SvgRenderOptions(width=320, height=180)

    wrapped = backend._prepare_svg_markup("<rect width='10' height='10' />", options)
    unchanged = backend._prepare_svg_markup("<svg viewBox='0 0 10 10'></svg>", options)
    xml_declared = backend._prepare_svg_markup(
        '<?xml version="1.0" encoding="UTF-8"?><svg viewBox="0 0 10 10"></svg>',
        options,
    )
    long_prefixed = backend._prepare_svg_markup(
        f"<!-- {'x' * 300} --><svg viewBox='0 0 10 10'></svg>",
        options,
    )
    xml_fragment = backend._prepare_svg_markup(
        '<?xml version="1.0"?><rect width="10" height="10" />',
        options,
    )
    xml_multi_fragment = backend._prepare_svg_markup(
        '<?xml version="1.0"?><rect width="10" height="10" /><circle r="5" />',
        options,
    )
    doctype_fragment = backend._prepare_svg_markup(
        '<!DOCTYPE svg [<!ENTITY label "x">]><text>safe</text>',
        options,
    )

    assert wrapped.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'viewBox="0 0 320 180"' in wrapped
    assert "<rect width='10' height='10' />" in wrapped
    assert unchanged == "<svg viewBox='0 0 10 10'></svg>"
    assert xml_declared == '<?xml version="1.0" encoding="UTF-8"?><svg viewBox="0 0 10 10"></svg>'
    assert long_prefixed == f"<!-- {'x' * 300} --><svg viewBox='0 0 10 10'></svg>"
    assert '<?xml version="1.0"?>' not in xml_fragment
    assert '<rect width="10" height="10" />' in xml_fragment
    assert '<?xml version="1.0"?>' not in xml_multi_fragment
    assert '<rect width="10" height="10" /><circle r="5" />' in xml_multi_fragment
    assert "<!DOCTYPE" not in doctype_fragment
    assert "<text>safe</text>" in doctype_fragment


@pytest.mark.asyncio
async def test_cairosvg_backend_rejects_non_bytes_result(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("cairosvg")

    def svg2png(**_kwargs: Any) -> None:
        return None

    module.__dict__["svg2png"] = svg2png
    monkeypatch.setitem(sys.modules, "cairosvg", module)

    backend = CairoSvgRenderBackend()
    with pytest.raises(RuntimeError, match="image bytes"):
        await backend.render_svg_to_bytes("<svg />", SvgRenderOptions())


@pytest.mark.asyncio
async def test_cairosvg_backend_limits_concurrent_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("cairosvg")
    active = 0
    max_active = 0

    def svg2png(**_kwargs: Any) -> bytes:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        import time

        time.sleep(0.02)
        active -= 1
        return b"svg"

    module.__dict__["svg2png"] = svg2png
    monkeypatch.setitem(sys.modules, "cairosvg", module)

    backend = CairoSvgRenderBackend(max_concurrency=1)
    await asyncio.gather(
        backend.render_svg_to_bytes("<svg />", SvgRenderOptions()),
        backend.render_svg_to_bytes("<svg />", SvgRenderOptions()),
    )

    assert max_active == 1


def test_typst_cli_backend_builds_compile_command() -> None:
    backend = TypstCliRenderBackend(executable_path="/usr/bin/typst", max_concurrency=1)
    options = TypstRenderOptions(
        page=2,
        ppi=96,
        root="/work",
        font_paths=("/fonts/a", "/fonts/b"),
        package_path="/packages",
        package_cache_path="/cache",
        ignore_system_fonts=True,
        inputs={"theme": "dark", "title": "Card"},
        jobs=1,
    )

    command = backend._build_command(options)

    assert command == [
        "/usr/bin/typst",
        "compile",
        "--format",
        "png",
        "--pages",
        "2",
        "--ppi",
        "96",
        "--root",
        "/work",
        "--font-path",
        "/fonts/a",
        "--font-path",
        "/fonts/b",
        "--package-path",
        "/packages",
        "--package-cache-path",
        "/cache",
        "--ignore-system-fonts",
        "--jobs",
        "1",
        "--input",
        "theme=dark",
        "--input",
        "title=Card",
        "-",
        "-",
    ]
