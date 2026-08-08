# ALIGNMENT: Multi-Agent Refactoring & Daisy Decoupling

## 1. Project Context Analysis
- **Current State**: The system is a single-agent chat application ("Daisy") with proactive capabilities, emotional memory, and specific role-playing styles (Love Styles).
- **Architecture**:
    - Backend: FastAPI, SQLAlchemy, Redis, LangChain/Graph.
    - Frontend: React + Vite.
    - Coupling: "Daisy" identity is hardcoded in `templates.py` (CommonSettings), `proactive_service.py` (Prompts), and potentially other areas.
    - Logic: Business logic for proactive engagement is mixed with agent identity.

## 2. Requirement Understanding
- **Goal**: Refactor the current project to support multi-agent role-playing (specifically for future novel/fanfic scenarios).
- **Key Tasks**:
    1.  **Decouple Daisy**: Extract Daisy's configuration, QA response logic, and proactive messaging logic into an independent module.
    2.  **Layered Design**: Establish a clear separation between the "Agent Platform" (infrastructure) and "Agent Implementation" (content).
    3.  **Extensibility**: Design patterns to support multiple agents, potentially interacting in the future.
- **Future Vision**: The system will load different "Characters" (Agents) with unique personalities, memories, and behaviors.

## 3. Smart Decision Strategy & Questions
- **Q1**: How should agent configurations be stored?
    - *Decision*: Use a JSON/YAML based configuration or a Database model for dynamic loading. For this refactor, we can start with a structured Python class/config file approach that can be easily serialized.
- **Q2**: How to handle the `ProactiveService`?
    - *Decision*: The service should become a generic "Scheduler/Trigger" that calls a specific Agent's `should_act()` method. The logic of *when* (time, emotion) might remain shared, but the *decision* and *content* must be agent-specific.
- **Q3**: What about the specific "Love Styles" (Eros, Ludus, etc.)?
    - *Decision*: These are specific to the "Daisy" (or "Romantic Partner") agent type. They should be moved into the Daisy-specific module, not global `templates.py`.

## 4. Proposed Architecture Changes
- **`app/core/agent`**: New module defining the `BaseAgent` interface.
- **`app/agents/daisy`**: Implementation of Daisy, containing her prompts, config, and specific logic.
- **`app/services/agent_manager.py`**: Service to load and retrieve agents.
- **`app/prompts`**: Refactor to remove hardcoded Daisy references; make them template-based or agent-owned.

## 5. Consensus
- **Acceptance Criteria**:
    - No hardcoded "Daisy" in `proactive_service.py`.
    - `CommonSettings` in `templates.py` replaced by a generic `AgentConfig`.
    - Ability to plug in a new agent (conceptually) without changing core service code.
    - Existing functionality (Chat, Proactive, Emotion) works exactly as before for Daisy.
