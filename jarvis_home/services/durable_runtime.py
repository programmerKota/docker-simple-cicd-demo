from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .durable_actions import DurableActionService

if TYPE_CHECKING:
    from ..application import Application

_ATTRIBUTE = "_durable_action_service"


def get_durable_actions(application: Application) -> DurableActionService:
    existing = getattr(application, _ATTRIBUTE, None)
    if existing is not None:
        return cast(DurableActionService, existing)
    service = DurableActionService(application)
    setattr(application, _ATTRIBUTE, service)
    return service
