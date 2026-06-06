# ShinBot Minesweeper Design

## Rendering

The plugin renders a compact plain-text board so it works on every ShinBot
adapter without image upload support. The default renderer uses Unicode symbols,
with an ASCII fallback controlled by config.

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
