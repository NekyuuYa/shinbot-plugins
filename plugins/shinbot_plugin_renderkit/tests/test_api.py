"""Tests for RenderKit public rendering APIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from shinbot_plugin_renderkit import (
    RenderOptions,
    SvgRenderOptions,
    close_default_backend,
    close_default_svg_backend,
    configure_default_backend,
    configure_default_svg_backend,
    render_html_to_bytes,
    render_html_to_file,
    render_svg_template_to_file,
    render_svg_to_bytes,
    render_svg_to_file,
    render_template_text,
    render_template_to_file,
)


class FakeBackend:
    """Deterministic render backend for tests."""

    def __init__(self, payload: bytes = b"image") -> None:
        self.payload = payload
        self.calls: list[tuple[str, RenderOptions]] = []

    async def render_html_to_bytes(self, html: str, options: RenderOptions) -> bytes:
        self.calls.append((html, options))
        return self.payload


class ClosableFakeBackend(FakeBackend):
    """Fake backend that records close calls."""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeSvgBackend:
    """Deterministic SVG render backend for tests."""

    def __init__(self, payload: bytes = b"svg-image") -> None:
        self.payload = payload
        self.calls: list[tuple[str, SvgRenderOptions]] = []

    async def render_svg_to_bytes(self, svg: str, options: SvgRenderOptions) -> bytes:
        self.calls.append((svg, options))
        return self.payload


class ClosableFakeSvgBackend(FakeSvgBackend):
    """Fake SVG backend that records close calls."""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FailingCloseFakeSvgBackend(FakeSvgBackend):
    """Fake SVG backend that fails during close."""

    async def close(self) -> None:
        raise RuntimeError("close failed")


@pytest.mark.asyncio
async def test_render_html_to_bytes_uses_injected_backend() -> None:
    backend = FakeBackend(payload=b"png")
    options = RenderOptions(width=320, height=180)

    payload = await render_html_to_bytes("<h1>Hello</h1>", options=options, backend=backend)

    assert payload == b"png"
    assert backend.calls == [("<h1>Hello</h1>", options)]


@pytest.mark.asyncio
async def test_render_svg_to_bytes_uses_injected_backend() -> None:
    backend = FakeSvgBackend(payload=b"png")
    options = SvgRenderOptions(width=320, height=180)

    payload = await render_svg_to_bytes("<svg />", options=options, backend=backend)

    assert payload == b"png"
    assert backend.calls == [("<svg />", options)]


@pytest.mark.asyncio
async def test_default_backend_can_be_configured_and_closed() -> None:
    backend = ClosableFakeBackend()
    configure_default_backend(backend)

    payload = await render_html_to_bytes("<h1>Hello</h1>")
    await close_default_backend()

    assert payload == b"image"
    assert backend.calls[0][0] == "<h1>Hello</h1>"
    assert backend.closed is True


@pytest.mark.asyncio
async def test_default_svg_backend_can_be_configured_and_closed() -> None:
    backend = ClosableFakeSvgBackend()
    configure_default_svg_backend(backend)

    payload = await render_svg_to_bytes("<svg />")
    await close_default_svg_backend()

    assert payload == b"svg-image"
    assert backend.calls[0][0] == "<svg />"
    assert backend.closed is True


@pytest.mark.asyncio
async def test_default_svg_backend_is_cleared_when_close_fails() -> None:
    backend = FailingCloseFakeSvgBackend()
    configure_default_svg_backend(backend)

    with pytest.raises(RuntimeError, match="close failed"):
        await close_default_svg_backend()

    replacement = FakeSvgBackend(payload=b"replacement")
    configure_default_svg_backend(replacement)
    payload = await render_svg_to_bytes("<svg />")
    await close_default_svg_backend()

    assert payload == b"replacement"


@pytest.mark.asyncio
async def test_render_html_to_file_writes_and_reuses_cache(tmp_path: Path) -> None:
    backend = FakeBackend(payload=b"first")
    options = RenderOptions(width=320, height=180)

    first = await render_html_to_file(
        "<main>Hello</main>",
        output_dir=tmp_path,
        options=options,
        backend=backend,
    )
    second = await render_html_to_file(
        "<main>Hello</main>",
        output_dir=tmp_path,
        options=options,
        backend=backend,
    )

    assert first.path.read_bytes() == b"first"
    assert first.path == second.path
    assert first.cached is False
    assert second.cached is True
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_render_svg_to_file_writes_and_reuses_cache(tmp_path: Path) -> None:
    backend = FakeSvgBackend(payload=b"svg")
    options = SvgRenderOptions(width=320, height=180)

    first = await render_svg_to_file(
        "<svg><rect width='10' height='10'/></svg>",
        output_dir=tmp_path,
        options=options,
        backend=backend,
    )
    second = await render_svg_to_file(
        "<svg><rect width='10' height='10'/></svg>",
        output_dir=tmp_path,
        options=options,
        backend=backend,
    )

    assert first.path.read_bytes() == b"svg"
    assert first.path == second.path
    assert first.path.name.startswith("render-svg-")
    assert first.cached is False
    assert second.cached is True
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_render_html_to_file_accepts_explicit_filename(tmp_path: Path) -> None:
    backend = FakeBackend(payload=b"named")

    result = await render_html_to_file(
        "<main>Hello</main>",
        output_dir=tmp_path,
        backend=backend,
        cache=False,
        filename="card.png",
    )

    assert result.path == tmp_path / "card.png"
    assert result.path.read_bytes() == b"named"


@pytest.mark.asyncio
async def test_render_svg_to_file_accepts_explicit_filename(tmp_path: Path) -> None:
    backend = FakeSvgBackend(payload=b"named-svg")

    result = await render_svg_to_file(
        "<svg />",
        output_dir=tmp_path,
        backend=backend,
        cache=False,
        filename="icon.png",
    )

    assert result.path == tmp_path / "icon.png"
    assert result.path.read_bytes() == b"named-svg"


def test_render_template_text_from_raw_template() -> None:
    html = render_template_text("<h1>{{ title }}</h1>", data={"title": "RenderKit"})

    assert html == "<h1>RenderKit</h1>"


def test_render_template_text_from_template_directory(tmp_path: Path) -> None:
    template_path = tmp_path / "card.html.j2"
    template_path.write_text("<p>{{ title }}</p>", encoding="utf-8")

    html = render_template_text(
        "card.html.j2",
        data={"title": "Status"},
        template_dirs=[tmp_path],
    )

    assert html == "<p>Status</p>"


@pytest.mark.asyncio
async def test_render_template_to_file_renders_template_data(tmp_path: Path) -> None:
    backend = FakeBackend(payload=b"template")

    result = await render_template_to_file(
        "<h1>{{ title }}</h1>",
        data={"title": "Card"},
        output_dir=tmp_path,
        backend=backend,
    )

    assert result.path.read_bytes() == b"template"
    assert backend.calls[0][0] == "<h1>Card</h1>"


@pytest.mark.asyncio
async def test_render_svg_template_to_file_renders_template_data(tmp_path: Path) -> None:
    backend = FakeSvgBackend(payload=b"svg-template")

    result = await render_svg_template_to_file(
        "<svg><text>{{ title }}</text></svg>",
        data={"title": "Badge"},
        output_dir=tmp_path,
        backend=backend,
    )

    assert result.path.read_bytes() == b"svg-template"
    assert backend.calls[0][0] == "<svg><text>Badge</text></svg>"


def test_render_options_validate_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="width"):
        RenderOptions(width=0).validate()

    with pytest.raises(ValueError, match="Transparent"):
        RenderOptions(image_format="jpeg", transparent_background=True).validate()


def test_svg_render_options_validate_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="width"):
        SvgRenderOptions(width=0).validate()

    with pytest.raises(ValueError, match="scale"):
        SvgRenderOptions(scale=0).validate()

    with pytest.raises(ValueError, match="scale"):
        SvgRenderOptions(scale=4.1).validate()
