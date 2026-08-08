# DESIGN: Multi-Agent Architecture

## 1. System Architecture

```mermaid
graph TD
    User[User / Client] --> API[FastAPI Endpoints]
    API --> Service[Services (Chat, Proactive)]
    
    subgraph "Agent Layer (New)"
        Manager[Agent Manager]
        Base[Base Agent Interface]
        Daisy[Daisy Agent]
        Other[Other Agents (Future)]
        
        Manager -->|Retrieves| Base
        Daisy -- Implements --> Base
        Other -- Implements --> Base
    end
    
    Service -->|Request Agent| Manager
    Service -->|Use Agent Logic| Base
    
    Daisy -->|Config| Config[Daisy Config]
    Daisy -->|Prompts| Prompts[Daisy Prompts]
```

## 2. Component Design

### 2.1 `app.agents.base.BaseAgent`
The contract for all agents.

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: pass
    
    @abstractmethod
    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Generate the core system prompt for chat."""
        pass
        
    @abstractmethod
    async def check_proactive_trigger(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if proactive message is needed.
        Returns: { "should_act": bool, "content": str, "reason": str }
        """
        pass
```

### 2.2 `app.agents.manager.AgentManager`
Manages agent lifecycle and retrieval.

```python
class AgentManager:
    def __init__(self):
        self._agents = {}
        # Pre-register Daisy
        self.register_agent(DaisyAgent())
        
    def get_agent(self, agent_id: str = "default") -> BaseAgent:
        return self._agents.get(agent_id, self._agents["daisy"])
```

### 2.3 `app.agents.daisy.DaisyAgent`
Encapsulates current Daisy logic.
- Moves `RoleProfile` and `CommonSettings` here.
- Implements `get_system_prompt` using `PromptLoader` but with local templates.
- Implements `check_proactive_trigger` using the logic extracted from `ProactiveService`.

## 3. Data Flow

### Chat Flow
1. User sends message.
2. `ChatService` calls `AgentManager.get_agent(user_settings.agent_id)`.
3. `ChatService` calls `agent.get_system_prompt(...)`.
4. LLM is invoked with the prompt.

### Proactive Flow
1. `Worker` triggers `ProactiveService`.
2. `ProactiveService` checks global constraints (online, busy).
3. `ProactiveService` calls `AgentManager.get_agent(...)`.
4. `ProactiveService` calls `agent.check_proactive_trigger(...)`.
5. If yes, sends message.

## 4. Interfaces & Contracts

- **Agent Config**: JSON/Pydantic model specific to the agent.
- **Context**: Dictionary containing `user_profile`, `history`, `emotion`, `time`, etc.

## 5. Migration Strategy
1. Create `app/agents/base.py`.
2. Create `app/agents/daisy/` and move code from `templates.py`.
3. Create `app/agents/manager.py`.
4. Modify `ProactiveService` to use `AgentManager`.
5. Modify `ChatService` (if necessary) to use `AgentManager` for system prompts.
