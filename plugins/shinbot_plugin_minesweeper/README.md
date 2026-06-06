# ShinBot Minesweeper

Session-scoped chat minesweeper plugin for ShinBot.

## Commands

- `/ms` shows help.
- `/ms start easy`, `/ms start normal`, `/ms start hard`
- `/ms start 12 12 20`, `/ms start 12x12 20`, `/ms start custom 12 12 20`
- `/ms open a1`, `/ms flag b2`, `/ms chord c3`
- `,op a1 b1`, `,flg c3 d4`, `,ch e5`
- `/ms status`, `/ms restart`, `/ms quit`

Coordinates are case-insensitive. Comma shortcuts support multiple cells in one
message and only use the `op`, `flg`, and `ch` verbs.

## Difficulties

- `easy`: 9x9, 10 mines
- `normal`: 16x16, 40 mines
- `hard`: 30x16, 99 mines

Custom boards are bounded by plugin configuration. Defaults are 5-30 width,
5-24 height, and 1-200 mines.
