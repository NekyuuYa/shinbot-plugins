# RenderKit Design

## Goal

RenderKit is an optional capability plugin that provides image rendering for
other ShinBot plugins. It is a reusable component, not a domain plugin. It should
be useful for games, status cards, leaderboards, receipts, dashboards, and other
visual replies.

## Input Format

RenderKit uses existing web standards:

- HTML for document structure.
- CSS for layout and visual styling.
- Jinja2 for optional server-side templates.

It intentionally does not invent a scene schema. Business plugins own their data
mapping and templates.

## Public Python API

- `render_html_to_file(html, output_dir, ...)`
- `render_template_to_file(template, data, template_dirs, output_dir, ...)`
- `render_html_to_bytes(html, ...)`
- `render_template_to_bytes(template, data, template_dirs, ...)`

All rendering APIs are async because the browser backend is async.

## Backend

The default backend is Playwright/Chromium. It is imported lazily so installing
RenderKit without browser dependencies is still possible. Callers may inject a
custom backend in tests or constrained deployments.

## Caching

File rendering can cache by hashing the normalized render request:

- HTML content
- viewport
- output format
- device scale factor
- selector/full-page mode

If an existing cached file is present, RenderKit returns it without starting the
backend.

## ShinBot Integration

The plugin exposes Python APIs for other plugins. During `setup(plg)`, it also
tries to register a public `render_html_image` tool when ShinBot provides a
`ToolRegistry`. The tool is optional and should not be the primary plugin-to-
plugin integration path.
