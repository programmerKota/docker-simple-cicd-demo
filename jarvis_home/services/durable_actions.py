from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dbos import DBOS, SetWorkflowID
from fastapi import FastAPI

from ..schemas import ToolInvocation, ToolResult, UserContext
from .event_runtime import get_event_outbox

if TYPE_CHECKING:
    from ..application import Application

_runtime: Application | None = None


@dataclass(frozen=True)
class LightAction:
    entity_id: str
    service: str
    desired_state: str
    brightness_pct: int | None


def configure_runtime(application: Application) -> None:
    global _runtime
    _runtime = application


def get_runtime() -> Application:
    if _runtime is None:
        raise RuntimeError("Durable action runtime has not been configured")
    return _runtime


def parse_light_action(invocation: ToolInvocation) -> LightAction | None:
    if invocation.tool_name != "home.call_service":
        return None
    arguments = invocation.arguments
    if arguments.get("domain") != "light":
        raise ValueError("Durable home execution currently supports only the light domain")
    service = str(arguments.get("service", ""))
    if service not in {"turn_on", "turn_off"}:
        raise ValueError("Only idempotent light turn_on and turn_off services are supported")
    target = arguments.get("target")
    if not isinstance(target, dict):
        raise ValueError("A single Home Assistant entity target is required")
    entity_id = target.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id.startswith("light.") or "," in entity_id:
        raise ValueError("A single valid light entity_id is required")
    service_data = arguments.get("service_data") or {}
    if not isinstance(service_data, dict):
        raise ValueError("service_data must be an object")
    allowed_fields = {"brightness_pct"}
    unknown_fields = set(service_data) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Unsupported light service fields: {sorted(unknown_fields)}")
    brightness = service_data.get("brightness_pct")
    if brightness is not None:
        if service != "turn_on" or not isinstance(brightness, int) or isinstance(brightness, bool):
            raise ValueError("brightness_pct is valid only as an integer with turn_on")
        if not 1 <= brightness <= 100:
            raise ValueError("brightness_pct must be between 1 and 100")
    return LightAction(
        entity_id=entity_id,
        service=service,
        desired_state="on" if service == "turn_on" else "off",
        brightness_pct=brightness,
    )


@DBOS.step(retries_allowed=True, interval_seconds=0.25, max_attempts=5, backoff_rate=2.0)
async def record_outbox_event_step(
    event_id: str,
    subject: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    inserted = get_event_outbox(get_runtime()).append(event_id, subject, payload)
    return {"event_id": event_id, "inserted": inserted}


@DBOS.step(retries_allowed=True, interval_seconds=1.0, max_attempts=3, backoff_rate=2.0)
async def apply_light_action_step(
    actor: str,
    entity_id: str,
    service: str,
    brightness_pct: int | None,
) -> dict[str, Any]:
    application = get_runtime()
    service_data: dict[str, Any] = {}
    if brightness_pct is not None:
        service_data["brightness_pct"] = brightness_pct
    result = await application.registry.invoke(
        ToolInvocation(
            tool_name="home.call_service",
            arguments={
                "domain": "light",
                "service": service,
                "service_data": service_data,
                "target": {"entity_id": entity_id},
            },
        ),
        UserContext(username=actor, role="owner", source="dbos-workflow"),
        bypass_policy=True,
    )
    if not result.ok:
        raise RuntimeError(result.error or "Home Assistant light action failed")
    return result.model_dump(mode="json")


@DBOS.step(retries_allowed=True, interval_seconds=1.0, max_attempts=2, backoff_rate=2.0)
async def verify_light_state_step(
    entity_id: str,
    desired_state: str,
    attempts: int,
    interval_seconds: float,
) -> dict[str, Any]:
    application = get_runtime()
    last_state: dict[str, Any] | None = None
    for _ in range(attempts):
        last_state = await application.get_home_assistant_client().get_state(entity_id)
        if last_state.get("state") == desired_state:
            return {
                "verified": True,
                "entity_id": entity_id,
                "desired_state": desired_state,
                "observed": last_state,
            }
        await asyncio.sleep(interval_seconds)
    observed = last_state.get("state") if last_state else "unknown"
    raise RuntimeError(
        f"State witness failed for {entity_id}: expected {desired_state}, observed {observed}"
    )


@DBOS.workflow(name="jarvis_home.execute_light_action.v1", max_recovery_attempts=10)
async def execute_light_action_workflow(
    approval_id: str,
    actor: str,
    entity_id: str,
    service: str,
    desired_state: str,
    brightness_pct: int | None,
    witness_attempts: int,
    witness_interval_seconds: float,
) -> dict[str, Any]:
    workflow_id = DBOS.workflow_id
    base_event = {
        "schema_version": 1,
        "approval_id": approval_id,
        "workflow_id": workflow_id,
        "actor": actor,
        "entity_id": entity_id,
        "service": service,
        "desired_state": desired_state,
        "brightness_pct": brightness_pct,
    }
    await record_outbox_event_step(
        f"approval:{approval_id}:authorized",
        "home.plan.authorized.v1",
        base_event,
    )
    try:
        action_result = await apply_light_action_step(actor, entity_id, service, brightness_pct)
        witness = await verify_light_state_step(
            entity_id,
            desired_state,
            witness_attempts,
            witness_interval_seconds,
        )
        await record_outbox_event_step(
            f"approval:{approval_id}:completed",
            "home.action.completed.v1",
            {**base_event, "state_witness": witness},
        )
        return ToolResult(
            ok=True,
            content={
                "approval_id": approval_id,
                "workflow_id": workflow_id,
                "action": action_result,
                "state_witness": witness,
            },
            metadata={"durable": True, "state_verified": True},
        ).model_dump(mode="json")
    except Exception as exc:
        await record_outbox_event_step(
            f"approval:{approval_id}:failed",
            "home.action.failed.v1",
            {**base_event, "error": str(exc)},
        )
        raise


class DurableActionService:
    def __init__(self, application: Application):
        self.application = application
        self.dbos: DBOS | None = None
        configure_runtime(application)

    @property
    def enabled(self) -> bool:
        return self.application.settings.durable_workflows_enabled

    def attach_fastapi(self, app: FastAPI) -> None:
        if not self.enabled:
            return
        self.dbos = DBOS(
            fastapi=app,
            config={
                "name": "jarvis-home",
                "system_database_url": self.application.settings.dbos_database_url,
                "application_version": "jarvis-home-light-actions-v1",
                "run_admin_server": False,
                "log_level": self.application.settings.log_level,
            },
        )

    async def execute_approved(
        self,
        approval_id: str,
        invocation: ToolInvocation,
        user: UserContext,
    ) -> ToolResult:
        try:
            action = parse_light_action(invocation)
        except ValueError as exc:
            if invocation.tool_name == "home.call_service" and self.enabled:
                return ToolResult(ok=False, error=str(exc), metadata={"durable": True, "denied": True})
            raise

        if action is None or not self.enabled:
            result = await self.application.registry.invoke(invocation, user, bypass_policy=True)
            result.metadata["durable"] = False
            return result

        workflow_id = f"approval:{approval_id}"
        try:
            with SetWorkflowID(workflow_id):
                handle = await DBOS.start_workflow_async(
                    execute_light_action_workflow,
                    approval_id,
                    user.username,
                    action.entity_id,
                    action.service,
                    action.desired_state,
                    action.brightness_pct,
                    self.application.settings.state_witness_attempts,
                    self.application.settings.state_witness_interval_seconds,
                )
            payload = await handle.get_result()
            result = ToolResult.model_validate(payload)
            result.metadata["workflow_id"] = workflow_id
            return result
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=str(exc),
                metadata={"durable": True, "workflow_id": workflow_id, "state_verified": False},
            )

    async def recover_approved_without_result(self) -> int:
        if not self.enabled:
            return 0
        recovered = 0
        for approval_id, username, invocation in self.application.approvals.list_approved_without_result():
            result = await self.execute_approved(
                approval_id,
                invocation,
                UserContext(username=username, role="owner", source="approval-recovery"),
            )
            self.application.approvals.store_result(approval_id, result.model_dump(mode="json"))
            self.application.audit.record(
                "system",
                "approval.recover",
                approval_id,
                "success" if result.ok else "error",
                {"tool": invocation.tool_name, "workflow": result.metadata.get("workflow_id")},
            )
            recovered += 1
        return recovered
