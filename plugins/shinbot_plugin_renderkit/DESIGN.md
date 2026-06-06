# RenderKit Design

## Goal

RenderKit is an optional capability plugin that provides image rendering for
other ShinBot plugins. It is a reusable component, not a domain plugin. It should
be useful for games, status cards, leaderboards, receipts, dashboards, and other
visual replies.

## Input Format

RenderKit uses existing standards:

- HTML for document structure.
- CSS for layout and visual styling.
- SVG for compact vector scenes and fast rasterization.
- Typst for document-style cards and precise page layout.
- Jinja2 for optional server-side templates.

It intentionally does not invent a scene schema. Business plugins own their data
mapping and templates.

## Public Python API

- `render_html_to_file(html, output_dir, ...)`
- `render_template_to_file(template, data, template_dirs, output_dir, ...)`
- `render_html_to_bytes(html, ...)`
- `render_template_to_bytes(template, data, template_dirs, ...)`
- `render_svg_to_file(svg, output_dir, ...)`
- `render_svg_template_to_file(template, data, template_dirs, output_dir, ...)`
- `render_svg_to_bytes(svg, ...)`
- `render_svg_template_to_bytes(template, data, template_dirs, ...)`
- `render_typst_to_file(source, output_dir, ...)`
- `render_typst_template_to_file(template, data, template_dirs, output_dir, ...)`
- `render_typst_to_bytes(source, ...)`
- `render_typst_template_to_bytes(template, data, template_dirs, ...)`

All rendering APIs are async. HTML rendering uses an async browser backend. SVG
rendering is run in a worker thread so callers can use the same async API shape.
Typst rendering shells out to the standard Typst CLI through an async subprocess.

## Backend

The default HTML backend is Playwright/Chromium. It is imported lazily so
installing RenderKit without browser dependencies is still possible.

The default SVG backend is CairoSVG. It is also imported lazily and is available
through the optional `svg` extra. Callers may inject custom backends in tests or
constrained deployments.

The default Typst backend is the `typst` CLI. It is configured lazily and callers
may override the executable path through plugin config.

RenderKit exposes a shallow capability probe for backend availability. It checks
optional Python dependencies and configured executable visibility without
launching Chromium or compiling a document.

## Caching

File rendering can cache by hashing the normalized render request:

- HTML content
- viewport
- output format
- device scale factor
- selector/full-page mode
- SVG output size
- SVG scale/background/safety options
- Typst source
- Typst page/PPI/root/font/package/input options

If an existing cached file is present, RenderKit returns it without starting the
backend.

## ShinBot Integration

The plugin exposes Python APIs for other plugins. During `setup(plg)`, it also
tries to register public `render_html_image`, `render_svg_image`, and
`render_typst_image` tools when ShinBot provides a `ToolRegistry` and the
corresponding backend is available. The global `tool_enabled` setting disables
all tool registration. Backend-specific settings can disable only the HTML, SVG,
or Typst tool. The tools are optional and should not be the primary
plugin-to-plugin integration path.
