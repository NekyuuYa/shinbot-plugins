"""ShinBot plugin: session-scoped chat minesweeper."""

from __future__ import annotations

import sys
import time
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .engine import (
    BoardSpec,
    CellOperationError,
    GameAlreadyEndedError,
    MinesweeperEngine,
)
from .models import GameState, Position
from .parser import (
    DIFFICULTIES,
    THEME_NAMES,
    CustomLimits,
    GameSize,
    ParseError,
    RootCommand,
    ThemeName,
    cell_label,
    parse_root_command,
    parse_shortcut_message,
    shortcut_pattern,
)
from .renderer import (
    RenderContext,
    RenderOptions,
    SvgBoard,
    Theme,
    get_theme,
    render_board,
    render_board_svg,
    render_error,
    render_help,
)
from .store import GameStore, JsonGameStore, MemoryGameStore

if TYPE_CHECKING:
    from shinbot.core.plugins.context import Plugin

__plugin_name__ = "Minesweeper"
__plugin_description__ = "Session-scoped chat minesweeper game."

_STORE: GameStore[GameState] | None = None
_ENGINE = MinesweeperEngine()


class MinesweeperPluginConfig(BaseModel):
    """Configuration for the minesweeper plugin."""

    default_difficulty: Literal["easy", "normal", "hard"] = "easy"
    default_custom_width: int = Field(default=12, ge=5, le=60)
    default_custom_height: int = Field(default=12, ge=5, le=40)
    default_custom_mines: int = Field(default=20, ge=1, le=999)
    max_width: int = Field(default=30, ge=5, le=60)
    max_height: int = Field(default=24, ge=5, le=40)
    max_mines: int = Field(default=200, ge=1, le=999)
    allow_custom: bool = True
    persist_games: bool = True
    reveal_mines_on_loss: bool = True
    show_coordinates: bool = True
    ascii_symbols: bool = False
    render_mode: Literal["text", "auto", "image"] = "auto"
    theme: ThemeName = "light"
    shortcut_prefix: str = Field(default=",", min_length=1, max_length=8)
    image_scale: float = Field(default=1.0, gt=0, le=4)
    recall_old_boards: bool = True
    keep_recent_board_messages: int = Field(default=2, ge=1, le=5)
    session_idle_ttl_seconds: int = Field(default=86400, ge=60, le=604800)


__plugin_config_class__ = MinesweeperPluginConfig


def setup(plg: Plugin) -> None:
    """Register minesweeper commands and shortcut route."""
    from shinbot.core.dispatch.ingress import RouteDispatchContext
    from shinbot.core.dispatch.routing import RouteCondition, RouteMatchMode, RouteRule

    config = _load_plugin_config(plg.plugin_id)
    store = _build_store(plg, config)
    render_dir = Path(plg.data_dir) / "renders"
    shortcut_prefix = _normalize_shortcut_prefix(config.shortcut_prefix)
    shortcut_matcher = _build_shortcut_matcher(shortcut_prefix)

    @plg.on_command(
        "minesweeper",
        aliases=["ms"],
        description="在当前会话开始或操作扫雷游戏",
        usage=(
            f"/minesweeper start easy | /ms open a1 | "
            f"{shortcut_prefix}op a1 | {shortcut_prefix}flg b2"
        ),
        permission="cmd.minesweeper",
    )
    async def minesweeper_command(ctx: Any, args: str) -> None:
        await _handle_root_command(
            ctx,
            args,
            store=store,
            config=config,
            logger=plg.logger,
            render_dir=render_dir,
        )

    @plg.on_route(
        RouteCondition(
            event_types=frozenset({"message-created"}),
            custom_matcher=shortcut_matcher,
        ),
        rule_id="shinbot_plugin_minesweeper.shortcut",
        priority=80,
        match_mode=RouteMatchMode.NORMAL,
    )
    async def minesweeper_shortcut(context: RouteDispatchContext, _rule: RouteRule) -> None:
        ctx = context.require_message_context()
        if not ctx.has_permission("cmd.minesweeper"):
            await ctx.send("权限不足：需要 cmd.minesweeper")
            return
        await _handle_shortcut(
            ctx,
            store=store,
            config=config,
            logger=plg.logger,
            render_dir=render_dir,
        )

    plg.logger.info("Minesweeper plugin loaded")


def on_disable(_plg: Plugin) -> None:
    """Clear transient store references on plugin disable."""
    global _STORE
    _STORE = None


def _build_shortcut_matcher(shortcut_prefix: str) -> Any:
    pattern = shortcut_pattern(shortcut_prefix)

    def matches_shortcut(_event: Any, message: Any) -> bool:
        text = message.get_text().strip()
        return bool(pattern.match(text))

    return matches_shortcut


async def _handle_root_command(
    ctx: Any,
    args: str,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    game = store.load(ctx.session_id)
    try:
        command = _parse_root(args, game=game, config=config)
    except ParseError as exc:
        await ctx.send(render_error(str(exc)))
        return

    if command.action == "help":
        await ctx.send(render_help())
        return
    if command.action == "start":
        await _start_game(
            ctx,
            command,
            store=store,
            config=config,
            logger=logger,
            render_dir=render_dir,
        )
        return
    if command.action == "restart":
        await _restart_game(
            ctx,
            command,
            game,
            store=store,
            config=config,
            logger=logger,
            render_dir=render_dir,
        )
        return
    if command.action == "status":
        await _send_status(
            ctx,
            game,
            store=store,
            config=config,
            logger=logger,
            render_dir=render_dir,
        )
        return
    if command.action == "theme":
        await _handle_theme(
            ctx,
            command,
            game,
            store=store,
            config=config,
            logger=logger,
            render_dir=render_dir,
        )
        return
    if command.action == "quit":
        await _quit_game(
            ctx,
            game,
            store=store,
            config=config,
            logger=logger,
            render_dir=render_dir,
        )
        return

    await _apply_operation(
        ctx,
        command,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _handle_shortcut(
    ctx: Any,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    game = store.load(ctx.session_id)
    if game is None or game.status != "active":
        await ctx.send("当前会话没有进行中的扫雷。使用 /ms start easy 开始。")
        return

    try:
        command = parse_shortcut_message(
            ctx.text,
            shortcut_prefix=_normalize_shortcut_prefix(config.shortcut_prefix),
            board_width=game.board.width,
            board_height=game.board.height,
        )
    except ParseError as exc:
        await ctx.send(render_error(str(exc)))
        return
    if command is None:
        return

    root = RootCommand(action=command.action, cells=command.cells)
    await _apply_operation(
        ctx,
        root,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _start_game(
    ctx: Any,
    command: RootCommand,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    existing = store.load(ctx.session_id)
    if existing is not None and existing.status == "active":
        await ctx.send("当前会话已有进行中的扫雷。使用 /ms status 查看，或 /ms restart 重开。")
        return
    size = command.size or _default_size(config)
    try:
        game = _create_game(ctx, size, config=config)
    except ParseError as exc:
        await ctx.send(render_error(str(exc)))
        return
    if existing is not None and existing.theme:
        game.theme = existing.theme
    store.save(game)
    await _send_board(
        ctx,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _restart_game(
    ctx: Any,
    command: RootCommand,
    game: GameState | None,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    size = command.size or _default_size(config)
    if size.kind == "current":
        if game is None:
            await ctx.send("当前会话没有进行中的扫雷。使用 /ms start easy 开始。")
            return
        size = _size_from_existing_game(game)
    try:
        new_game = _create_game(ctx, size, config=config)
    except ParseError as exc:
        await ctx.send(render_error(str(exc)))
        return
    if game is not None:
        new_game.board_message_ids = list(game.board_message_ids)
        new_game.theme = game.theme or config.theme
    store.save(new_game)
    await _send_board(
        ctx,
        new_game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _send_status(
    ctx: Any,
    game: GameState | None,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    if game is None:
        await ctx.send("当前会话没有进行中的扫雷。使用 /ms start easy 开始。")
        return
    await _send_board(
        ctx,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
        track_board=False,
    )


async def _handle_theme(
    ctx: Any,
    command: RootCommand,
    game: GameState | None,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    if command.theme is None:
        await ctx.send(_render_theme_status(game, config=config))
        return

    if game is None:
        await ctx.send(
            "当前会话没有扫雷记录。使用 /ms start easy 开始后再切换主题。"
        )
        return

    game.theme = command.theme
    game.updated_at = time.time()
    store.save(game)
    await ctx.send(f"已切换扫雷主题：{command.theme}")
    await _send_board(
        ctx,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _quit_game(
    ctx: Any,
    game: GameState | None,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    if game is None:
        await ctx.send("当前会话没有进行中的扫雷。使用 /ms start easy 开始。")
        return
    try:
        _ENGINE.quit_game(game)
    except GameAlreadyEndedError:
        pass
    game.updated_at = time.time()
    game.last_action = "结束本局"
    store.save(game)
    await _send_board(
        ctx,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _apply_operation(
    ctx: Any,
    command: RootCommand,
    game: GameState | None,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
) -> None:
    if game is None:
        await ctx.send("当前会话没有进行中的扫雷。使用 /ms start easy 开始。")
        return
    if game.status != "active":
        await ctx.send("本局已经结束。使用 /ms restart 重开。")
        return

    positions = [Position(cell.x, cell.y) for cell in command.cells]
    labels = " ".join(cell.label.lower() for cell in command.cells)
    try:
        if command.action == "open":
            result = _ENGINE.open_many(game, positions)
            game.last_action = f"打开 {labels}"
        elif command.action == "flag":
            result = _ENGINE.toggle_flags(game, positions)
            game.last_action = f"标记 {labels}"
        elif command.action == "chord":
            result = _ENGINE.chord_many(game, positions)
            game.last_action = f"连开 {labels}"
        else:
            await ctx.send(render_help())
            return
    except (CellOperationError, GameAlreadyEndedError, ValueError) as exc:
        await ctx.send(render_error(_translate_engine_error(str(exc))))
        return

    if result.status == "lost":
        exploded = _exploded_cell(game)
        game.last_action = f"踩雷 {cell_label(*exploded).lower()}" if exploded else "踩雷"
    elif result.status == "won":
        game.last_action = "胜利"

    store.save(game)
    await _send_board(
        ctx,
        game,
        store=store,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )


async def _send_board(
    ctx: Any,
    game: GameState,
    *,
    store: GameStore[GameState],
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None = None,
    track_board: bool = True,
) -> None:
    content = await _render_game_message(
        game,
        config=config,
        logger=logger,
        render_dir=render_dir,
    )
    try:
        handle = await ctx.send(content)
    except Exception as exc:
        if not _is_image_message(content):
            raise
        logger.debug("Minesweeper image send failed, falling back to text: %s", exc)
        handle = await ctx.send(_render_game_board(game, config=config))
    message_id = getattr(handle, "message_id", None)
    if track_board and message_id is not None and str(message_id):
        game.board_message_ids.append(str(message_id))
    if track_board:
        await _recall_old_boards(ctx, game, config=config, logger=logger)
        store.save(game)


def _is_image_message(content: object) -> bool:
    if not isinstance(content, list):
        return False
    return any(
        getattr(element, "type", None) == "img"
        or (isinstance(element, dict) and element.get("type") == "img")
        for element in content
    )


async def _render_game_message(
    game: GameState,
    *,
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None,
    theme: Theme | None = None,
) -> object:
    image = await _try_render_game_image(
        game,
        config=config,
        logger=logger,
        render_dir=render_dir,
        theme=theme,
    )
    if image is not None:
        return image
    return _render_game_board(game, config=config)


async def _try_render_game_image(
    game: GameState,
    *,
    config: MinesweeperPluginConfig,
    logger: Any,
    render_dir: Path | None,
    theme: Theme | None = None,
) -> list[Any] | None:
    if config.render_mode == "text" or render_dir is None:
        return None
    try:
        from shinbot.schema.elements import MessageElement
        from shinbot_plugin_renderkit import (
            SvgRenderOptions,
            probe_renderkit_capabilities,
            render_svg_template_to_file,
        )
    except ImportError as exc:
        logger.debug("Minesweeper image rendering unavailable: %s", exc)
        return None

    try:
        if not probe_renderkit_capabilities().svg:
            logger.debug("Minesweeper image rendering skipped: SVG backend unavailable")
            return None
        svg = _render_game_board_svg(game, config=config, theme=theme)
        result = await render_svg_template_to_file(
            svg.template,
            data=svg.data,
            template_dirs=svg.template_dirs,
            output_dir=render_dir,
            options=SvgRenderOptions(
                width=svg.width,
                height=svg.height,
                scale=config.image_scale,
            ),
            cache=True,
        )
        return [
            MessageElement.img(
                str(result.path),
                alt="扫雷棋盘",
                width=result.width,
                height=result.height,
            )
        ]
    except Exception as exc:
        logger.debug("Minesweeper image rendering failed: %s", exc)
        return None


def _render_game_board(game: GameState, *, config: MinesweeperPluginConfig) -> str:
    context = RenderContext(
        difficulty=game.difficulty,
        status=game.status,
        moves=game.moves,
        last_action=game.last_action or None,
        exploded_cell=_exploded_cell(game),
    )
    options = RenderOptions(
        ascii=config.ascii_symbols,
        show_coordinates=config.show_coordinates,
        shortcut_prefix=_normalize_shortcut_prefix(config.shortcut_prefix),
        reveal_mines_on_loss=config.reveal_mines_on_loss,
    )
    return render_board(game.board, context=context, options=options)


def _render_game_board_svg(
    game: GameState,
    *,
    config: MinesweeperPluginConfig,
    theme: Theme | None = None,
) -> SvgBoard:
    context = RenderContext(
        difficulty=game.difficulty,
        status=game.status,
        moves=game.moves,
        last_action=game.last_action or None,
        exploded_cell=_exploded_cell(game),
    )
    options = RenderOptions(
        ascii=config.ascii_symbols,
        show_coordinates=config.show_coordinates,
        include_hints=False,
        reveal_mines_on_loss=config.reveal_mines_on_loss,
    )
    return render_board_svg(
        game.board,
        context=context,
        options=options,
        theme=theme or get_theme(game.theme or config.theme),
    )


async def _recall_old_boards(
    ctx: Any,
    game: GameState,
    *,
    config: MinesweeperPluginConfig,
    logger: Any,
) -> None:
    if not config.recall_old_boards:
        return
    keep = config.keep_recent_board_messages
    if len(game.board_message_ids) <= keep:
        return
    old_ids = game.board_message_ids[:-keep]
    game.board_message_ids = game.board_message_ids[-keep:]
    for message_id in old_ids:
        try:
            await ctx.delete_msg(message_id)
        except Exception as exc:
            logger.debug("Minesweeper board recall failed for %s: %s", message_id, exc)


def _parse_root(
    args: str,
    *,
    game: GameState | None,
    config: MinesweeperPluginConfig,
) -> RootCommand:
    if game is None:
        return parse_root_command(
            args,
            default_difficulty=config.default_difficulty,
            limits=_limits(config),
        )
    return parse_root_command(
        args,
        default_difficulty=config.default_difficulty,
        limits=_limits(config),
        board_width=game.board.width,
        board_height=game.board.height,
    )


def _create_game(ctx: Any, size: GameSize, *, config: MinesweeperPluginConfig) -> GameState:
    spec = _spec_from_size(size, config=config)
    game = _ENGINE.create_game(
        session_id=ctx.session_id,
        spec=spec,
        owner_user_id=ctx.user_id or None,
    )
    game.theme = config.theme
    return game


def _render_theme_status(
    game: GameState | None,
    *,
    config: MinesweeperPluginConfig,
) -> str:
    current = game.theme if game is not None and game.theme else config.theme
    choices = "、".join(THEME_NAMES)
    return f"当前扫雷主题：{current}。可选主题：{choices}。用法：/ms theme dark"


def _spec_from_size(size: GameSize, *, config: MinesweeperPluginConfig) -> BoardSpec:
    if size.kind == "custom" and not config.allow_custom:
        raise ParseError("当前配置不允许自定义棋盘。")
    width = size.width if size.width is not None else config.default_custom_width
    height = size.height if size.height is not None else config.default_custom_height
    mines = size.mines if size.mines is not None else config.default_custom_mines
    _validate_size_limits(width=width, height=height, mines=mines, config=config)
    return BoardSpec(
        width=width,
        height=height,
        mines=mines,
        difficulty=size.difficulty or "custom",
    )


def _size_from_existing_game(game: GameState) -> GameSize:
    if game.difficulty in DIFFICULTIES:
        width, height, mines = DIFFICULTIES[game.difficulty]
        if (game.board.width, game.board.height, game.board.mine_count) == (
            width,
            height,
            mines,
        ):
            return GameSize(
                kind="difficulty",
                difficulty=game.difficulty,
                width=width,
                height=height,
                mines=mines,
            )
    return GameSize(
        kind="custom",
        width=game.board.width,
        height=game.board.height,
        mines=game.board.mine_count,
    )


def _default_size(config: MinesweeperPluginConfig) -> GameSize:
    width, height, mines = DIFFICULTIES[config.default_difficulty]
    return GameSize(
        kind="difficulty",
        difficulty=config.default_difficulty,
        width=width,
        height=height,
        mines=mines,
    )


def _limits(config: MinesweeperPluginConfig) -> CustomLimits:
    return CustomLimits(
        max_width=config.max_width,
        max_height=config.max_height,
        max_mines=config.max_mines,
    )


def _normalize_shortcut_prefix(value: str) -> str:
    prefix = value.strip()
    if not prefix or any(character.isspace() for character in prefix):
        return ","
    return prefix


def _validate_size_limits(
    *,
    width: int,
    height: int,
    mines: int,
    config: MinesweeperPluginConfig,
) -> None:
    limits = _limits(config)
    if width < limits.min_width or width > limits.max_width:
        raise ParseError(f"宽度必须在 {limits.min_width}-{limits.max_width} 之间。")
    if height < limits.min_height or height > limits.max_height:
        raise ParseError(f"高度必须在 {limits.min_height}-{limits.max_height} 之间。")
    if mines < limits.min_mines or mines > limits.max_mines:
        raise ParseError(f"雷数必须在 {limits.min_mines}-{limits.max_mines} 之间。")
    if mines >= width * height:
        raise ParseError("雷数必须小于格子总数。")


def _exploded_cell(game: GameState) -> tuple[int, int] | None:
    for y in range(game.board.height):
        for x in range(game.board.width):
            if game.board.cell_at(Position(x, y)).exploded:
                return (x, y)
    return None


def _translate_engine_error(message: str) -> str:
    translations = {
        "Cannot flag a revealed cell.": "不能标记已经打开的格子。",
        "Cannot open a flagged cell.": "不能打开已标记的格子。",
        "Can only chord a revealed cell.": "只能对已打开的数字格连开。",
        "Can only chord a numbered cell.": "只能对数字格连开。",
        "Game has already ended.": "本局已经结束。使用 /ms restart 重开。",
    }
    return translations.get(message, message)


def _build_store(plg: Plugin, config: MinesweeperPluginConfig) -> GameStore[GameState]:
    global _STORE
    if config.persist_games:
        _STORE = JsonGameStore(
            plg.data_dir / "games",
            serialize=lambda game: game.to_dict(),
            deserialize=GameState.from_dict,
            updated_at=lambda game: game.updated_at,
        )
    else:
        _STORE = MemoryGameStore(updated_at=lambda game: game.updated_at)
    _STORE.cleanup_expired(time.time(), config.session_idle_ttl_seconds)
    return _STORE


def _resolve_config_path(argv: Sequence[str] | None = None) -> Path:
    from shinbot.core.application.paths import DEFAULT_CONFIG_PATH

    args = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(args):
        if value == "--config" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--config="):
            return Path(value.split("=", 1)[1])
    return DEFAULT_CONFIG_PATH


def _load_plugin_config(plugin_id: str) -> MinesweeperPluginConfig:
    from shinbot.core.plugins.config import plugin_config_block

    path = _resolve_config_path()
    raw: dict[str, Any] = {}
    try:
        if path.exists():
            with path.open("rb") as file_obj:
                payload = tomllib.load(file_obj)
            raw = plugin_config_block(payload, plugin_id)
    except Exception:
        raw = {}
    try:
        return MinesweeperPluginConfig.model_validate(raw)
    except ValidationError:
        return MinesweeperPluginConfig()
