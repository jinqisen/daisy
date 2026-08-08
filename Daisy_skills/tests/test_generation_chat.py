import pytest

from app.skills.generation.scripts import chat as chat_script


class DummyLLM:
    async def generate_response_async(self, system_prompt, user_input, context="", metadata=None):
        return f"{system_prompt}|{user_input}|{context}"


@pytest.mark.asyncio
async def test_generation_chat_requires_input():
    result = await chat_script.execute({}, None)
    assert "error" in result


@pytest.mark.asyncio
async def test_generation_chat_uses_user_input(monkeypatch):
    monkeypatch.setattr(chat_script, "get_llm_service", lambda: DummyLLM())
    result = await chat_script.execute(
        {
            "user_input": "hi",
            "system_prompt": "sys",
            "context": {"source": "test"}
        },
        None
    )
    assert result["content"] == "sys|hi|{\"source\": \"test\"}"
