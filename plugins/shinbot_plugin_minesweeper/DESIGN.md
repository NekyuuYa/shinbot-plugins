# ShinBot Minesweeper Design

## Rendering

The plugin can render either an image board or a compact plain-text board. The
default `render_mode` is `auto`: it sends an image when the optional RenderKit
plugin and its SVG backend are available, and otherwise falls back to the
plain-text board so the game still works on every ShinBot adapter without image
upload support. The text renderer uses Unicode symbols, with an ASCII fallback
controlled by config.

When `render_mode` is `auto` (default) or `image`, the plugin uses the optional
RenderKit plugin to render a standard SVG board into a PNG image and send it as
an `img` message element. This is a best-effort path: if RenderKit is not
installed, its SVG backend is unavailable, or rendering fails, the plugin falls
back to the plain-text board. Setting `render_mode` to `text` forces text
output and skips the RenderKit code path entirely. The SVG generation stays inside the minesweeper
plugin because it owns game-specific board semantics; RenderKit only provides
generic image rasterization.

Each board reply includes game status, difficulty, board size, mine count,
remaining flags, move count, last action, coordinates, and a fixed-width grid.
On loss, mines can be revealed by config. The latest board replies can be kept
while older board messages are recalled best-effort when the adapter supports
message deletion.

## Controls

The root command is `/minesweeper`, with `/ms` as the short alias. There is no
`/mine` alias. Bare `/ms` returns help.

Common cell operations can use comma shortcuts:

- `,op a1 b1` opens one or more cells.
- `,flg c3 d4` toggles flags on one or more cells.
- `,ch e5` chords one or more revealed numbered cells.

Coordinates are case-insensitive, so `a1` and `A1` are equivalent.

## Start Parameters

Named difficulties:

- `easy`: 9x9 with 10 mines
- `normal`: 16x16 with 40 mines
- `hard`: 30x16 with 99 mines

Custom starts:

- `/ms start 12 12 20`
- `/ms start 12x12 20`
- `/ms start custom 12 12 20`

Custom sizes are bounded by plugin config. Defaults are width 5-30, height 5-24,
and mines 1-200. Mine count must be lower than the number of cells.

## Generator

Mines are seeded lazily on the first open. The first opened cell is always safe.
The generator first excludes the first cell and all neighboring cells; if the
board is too dense for that exclusion, it falls back to excluding only the first
cell. Adjacent counts are computed after mine placement.

## Persistence

Games are keyed by ShinBot session id. The default store writes JSON files under
the plugin data directory, with a memory-only mode available through config.
