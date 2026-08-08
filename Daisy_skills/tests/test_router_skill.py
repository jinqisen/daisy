import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.skills.router.scripts import route_input, get_route_info, update_route_patterns
from app.skills.router.scripts.intelligent_router import intelligent_router
from runtime.models import SkillContext

@pytest.fixture
def mock_context():
    return SkillContext(
        user_id="test_user",
        session_id="test_session"
    )

@pytest.mark.asyncio
async def test_fast_route(mock_context):
    # Test FAST pattern match
    input_data = {
        "user_input": "hi",
        "user_id": "u1",
        "session_id": "s1"
    }
    
    result = await route_input.execute(input_data, mock_context)
    
    assert result["route"] == "FAST"
    assert result["confidence"] == 1.0
    assert "Matched FAST pattern" in result["reasoning"]

@pytest.mark.asyncio
async def test_llm_route_standard(mock_context):
    # Mock LLM judge response
    mock_judge = AsyncMock()
    mock_judge.judge_route.return_value = AsyncMock(
        route="STANDARD",
        confidence=0.9,
        reasoning="Simple question"
    )
    # The return value of an AsyncMock needs to be awaitable, 
    # but judge_route returns a Pydantic model directly if not async,
    # or the result of it. 
    # Actually intelligent_router calls await route_judge.judge_route(...)
    
    # Let's mock the route_judge object inside intelligent_router
    with patch("app.skills.router.scripts.intelligent_router.route_judge") as mock_rj:
        mock_rj.judge_route = AsyncMock()
        # The result needs to have .model_dump() or be the RouteResult object
        from app.skills.router.scripts.route_judge import RouteResult
        mock_rj.judge_route.return_value = RouteResult(
            route="STANDARD",
            confidence=0.9,
            reasoning="Simple question"
        )

        input_data = {
            "user_input": "What is the weather?",
            "user_id": "u1",
            "session_id": "s1"
        }
        
        result = await route_input.execute(input_data, mock_context)
        
        assert result["route"] == "STANDARD"
        assert result["confidence"] == 0.9

@pytest.mark.asyncio
async def test_update_patterns(mock_context):
    new_patterns = ["^foo$", "^bar$"]
    result = await update_route_patterns.execute({"patterns": new_patterns}, mock_context)
    
    assert result["success"] is True
    assert result["count"] == 2
    
    # Verify update
    info = await get_route_info.execute({}, mock_context)
    assert info["fast_patterns"] == new_patterns
    
    # Reset for other tests (optional, but good practice if state is shared)
    from app.skills.router.scripts.patterns import DEFAULT_FAST_PATTERNS
    await update_route_patterns.execute({"patterns": DEFAULT_FAST_PATTERNS}, mock_context)
