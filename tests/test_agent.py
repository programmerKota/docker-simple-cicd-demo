from __future__ import annotations

import pytest

from jarvis_home.schemas import ChatRequest, UserContext


class FakeOllama:
    model = "fake"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools, think=False):
        self.calls += 1
        if self.calls == 1:
            return {
                "model": "fake",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "memory.remember",
                                "arguments": {"content": "favorite room is study"},
                            }
                        }
                    ],
                },
            }
        return {"model": "fake", "message": {"role": "assistant", "content": "記憶しました。"}}


@pytest.mark.asyncio
async def test_agent_tool_loop(application):
    application.agent.ollama = FakeOllama()
    response = await application.agent.chat(ChatRequest(message="書斎が好きだと覚えて"), UserContext(username="admin"))
    assert response.message == "記憶しました。"
    assert application.memory.search("favorite room")
