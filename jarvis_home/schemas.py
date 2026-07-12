from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionDecision(StrEnum):
    ALLOW = "allow"
    APPROVAL = "approval"
    DENY = "deny"


class UserContext(BaseModel):
    username: str
    role: str = "owner"
    source: str = "web"


class ToolInvocation(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None


class ToolResult(BaseModel):
    ok: bool
    content: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PendingApproval(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    risk: RiskLevel
    expires_at: str
    conversation_id: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16_000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    approvals: list[PendingApproval] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    degraded: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)
    kind: str = "note"
    importance: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)


class RoutineStep(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    continue_on_error: bool = False


class RoutineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    cron: str | None = None
    enabled: bool = True
    steps: list[RoutineStep] = Field(min_length=1, max_length=50)


class IntegrationSettingsUpdate(BaseModel):
    ollama_url: str | None = None
    ollama_model: str | None = None
    home_assistant_url: str | None = None
    home_assistant_token: str | None = None


class ApprovalDecision(BaseModel):
    approved: bool
