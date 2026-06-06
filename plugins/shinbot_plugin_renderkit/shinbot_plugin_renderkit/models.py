"""Public models for RenderKit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

ImageFormat = Literal["png", "jpeg"]


class RenderBackend(Protocol):
    """Backend capable of turning HTML into image bytes."""

    async def render_html_to_bytes(self, html: str, options: RenderOptions) -> bytes:
        """Render HTML to image bytes."""


class ClosableRenderBackend(RenderBackend, Protocol):
    """Render backend that owns resources and can be closed."""

    async def close(self) -> None:
        """Release backend resources."""


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Options for HTML/CSS image rendering."""

    width: int = 800
    height: int = 480
    image_format: ImageFormat = "png"
    device_scale_factor: float = 1.0
    full_page: bool = False
    selector: str | None = None
    timeout_ms: int = 30_000
    transparent_background: bool = False

    def validate(self) -> None:
        """Validate render options before a backend is invoked."""
        if self.width <= 0:
            raise ValueError("Render width must be positive.")
        if self.height <= 0:
            raise ValueError("Render height must be positive.")
        if self.device_scale_factor <= 0:
            raise ValueError("Device scale factor must be positive.")
        if self.timeout_ms <= 0:
            raise ValueError("Timeout must be positive.")
        if self.image_format not in {"png", "jpeg"}:
            raise ValueError(f"Unsupported image format: {self.image_format}.")
        if self.transparent_background and self.image_format != "png":
            raise ValueError("Transparent background is only supported for PNG.")

    @property
    def suffix(self) -> str:
        """Return the file suffix for this render format."""
        return ".jpg" if self.image_format == "jpeg" else ".png"

    @property
    def mime_type(self) -> str:
        """Return the MIME type for this render format."""
        return "image/jpeg" if self.image_format == "jpeg" else "image/png"


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Result returned by file rendering APIs."""

    path: Path
    mime_type: str
    width: int
    height: int
    cached: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "path": str(self.path),
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "cached": self.cached,
        }
