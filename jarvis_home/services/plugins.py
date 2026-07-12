from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from types import ModuleType
from typing import Any

from ..config import Settings
from ..tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class PluginLoader:
    def __init__(self, settings: Settings, plugin_dir: Path):
        self.settings = settings
        self.plugin_dir = plugin_dir

    def load(self, registry: ToolRegistry, services: dict[str, Any]) -> list[str]:
        if not self.settings.enable_plugins:
            return []
        loaded: list[str] = []
        enabled = self.settings.enabled_plugin_set
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            name = path.stem
            if name not in enabled:
                continue
            module = self._import(path, f"jarvis_plugin_{name}")
            register = getattr(module, "register", None)
            if not callable(register):
                raise RuntimeError(f"Plugin {name} has no register(registry, services) function")
            register(registry, services)
            loaded.append(name)
            logger.info("Loaded plugin %s from %s", name, path)
        return loaded

    @staticmethod
    def _import(path: Path, module_name: str) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            raise RuntimeError(f"Cannot import plugin: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
