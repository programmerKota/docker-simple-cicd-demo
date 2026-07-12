from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent import JarvisAgent
from .audit import AuditLog
from .config import Settings
from .db import Database
from .integrations.home_assistant import HomeAssistantClient
from .integrations.ollama import OllamaClient
from .integrations.system import FileSandbox, ShellRunner
from .policy import PolicyEngine
from .schemas import RiskLevel, UserContext
from .security import LoginRateLimiter, SecretStore, SecurityManager
from .services.approvals import ApprovalService
from .services.backup import BackupService
from .services.conversations import ConversationService
from .services.events import EventBus
from .services.memory import MemoryService
from .services.plugins import PluginLoader
from .services.routines import RoutineService
from .services.voice import VoiceService
from .tool_registry import ToolDefinition, ToolRegistry

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.initialize()
        self.security = SecurityManager(self.db, settings)
        self.security.bootstrap_admin()
        self.secrets = SecretStore(self.db, settings.master_key_file)
        if settings.home_assistant_token and not self.secrets.get("home_assistant_token"):
            self.secrets.set("home_assistant_token", settings.home_assistant_token)
        self.rate_limiter = LoginRateLimiter()
        self.audit = AuditLog(self.db)
        self.events = EventBus(self.db)
        self.memory = MemoryService(self.db)
        self.conversations = ConversationService(self.db)
        self.approvals = ApprovalService(self.db, settings)
        self.policy = PolicyEngine()
        self.registry = ToolRegistry(self.policy, self.approvals, self.audit, self.events)
        self.sandbox = FileSandbox(settings.workspace_root_list)
        self.shell = ShellRunner(settings, self.sandbox)
        self.backups = BackupService(self.db, settings)
        self.voice = VoiceService(settings)
        self._register_core_tools()
        self.routines = RoutineService(self.db, self.registry, self.events)
        self._register_routine_tools()
        self.loaded_plugins = PluginLoader(settings, Path("./plugins")).load(
            self.registry,
            {
                "db": self.db,
                "settings": self.settings,
                "events": self.events,
                "memory": self.memory,
                "audit": self.audit,
            },
        )
        self.agent = JarvisAgent(
            settings,
            self.get_ollama_client(),
            self.registry,
            self.conversations,
            self.memory,
        )

    def get_ollama_client(self) -> OllamaClient:
        url = self.db.get_setting("ollama_url", self.settings.ollama_url)
        model = self.db.get_setting("ollama_model", self.settings.ollama_model)
        return OllamaClient(str(url), str(model))

    def get_home_assistant_client(self) -> HomeAssistantClient:
        url = self.db.get_setting("home_assistant_url", self.settings.home_assistant_url)
        token = self.secrets.get("home_assistant_token", "")
        return HomeAssistantClient(str(url), token)

    def refresh_agent_clients(self) -> None:
        self.agent.ollama = self.get_ollama_client()

    async def status(self) -> dict[str, Any]:
        ollama = await self.get_ollama_client().health()
        home_assistant = await self.get_home_assistant_client().health()
        audit_ok, broken_at = self.audit.verify_chain()
        return {
            "ok": True,
            "version": "1.0.0",
            "time": datetime.now(UTC).isoformat(),
            "environment": self.settings.env,
            "database": {"ok": self.settings.database_path.exists()},
            "ollama": ollama,
            "home_assistant": home_assistant,
            "audit": {"ok": audit_ok, "broken_at": broken_at},
            "tools": len(self.registry.names()),
            "plugins": self.loaded_plugins,
            "shell_enabled": self.settings.enable_shell,
            "workspace_roots": [str(path) for path in self.settings.workspace_root_list],
        }

    def _register_core_tools(self) -> None:
        async def system_status() -> dict[str, Any]:
            return await self.status()

        async def home_list_entities(domain: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
            states = await self.get_home_assistant_client().list_states(domain)
            return states[: min(max(limit, 1), 300)]

        async def home_get_state(entity_id: str) -> dict[str, Any]:
            return await self.get_home_assistant_client().get_state(entity_id)

        async def home_call_service(
            domain: str,
            service: str,
            service_data: dict[str, Any] | None = None,
            target: dict[str, Any] | None = None,
        ) -> list[dict[str, Any]]:
            return await self.get_home_assistant_client().call_service(domain, service, service_data, target)

        self.registry.register(
            ToolDefinition(
                "system.status",
                "Read JARVIS, Ollama, Home Assistant, database, and audit-chain status.",
                {"type": "object", "properties": {}, "additionalProperties": False},
                RiskLevel.LOW,
                system_status,
            )
        )
        self.registry.register(
            ToolDefinition(
                "memory.search",
                "Search the owner's private long-term memories and notes.",
                {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                self.memory.search,
            )
        )
        self.registry.register(
            ToolDefinition(
                "memory.remember",
                "Store a durable fact, preference, or note explicitly requested by the owner.",
                {
                    "type": "object",
                    "required": ["content"],
                    "properties": {
                        "content": {"type": "string", "maxLength": 50000},
                        "kind": {"type": "string", "default": "note"},
                        "importance": {"type": "integer", "minimum": 1, "maximum": 10},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                self.memory.remember,
            )
        )
        self.registry.register(
            ToolDefinition(
                "home.list_entities",
                "List Home Assistant entities and their current states, optionally by domain.",
                {
                    "type": "object",
                    "properties": {
                        "domain": {"type": ["string", "null"]},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 300},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                home_list_entities,
            )
        )
        self.registry.register(
            ToolDefinition(
                "home.get_state",
                "Read one Home Assistant entity state.",
                {
                    "type": "object",
                    "required": ["entity_id"],
                    "properties": {"entity_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                home_get_state,
            )
        )
        self.registry.register(
            ToolDefinition(
                "home.call_service",
                "Call a Home Assistant service. Physical changes are policy-controlled.",
                {
                    "type": "object",
                    "required": ["domain", "service"],
                    "properties": {
                        "domain": {"type": "string"},
                        "service": {"type": "string"},
                        "service_data": {"type": ["object", "null"]},
                        "target": {"type": ["object", "null"]},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.MEDIUM,
                home_call_service,
            )
        )
        self.registry.register(
            ToolDefinition(
                "filesystem.list",
                "List files inside configured workspace roots.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "default": "."},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                self.sandbox.list_directory,
            )
        )
        self.registry.register(
            ToolDefinition(
                "filesystem.read",
                "Read a UTF-8 text file inside configured workspace roots.",
                {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 500000},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                self.sandbox.read_text,
            )
        )
        self.registry.register(
            ToolDefinition(
                "filesystem.search",
                "Search text files inside configured workspace roots.",
                {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string", "default": "."},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.LOW,
                self.sandbox.search_text,
            )
        )
        self.registry.register(
            ToolDefinition(
                "filesystem.write",
                "Write a text file atomically inside configured workspace roots.",
                {
                    "type": "object",
                    "required": ["path", "content"],
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean", "default": False},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.MEDIUM,
                self.sandbox.write_text,
            )
        )
        self.registry.register(
            ToolDefinition(
                "shell.run",
                "Run one allowlisted command without a shell inside a configured workspace root.",
                {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string", "default": "."},
                        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
                    },
                    "additionalProperties": False,
                },
                RiskLevel.HIGH,
                self.shell.run,
            )
        )
        self.registry.register(
            ToolDefinition(
                "backup.create",
                "Create an atomic encrypted-data backup archive. The master key is not included.",
                {"type": "object", "properties": {}, "additionalProperties": False},
                RiskLevel.LOW,
                self.backups.create,
            )
        )

    def _register_routine_tools(self) -> None:
        async def run_routine(routine_id: str) -> dict[str, Any]:
            return await self.routines.run(
                routine_id,
                UserContext(username="agent", role="owner", source="agent"),
            )

        self.registry.register(
            ToolDefinition(
                "routine.run",
                "Run a saved household routine by its identifier.",
                {
                    "type": "object",
                    "required": ["routine_id"],
                    "properties": {"routine_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                RiskLevel.MEDIUM,
                run_routine,
            )
        )
