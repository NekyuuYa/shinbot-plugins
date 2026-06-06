# ShinBot RenderKit

General-purpose rendering utilities for ShinBot plugins.

RenderKit turns standard HTML/CSS, SVG, or Typst into image files that other
plugins can send as `img` message elements. It is not tied to a specific
business domain. A plugin such as minesweeper can generate its own template and
use RenderKit when it is installed, while keeping a text fallback when it is not
installed.

## API

```python
from shinbot_plugin_renderkit import (
    RenderOptions,
    SvgRenderOptions,
    TypstRenderOptions,
    render_html_to_file,
    render_svg_template_to_file,
    render_svg_to_file,
    render_template_to_file,
    render_typst_template_to_file,
    render_typst_to_file,
)

result = await render_html_to_file(
    "<main><h1>Hello</h1></main>",
    output_dir=plg.data_dir / "renders",
    options=RenderOptions(width=800, height=480),
)

result = await render_template_to_file(
    "card.html.j2",
    data={"title": "Status"},
    template_dirs=[plg.data_dir / "templates"],
    output_dir=plg.data_dir / "renders",
)

result = await render_svg_to_file(
    '<svg viewBox="0 0 160 90"><text x="12" y="48">Hello</text></svg>',
    output_dir=plg.data_dir / "renders",
    options=SvgRenderOptions(width=320, height=180),
)

result = await render_svg_template_to_file(
    "badge.svg.j2",
    data={"label": "Ready"},
    template_dirs=[plg.data_dir / "templates"],
    output_dir=plg.data_dir / "renders",
)

result = await render_typst_to_file(
    '#set page(width: 200pt, height: 80pt, margin: 8pt)\n= Hello',
    output_dir=plg.data_dir / "renders",
    options=TypstRenderOptions(ppi=144),
)

result = await render_typst_template_to_file(
    "badge.typ.j2",
    data={"label": "Ready"},
    template_dirs=[plg.data_dir / "templates"],
    output_dir=plg.data_dir / "renders",
)
```

The default HTML backend uses Playwright/Chromium and is loaded lazily. The
default SVG backend uses CairoSVG and is also loaded lazily. Tests and callers
can inject backend objects for deterministic rendering. Typst rendering uses the
standard `typst` CLI and writes PNG output.

## Scope

RenderKit accepts existing standards: HTML, CSS, SVG, Typst, and Jinja2
templates. It does not define a custom scene format and does not understand
plugin-specific concepts such as game boards, mines, score tables, or alerts.
