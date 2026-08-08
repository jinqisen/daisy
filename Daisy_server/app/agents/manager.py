from typing import Dict, Optional
from .base import BaseAgent

class AgentManager:
    """
    Manages agent lifecycle and retrieval.
    """
    _instance = None
    _agents: Dict[str, BaseAgent] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentManager, cls).__new__(cls)
            cls._instance._initialize_defaults()
        return cls._instance

    def _initialize_defaults(self):
        try:
            from .daisy.agent import DaisyAgent
            self.register_agent(DaisyAgent())
        except Exception as e:
            print(f"Failed to register default DaisyAgent: {e}")

    def register_agent(self, agent: BaseAgent):
        """Register a new agent."""
        self._agents[agent.name.lower()] = agent
        
    def get_agent(self, agent_id: str = "daisy") -> Optional[BaseAgent]:
        """Get an agent by ID (name). Defaults to 'daisy'."""
        return self._agents.get(agent_id.lower())

    @classmethod
    def get_instance(cls):
        return cls()
