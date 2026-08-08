# Daisy Skills Development Plan (Migration from Daisy Server)

## Overview
This document outlines the plan to migrate the functionality of `Daisy_server` to the new `Daisy_skills` architecture, which is based on the **Model Context Protocol (MCP)** and a modernized **LangChain/LangGraph** workflow. The goal is to fully replace the old server while maintaining all business logic (Emotion, Memory, Reflexion).

## Phase 1: Workflow Foundation (Current Focus)
The objective is to establish the graph-based workflow and ensure basic conversation capabilities with context awareness.

- [x] **MCP Infrastructure**: Server, Client, and Tool registration.
- [x] **Database Connectivity**: Shared access to `sqlite.db` and model porting.
- [x] **Orchestrator Fast Path**: Generation skill execution alignment and test coverage.
- [x] **Standard/Deep Integration Tests**: Added routing stubs and reflexion mocks.
- [x] **Orchestrator Context Wiring**: Emotion/Topic/Memory/Portrait context in MAIN_DIALOGUE_FLOW.
- [x] **Parallel Preprocessing**: Emotion/Topic/Reflexion run in parallel where possible.
- [ ] **Workflow Reconstruction (LangGraph)**:
    - Replace the simple `AgentWorkflow` with a `StateGraph`.
    - Implement a `Router` node (Standard vs. Deep path).
    - Implement placeholder nodes for complex services.
- [ ] **Context Injection**:
    - Load `User`, `CharacterCard`, and `ChatHistory` from the database at the start of the workflow.
    - Inject these into the LLM context.

## Phase 2: Core Services Migration
Port the sophisticated business logic services from the old server to the new architecture, potentially as **MCP Tools** or **Graph Nodes**.

- [ ] **Emotion Engine**:
    - Port `services/emotion.py` logic.
    - Implement `analyze_emotion` node in the graph.
- [ ] **Memory System**:
    - Port `services/memory.py` (Short-term & Long-term).
    - Implement `retrieve_memory` and `save_memory` nodes.
- [ ] **Reflexion & Style**:
    - Port `services/reflexion/` and `analyze_style` logic.
    - Implement `agent_thoughts` node (internal monologue).
- [ ] **Topic Management**:
    - Port `summarize_topic` logic.

## Phase 3: API & System Integration
Expose the full functionality via FastAPI to match the old server's API surface.

- [ ] **API Router Migration**:
    - Implement `routers/chat.py` (streaming response, history).
    - Implement `routers/session.py` (session management).
    - Implement `routers/upload.py` (file handling).
- [ ] **Authentication**:
    - Port `api/auth.py` (OAuth2 / JWT) and `api/deps.py`.
- [ ] **Task Queue**:
    - Port `tasks/` (arq) for background processing (e.g., proactive messages).

## Phase 4: Optimization & Expansion
Enhance the system for production readiness.

- [ ] **Dockerization**: Create `Dockerfile` and `docker-compose.yml`.
- [ ] **MCP Tool Expansion**: Add more tools (File System, Web Browser, etc.).
- [ ] **Testing**: Unit and Integration tests for the new workflow.

## Migration Strategy
- **Incremental Replacement**: We will build `Daisy_skills` alongside `Daisy_server`.
- **Shared Data**: Both servers share the same SQLite database, allowing for seamless switching.
- **Verification**: Each phase will be verified with test scripts (like `client.py`).
