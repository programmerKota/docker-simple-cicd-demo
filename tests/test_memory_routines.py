from __future__ import annotations

import pytest

from jarvis_home.schemas import RoutineCreate, RoutineStep, UserContext


def test_memory_full_text_search(application):
    application.memory.remember("司法予備試験の勉強を優先する", tags=["study"])
    results = application.memory.search("司法予備試験")
    assert results
    assert "勉強" in results[0]["content"]


@pytest.mark.asyncio
async def test_routine_executes_low_risk_step(application):
    routine = application.routines.create(
        RoutineCreate(
            name="remember-test",
            steps=[RoutineStep(tool="memory.remember", arguments={"content": "routine ran"})],
        )
    )
    result = await application.routines.run(routine["id"], UserContext(username="admin"))
    assert result["results"][0]["ok"] is True
    assert application.memory.search("routine ran")
