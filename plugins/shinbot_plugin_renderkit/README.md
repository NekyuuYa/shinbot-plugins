# ShinBot RenderKit

General-purpose rendering utilities for ShinBot plugins.

RenderKit turns standard HTML/CSS into image files that other plugins can send as
`img` message elements. It is not tied to a specific business domain. A plugin
such as minesweeper can generate its own HTML template and use RenderKit when it
is installed, while keeping a text fallback when it is not installed.

## API

```python
from shinbot_plugin_renderkit import render_html_to_file, render_template_to_file

result = await render_html_to_file(
    "<main><h1>Hello</h1></main>",
    output_dir=plg.data_dir / "renders",
    viewport=(800, 480),
)

result = await render_template_to_file(
    "card.html.j2",
    data={"title": "Status"},
    template_dirs=[plg.data_dir / "templates"],
    output_dir=plg.data_dir / "renders",
)
```

The default backend uses Playwright/Chromium and is loaded lazily. Tests and
callers can inject a backend object for deterministic rendering.

## Scope

RenderKit accepts existing standards: HTML and CSS. It does not define a custom
scene format and does not understand plugin-specific concepts such as game
boards, mines, score tables, or alerts.
