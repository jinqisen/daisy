# CONSENSUS: Multi-Agent Refactoring

## 1. Requirement Description
Refactor the Daisy_server to support a multi-agent architecture. The goal is to decouple the specific "Daisy" role logic from the core system services, allowing for future expansion into multi-role scenarios (novels, fanfiction).

## 2. Technical Implementation

### 2.1 Core Abstractions
We will introduce a new `app/agents` module.

#### `BaseAgent` (Abstract Base Class)
- **Responsibility**: Defines the standard interface for any agent.
- **Methods**:
    - `get_system_prompt(context: AgentContext) -> str`: Generates the system prompt.
    - `check_proactive_trigger(context: AgentContext) -> ProactiveDecision`: Decides whether to initiate conversation.
    - `get_config() -> AgentConfig`: Returns metadata (name, style, etc.).

#### `DaisyAgent` (Implementation)
- **Responsibility**: Encapsulates all current "Daisy" logic.
- **Components**:
    - `config`: Contains the "Love Styles" (Eros, etc.) and basic settings.
    - `prompts`: Contains the specific prompts currently in `templates.py` and `proactive_service.py`.

#### `AgentManager` (Service)
- **Responsibility**: Loads and provides access to agents.
- **Function**: `get_agent(agent_id: str) -> BaseAgent`. For now, it will default to returning the `DaisyAgent`.

### 2.2 Service Refactoring

#### `ProactiveService`
- **Change**: Remove hardcoded "Daisy" prompt.
- **Logic**:
    1.  Check basic constraints (Time, Online status) - *Keep in Service*.
    2.  Retrieve the active Agent.
    3.  Call `agent.check_proactive_trigger(context)`.
    4.  If trigger is true, use `agent` to generate the message content.

#### `PromptLoader` / `templates.py`
- **Change**: `CommonSettings` will be deprecated/migrated to `DaisyAgent` config.
- **Logic**: Global templates can remain, but character-specific templates move to the Agent.

### 2.3 Directory Structure
```
app/
  agents/
    __init__.py
    base.py           # BaseAgent interface
    manager.py        # AgentRegistry/Manager
    daisy/
      __init__.py
      agent.py        # DaisyAgent class
      config.py       # RoleProfile, CommonSettings moved here
      prompts.py      # Specific prompts
```

## 3. Task Boundaries
- **Scope**:
    - Refactor `ProactiveService`.
    - Refactor `app/prompts/templates.py` (move Daisy stuff out).
    - Create `app/agents` structure.
    - Ensure existing tests pass (or update them).
- **Out of Scope**:
    - Implementing the actual "Novel/Fanfic" multi-agent logic (this is preparation only).
    - Frontend changes (Frontend will still talk to "the system", which proxies to the default agent).

## 4. Acceptance Criteria
1.  **Code Structure**: `app/agents/daisy` exists and contains Daisy's logic.
2.  **Proactive Service**: No string "You are Daisy" in `proactive_service.py`.
3.  **Functionality**:
    - Chat works normally.
    - Proactive messages still trigger (simulated or verified).
4.  **Tests**: Existing tests pass.
