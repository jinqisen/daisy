from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the agent (e.g., 'Daisy')."""
        pass
        
    @property
    @abstractmethod
    def config(self) -> Dict[str, Any]:
        """Configuration dictionary."""
        pass

    @abstractmethod
    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Generate the core system prompt for chat.
        
        Args:
            context: Context dictionary containing user_profile, history, etc.
        """
        pass
        
    @abstractmethod
    async def check_proactive_trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if proactive message is needed.
        
        Args:
            context: Context dictionary (time, emotion, history).
            
        Returns: 
            Dict: { "should_act": bool, "content": str, "reason": str }
        """
        pass
