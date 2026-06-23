"""loader.py — stub injection and AstrBot plugin loading."""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot._registry import HandlerMeta

logger = logging.getLogger(__name__)

_STUB_INJECTED = False


def inject_stub() -> None:
    """Prepend the compat plugin root to sys.path so Python finds our 'astrbot' package.

    Called once at setup time.  The stub shadows any real astrbot installation
    because we prepend rather than append.
    """
    global _STUB_INJECTED
    if _STUB_INJECTED:
        return

    stub_parent = str(Path(__file__).parent)
    if stub_parent not in sys.path:
        sys.path.insert(0, stub_parent)

    # Force the stub package into sys.modules
    import astrbot  # noqa: F401

    _STUB_INJECTED = True
    logger.debug("astrbot stub injected from %s", stub_parent)


@dataclass
class LoadedCompatPlugin:
    """A loaded AstrBot-compatible plugin."""

    star_cls: type
    handlers: list[HandlerMeta]
    module_name: str
    plugin_dir: Path
    instance: Any = field(default=None, init=False)

    async def initialize(self, context: Any) -> None:
        """Create the Star instance and call initialize()."""
        self.instance = self.star_cls(context=context)
        if hasattr(self.instance, "initialize"):
            await self.instance.initialize()
        logger.info("Initialized compat plugin: %s", self.plugin_dir.name)

    async def terminate(self) -> None:
        """Call terminate() on the Star instance."""
        if self.instance is None:
            return
        if hasattr(self.instance, "terminate"):
            try:
                await self.instance.terminate()
            except Exception:
                logger.exception(
                    "Error terminating compat plugin: %s", self.plugin_dir.name
                )
        self.instance = None


def load_compat_plugin(plugin_dir: Path) -> LoadedCompatPlugin | None:
    """Import an AstrBot plugin from *plugin_dir* and return a LoadedCompatPlugin."""
    from astrbot._registry import clear, pending_handlers, pending_stars

    main_file = plugin_dir / "main.py"
    if not main_file.exists():
        logger.warning("astrbot compat: no main.py in %s, skipping", plugin_dir)
        return None

    # Auto-install bridge-level dependencies (e.g. apscheduler)
    _install_bridge_deps()

    # Auto-install requirements.txt if present
    _install_requirements(plugin_dir)

    clear()

    module_name = f"_astrbot_compat_{plugin_dir.name}"

    # Add plugin dir to path so intra-plugin relative imports work
    plugin_path_str = str(plugin_dir)
    inserted = False
    if plugin_path_str not in sys.path:
        sys.path.insert(0, plugin_path_str)
        inserted = True

    try:
        # Remove stale module if reloading
        sys.modules.pop(module_name, None)

        spec = importlib.util.spec_from_file_location(
            module_name, main_file,
            submodule_search_locations=[str(plugin_dir)],
        )
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        # Register as a package so relative imports (from .src...) work
        module.__package__ = module_name
        module.__path__ = [str(plugin_dir)]
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception:
        logger.exception("astrbot compat: failed to import %s", plugin_dir)
        sys.modules.pop(module_name, None)
        return None
    finally:
        if inserted and plugin_path_str in sys.path:
            sys.path.remove(plugin_path_str)

    if not pending_stars:
        logger.warning("astrbot compat: no Star subclass found in %s", plugin_dir)
        return None

    star_cls = pending_stars[0]
    handlers = list(pending_handlers)

    logger.info(
        "Loaded compat plugin %s (%s, %d handler(s))",
        plugin_dir.name,
        star_cls.__name__,
        len(handlers),
    )
    return LoadedCompatPlugin(
        star_cls=star_cls,
        handlers=handlers,
        module_name=module_name,
        plugin_dir=plugin_dir,
    )


def _install_requirements(plugin_dir: Path) -> None:
    """Install packages from requirements.txt if present in the plugin directory."""
    req_file = plugin_dir / "requirements.txt"
    if not req_file.exists():
        return

    deps = [
        line.strip()
        for line in req_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not deps:
        return

    _install_missing_deps(deps, plugin_dir.name)


def _install_bridge_deps() -> None:
    """Install dependencies declared in the bridge plugin's pyproject.toml."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return

    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        deps = data.get("project", {}).get("dependencies", [])
    except Exception:
        return

    if deps:
        _install_missing_deps(deps, "shinbot_converter_astrbot (bridge)")


def _install_missing_deps(deps: list[str], source: str) -> None:
    """Install dependencies that are not already importable."""
    import subprocess

    # Filter out already-importable deps to avoid repeated installs
    missing = []
    for dep in deps:
        pkg = dep.split(">=")[0].split("==")[0].split("<=")[0].split("~=")[0].strip()
        pkg = pkg.replace("-", "_")
        try:
            __import__(pkg)
        except ImportError:
            missing.append(dep)

    if not missing:
        return

    logger.info("astrbot compat: installing %d missing dep(s) for %s", len(missing), source)

    # Prefer uv pip install (works in uv-managed venvs), fall back to pip
    for cmd in [
        ["uv", "pip", "install", "--quiet", *missing],
        [sys.executable, "-m", "pip", "install", "--quiet", *missing],
    ]:
        try:
            subprocess.check_call(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            logger.info("astrbot compat: dependencies installed successfully")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    logger.warning(
        "astrbot compat: failed to install dependencies for %s: "
        "neither uv pip nor pip succeeded",
        source,
    )
