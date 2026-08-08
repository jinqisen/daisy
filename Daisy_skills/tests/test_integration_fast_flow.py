import pytest
from pathlib import Path

from runtime.loader import SkillLoader
from runtime.discovery import SkillDiscovery
from runtime.executor import SkillExecutor
from runtime.orchestrator import SkillOrchestrator
from app.flows.definitions import MAIN_DIALOGUE_FLOW
from app.services import llm as llm_service


class DummyLLM:
    async def generate_response_async(self, system_prompt, user_input, context="", metadata=None):
        return "fast-response"


@pytest.mark.asyncio
async def test_fast_flow_integration(monkeypatch):
    monkeypatch.setattr(llm_service, "get_llm_service", lambda: DummyLLM())
    base_dir = Path(__file__).resolve().parents[1]
    skills_dir = base_dir / "app" / "skills"

    loader = SkillLoader(str(skills_dir))
    await loader.discover_skills()
    discovery = SkillDiscovery(loader)
    await discovery.build_index()
    executor = SkillExecutor(loader)
    orchestrator = SkillOrchestrator(loader, discovery, executor)

    result = await orchestrator.execute_flow(
        MAIN_DIALOGUE_FLOW,
        {
            "user_input": "hi",
            "user_id": "test_user",
            "session_id": "test_session",
            "context": {}
        }
    )

    assert result["route_result"]["route"] == "FAST"
    assert result["response"]["content"] == "fast-response"


@pytest.mark.asyncio
async def test_standard_flow_integration(monkeypatch):
    async def judge_route(*args, **kwargs):
        from app.skills.router.scripts.route_judge import RouteResult
        return RouteResult(route="STANDARD", confidence=0.8, reasoning="test")

    monkeypatch.setattr(llm_service, "get_llm_service", lambda: DummyLLM())
    monkeypatch.setattr("app.skills.router.scripts.route_judge.route_judge.judge_route", judge_route)

    base_dir = Path(__file__).resolve().parents[1]
    skills_dir = base_dir / "app" / "skills"

    loader = SkillLoader(str(skills_dir))
    await loader.discover_skills()
    discovery = SkillDiscovery(loader)
    await discovery.build_index()
    executor = SkillExecutor(loader)
    orchestrator = SkillOrchestrator(loader, discovery, executor)

    result = await orchestrator.execute_flow(
        MAIN_DIALOGUE_FLOW,
        {
            "user_input": "tell me a joke",
            "user_id": "test_user",
            "session_id": "test_session",
            "context": {}
        }
    )

    assert result["route_result"]["route"] == "STANDARD"
    assert "system_prompt" in result["system_prompt_data"]
    assert result["response"]["content"] == "fast-response"


@pytest.mark.asyncio
async def test_deep_flow_integration(monkeypatch):
    async def judge_route(*args, **kwargs):
        from app.skills.router.scripts.route_judge import RouteResult
        return RouteResult(route="DEEP", confidence=0.9, reasoning="test")

    async def retrieve_exemplars(*args, **kwargs):
        return {"items": []}

    monkeypatch.setattr(llm_service, "get_llm_service", lambda: DummyLLM())
    monkeypatch.setattr("app.skills.router.scripts.route_judge.route_judge.judge_route", judge_route)
    monkeypatch.setattr("app.skills.reflexion.scripts.service.reflexion_service.retrieve_exemplars", retrieve_exemplars)

    base_dir = Path(__file__).resolve().parents[1]
    skills_dir = base_dir / "app" / "skills"

    loader = SkillLoader(str(skills_dir))
    await loader.discover_skills()
    discovery = SkillDiscovery(loader)
    await discovery.build_index()
    executor = SkillExecutor(loader)
    orchestrator = SkillOrchestrator(loader, discovery, executor)

    result = await orchestrator.execute_flow(
        MAIN_DIALOGUE_FLOW,
        {
            "user_input": "I feel overwhelmed and need help",
            "user_id": "test_user",
            "session_id": "test_session",
            "context": {}
        }
    )

    assert result["route_result"]["route"] == "DEEP"
    assert "system_prompt" in result["system_prompt_data"]
    assert result["response"]["content"] == "fast-response"
