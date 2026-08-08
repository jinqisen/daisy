import asyncio
import sys
import os
import structlog
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock dependencies BEFORE importing reflexion
sys.modules["app.core.database"] = MagicMock()
sys.modules["app.services.memory.chat_history"] = MagicMock()
sys.modules["app.models"] = MagicMock()
sys.modules["app.core.redis"] = MagicMock()
sys.modules["app.agents.daisy.character_card"] = MagicMock()
sys.modules["app.core.llm"] = MagicMock()

from app.services.learning.reflexion_system import AsyncReflexionSystem

# Configure structlog to print to stderr
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

async def test_reflexion_system():
    print("=== Testing AsyncReflexionSystem ===")
    
    # Setup Mocks
    reflexion = AsyncReflexionSystem()
    
    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.ainvoke.return_value = MagicMock(content="CRITIQUE: Good job\nSCORE: 8\nPATCH: None")
    reflexion.llm_service.get_llm.return_value = mock_llm
    
    # Start System
    await reflexion.start()
    print("Reflexion System Started")
    
    # Enqueue Event
    event = {
        "user_id": "123",
        "session_id": "session_test",
        "user_input": "Hello",
        "agent_response": "Hi there"
    }
    
    print("Enqueuing event...")
    await reflexion.enqueue_event(event)
    
    # Wait for processing
    print("Waiting for worker...")
    await asyncio.sleep(2)
    
    # Stop
    reflexion._running = False
    print("Test Finished")

if __name__ == "__main__":
    asyncio.run(test_reflexion_system())
