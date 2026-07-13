from __future__ import annotations

import re
import secrets
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .application import Application
from .config import Settings, get_settings
from .integrations.home_assistant_ws import HomeAssistantWebSocketClient
from .integrations.opa import OPAClient, PolicyDecision
from .schemas import ToolInvocation, UserContext
from .services.household_twin import HouseholdTwin

_ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_DOMAIN = re.compile(r"^[a-z0-9_]+$")


class PolicyClient(Protocol):
    async def health(self) -> dict[str, Any]: ...

    async def decide(self, policy_input: dict[str, Any]) -> PolicyDecision: ...


class BearerTokenGate:
    """Fail-closed bearer gate for the private MCP transport."""

    def __init__(self, app: ASGIApp, token: str):
        if len(token) < 32:
            raise RuntimeError("JARVIS_MCP_TOKEN must contain at least 32 characters")
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"")
        if not secrets.compare_digest(supplied, self.expected):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class HomeGateway:
    """Narrow household capability surface exposed to an external AI runtime."""

    def __init__(
        self,
        application: Application,
        policy_client: PolicyClient | None = None,
        household_twin: HouseholdTwin | None = None,
    ):
        self.application = application
        self.policy_client = policy_client or OPAClient(application.settings.opa_url)
        home_assistant_url = application.db.get_setting(
            "home_assistant_url", application.settings.home_assistant_url
        )
        home_assistant_token = application.secrets.get("home_assistant_token", "")
        self.household_twin = household_twin or HouseholdTwin(
            application.settings.twin_store_path,
            HomeAssistantWebSocketClient(str(home_assistant_url), home_assistant_token),
            refresh_interval_seconds=application.settings.twin_refresh_interval_seconds,
        )
        self.agent_user = UserContext(
            username=application.settings.admin_username,
            role="agent",
            source="openjarvis-mcp",
        )

    async def status(self) -> dict[str, Any]:
        status = await self.application.status()
        return {
            "gateway": "ready",
            "home_assistant": status["home_assistant"],
            "policy": await self.policy_client.health(),
            "audit": status["audit"],
            "household_twin": self.household_twin.status(),
            "pending_approvals": len(
                self.application.approvals.list_pending(self.application.settings.admin_username)
            ),
        }

    async def observe(
        self,
        entity_id: str = "",
        domain: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        if entity_id:
            normalized_entity = entity_id.strip().lower()
            self._validate_entity_id(normalized_entity)
            result = await self.application.registry.invoke(
                ToolInvocation(tool_name="home.get_state", arguments={"entity_id": normalized_entity}),
                self.agent_user,
            )
            return result.model_dump(mode="json")

        normalized_domain = domain.strip().lower()
        if normalized_domain and not _DOMAIN.fullmatch(normalized_domain):
            raise ValueError("Invalid Home Assistant domain")
        bounded_limit = min(max(int(limit), 1), 100)
        result = await self.application.registry.invoke(
            ToolInvocation(
                tool_name="home.list_entities",
                arguments={"domain": normalized_domain or None, "limit": bounded_limit},
            ),
            self.agent_user,
        )
        return result.model_dump(mode="json")

    async def twin_summary(self) -> dict[str, Any]:
        await self.household_twin.ensure_fresh()
        return self.household_twin.summary()

    async def find_twin_entities(
        self,
        room: str = "",
        domain: str = "",
        state: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        freshness = await self.household_twin.ensure_fresh()
        return {
            "twin": freshness,
            "entities": self.household_twin.find_entities(
                room=room,
                domain=domain,
                state=state,
                limit=limit,
            ),
        }

    async def explain_twin_entity(self, entity_id: str) -> dict[str, Any]:
        normalized_entity = entity_id.strip().lower()
        self._validate_entity_id(normalized_entity)
        await self.household_twin.ensure_fresh()
        try:
            return self.household_twin.explain_entity(normalized_entity)
        except KeyError as exc:
            raise ValueError(f"Entity is not present in the household twin: {normalized_entity}") from exc

    async def propose_light_action(
        self,
        entity_id: str,
        action: Literal["turn_on", "turn_off"],
        brightness_pct: int | None = None,
    ) -> dict[str, Any]:
        """Policy-check and create, but never silently execute, one idempotent light action."""
        normalized_entity = entity_id.strip().lower()
        self._validate_entity_id(normalized_entity)
        if not normalized_entity.startswith("light."):
            raise ValueError("Only light entities are accepted by this first production capability")
        if brightness_pct is not None:
            if action != "turn_on":
                raise ValueError("brightness_pct is valid only with turn_on")
            if not 1 <= brightness_pct <= 100:
                raise ValueError("brightness_pct must be between 1 and 100")

        decision = await self.policy_client.decide(
            {
                "schema_version": 1,
                "actor": {
                    "id": self.agent_user.username,
                    "role": self.agent_user.role,
                    "source": self.agent_user.source,
                },
                "action": {
                    "capability": "home.light.write",
                    "domain": "light",
                    "service": action,
                    "entity_id": normalized_entity,
                    "brightness_pct": brightness_pct,
                },
                "context": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "owner_present": None,
                    "fresh_owner_approval": False,
                    "emergency": False,
                },
            }
        )

        service_data: dict[str, Any] = {}
        if brightness_pct is not None:
            service_data["brightness_pct"] = brightness_pct
        result = await self.application.registry.invoke(
            ToolInvocation(
                tool_name="home.call_service",
                arguments={
                    "domain": "light",
                    "service": action,
                    "service_data": service_data,
                    "target": {"entity_id": normalized_entity},
                },
            ),
            self.agent_user,
        )
        payload = result.model_dump(mode="json")
        payload["policy_decision"] = asdict(decision)
        return payload

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.application.approvals.list_pending(self.application.settings.admin_username)
        ]

    @staticmethod
    def _validate_entity_id(entity_id: str) -> None:
        if not _ENTITY_ID.fullmatch(entity_id):
            raise ValueError("Invalid Home Assistant entity_id")


def build_mcp_app(
    settings: Settings | None = None,
    application: Application | None = None,
    policy_client: PolicyClient | None = None,
    household_twin: HouseholdTwin | None = None,
) -> ASGIApp:
    settings = settings or get_settings()
    application = application or Application(settings)
    gateway = HomeGateway(
        application,
        policy_client=policy_client,
        household_twin=household_twin,
    )
    mcp = FastMCP(
        "JARVIS Home Safety Gateway",
        instructions=(
            "Use the household twin for room/device meaning and reported state. Physical light "
            "changes are idempotent turn_on or turn_off proposals: they pass an external policy "
            "service and create an owner approval request. Never claim execution before a state "
            "witness confirms it."
        ),
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @mcp.tool(name="home_gateway_status")
    async def home_gateway_status() -> dict[str, Any]:
        """Read gateway, integrations, audit, twin freshness, and approval status."""
        return await gateway.status()

    @mcp.tool(name="home_observe")
    async def home_observe(
        entity_id: str = "",
        domain: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Read one entity or a bounded list of raw Home Assistant entity states."""
        return await gateway.observe(entity_id=entity_id, domain=domain, limit=limit)

    @mcp.tool(name="home_twin_summary")
    async def home_twin_summary() -> dict[str, Any]:
        """Summarize the last-known-good semantic model of rooms, devices, and entities."""
        return await gateway.twin_summary()

    @mcp.tool(name="home_find_entities")
    async def home_find_entities(
        room: str = "",
        domain: str = "",
        state: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Find entities by resolved room, exact domain, and exact reported state."""
        return await gateway.find_twin_entities(room, domain, state, limit)

    @mcp.tool(name="home_explain_entity")
    async def home_explain_entity(entity_id: str) -> dict[str, Any]:
        """Explain one entity's room, device, type, availability, and reported state."""
        return await gateway.explain_twin_entity(entity_id)

    @mcp.tool(name="home_propose_light_action")
    async def home_propose_light_action(
        entity_id: str,
        action: Literal["turn_on", "turn_off"],
        brightness_pct: int | None = None,
    ) -> dict[str, Any]:
        """Propose an idempotent light action. Policy and owner approval are mandatory."""
        return await gateway.propose_light_action(entity_id, action, brightness_pct)

    @mcp.tool(name="home_list_pending_approvals")
    def home_list_pending_approvals() -> list[dict[str, Any]]:
        """List physical actions waiting for the owner in JARVIS Home."""
        return gateway.pending_approvals()

    return BearerTokenGate(mcp.streamable_http_app(), settings.mcp_token)


def serve() -> None:
    settings = get_settings()
    uvicorn.run(
        build_mcp_app(settings),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
    )
