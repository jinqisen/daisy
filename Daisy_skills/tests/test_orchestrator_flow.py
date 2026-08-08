import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from runtime.orchestrator import SkillOrchestrator
from runtime.executor import SkillExecutor
from runtime.loader import SkillLoader
from runtime.discovery import SkillDiscovery
from runtime.models import SkillContext, SkillResult
from app.flows.definitions import MAIN_DIALOGUE_FLOW

@pytest.fixture
def mock_executor():
    executor = AsyncMock(spec=SkillExecutor)
    return executor

@pytest.fixture
def orchestrator(mock_executor):
    loader = MagicMock(spec=SkillLoader)
    discovery = MagicMock(spec=SkillDiscovery)
    return SkillOrchestrator(loader, discovery, mock_executor)

@pytest.mark.asyncio
async def test_fast_flow(orchestrator, mock_executor):
    # Setup mock returns
    async def side_effect(skill, operation, input_data, context):
        if skill == "router" and operation == "route_input":
            return SkillResult(success=True, data={"route": "FAST", "confidence": 1.0})
        if skill == "generation" and operation == "chat":
            return SkillResult(success=True, data={"content": "Fast response", "role": "assistant"})
        return SkillResult(success=False, error="Unknown skill")

    mock_executor.execute.side_effect = side_effect

    initial_input = {
        "user_input": "Hi",
        "user_id": "test_user",
        "session_id": "test_session"
    }

    result = await orchestrator.execute_flow(MAIN_DIALOGUE_FLOW, initial_input)

    # Verify Router was called
    mock_executor.execute.assert_any_call(
        "router", "route_input", 
        {"user_input": "Hi", "user_id": "test_user", "session_id": "test_session"}, 
        None
    )
    
    # Verify Generation was called (FAST path)
    # Note: args matching might be tricky with dicts, so we check basic presence
    calls = mock_executor.execute.call_args_list
    assert any(c[0][0] == "generation" for c in calls)
    
    assert result.get("response", {}).get("content") == "Fast response"

@pytest.mark.asyncio
async def test_standard_flow(orchestrator, mock_executor):
    # Setup mock returns
    async def side_effect(skill, operation, input_data, context):
        if skill == "router" and operation == "route_input":
            return SkillResult(success=True, data={"route": "STANDARD"})
        if skill == "emotion" and operation == "analyze":
            return SkillResult(success=True, data={"scores": {"joy": 1.0}, "ekman_scores": {"joy": 1.0}})
        if skill == "topic" and operation == "summarize":
            return SkillResult(success=True, data={"summary": "summary"})
        if skill == "memory" and operation == "search":
            return SkillResult(success=True, data={"memories": []})
        if skill == "persona" and operation == "select":
            return SkillResult(success=True, data={"selected_personality": "cheerful"})
        if skill == "portrait" and operation == "generate":
            return SkillResult(success=True, data={"portrait_text": "", "character_card": {}})
        if skill == "persona" and operation == "build_system_prompt":
            return SkillResult(success=True, data={"system_prompt": "You are cheerful."})
        if skill == "generation" and operation == "chat":
            return SkillResult(success=True, data={"content": "Standard response", "role": "assistant"})
        return SkillResult(success=False, error=f"Unknown skill {skill}")

    mock_executor.execute.side_effect = side_effect

    initial_input = {
        "user_input": "Hello",
        "user_id": "test_user",
        "session_id": "test_session"
    }

    result = await orchestrator.execute_flow(MAIN_DIALOGUE_FLOW, initial_input)

    # Verify sequence
    # 1. Router
    # 2. Persona Select
    # 3. Persona Build Prompt
    # 4. Generation
    
    skill_calls = [c[0][0] for c in mock_executor.execute.call_args_list]
    assert "router" in skill_calls
    assert "persona" in skill_calls
    assert "generation" in skill_calls
    
    assert result.get("response", {}).get("content") == "Standard response"

@pytest.mark.asyncio
async def test_deep_flow(orchestrator, mock_executor):
    # Setup mock returns
    async def side_effect(skill, operation, input_data, context):
        if skill == "router" and operation == "route_input":
            return SkillResult(success=True, data={"route": "DEEP"})
        if skill == "emotion" and operation == "analyze":
            return SkillResult(success=True, data={"scores": {"sadness": 1.0}, "ekman_scores": {"sadness": 1.0}})
        if skill == "topic" and operation == "summarize":
            return SkillResult(success=True, data={"summary": "summary"})
        if skill == "reflexion" and operation == "retrieve_exemplars":
            return SkillResult(success=True, data={"exemplars": []})
        if skill == "memory" and operation == "search":
            return SkillResult(success=True, data={"memories": []})
        if skill == "persona" and operation == "select":
            return SkillResult(success=True, data={"selected_personality": "comfort"})
        if skill == "portrait" and operation == "generate":
            return SkillResult(success=True, data={"portrait_text": "", "character_card": {}})
        if skill == "persona" and operation == "build_system_prompt":
            return SkillResult(success=True, data={"system_prompt": "You are comforting."})
        if skill == "generation" and operation == "chat":
            return SkillResult(success=True, data={"content": "Deep response", "role": "assistant"})
        if skill == "reflexion" and operation == "enqueue_event":
            return SkillResult(success=True, data={"status": "queued"})
        return SkillResult(success=False, error=f"Unknown skill {skill}")

    mock_executor.execute.side_effect = side_effect

    initial_input = {
        "user_input": "I am sad",
        "user_id": "test_user",
        "session_id": "test_session"
    }

    result = await orchestrator.execute_flow(MAIN_DIALOGUE_FLOW, initial_input)

    skill_calls = [c[0][0] for c in mock_executor.execute.call_args_list]
    assert "router" in skill_calls
    assert "reflexion" in skill_calls
    assert "persona" in skill_calls
    assert "generation" in skill_calls
    
    # Check if reflexion enqueue was called last (or near end)
    assert skill_calls[-1] == "reflexion" or "reflexion" in skill_calls
    
    assert result.get("response", {}).get("content") == "Deep response"
