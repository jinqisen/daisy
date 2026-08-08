# Skill Orchestrator Implementation Report

## Overview
This document details the implementation of the `SkillOrchestrator` and the `MAIN_DIALOGUE_FLOW` which together form the complete dialogue loop for Daisy. The implementation follows the Agent Skills architecture, enabling dynamic routing and execution of skill chains.

## Components

### 1. Skill Orchestrator (`runtime/orchestrator.py`)
The `SkillOrchestrator` is the central engine that executes flow definitions. It supports:
- **Chain Execution**: Sequential execution of steps.
- **Parallel Execution**: Concurrent execution of tasks (using `asyncio.gather`).
- **Switch/Branching**: Conditional execution based on router outputs (supports dynamic routing).
- **Skill Execution**: Direct invocation of `SkillExecutor` for atomic operations.
- **State Management**: Propagates state updates across steps and nested flows.

**Key Features:**
- **Recursive Flow Execution**: Nested flows (chains within switches) are fully supported.
- **Input Mapping**: Flexible mapping of state variables to skill inputs (`inputs`) and support for constant parameters (`params`).
- **Error Handling**: Graceful failure handling and error propagation.

### 2. Dialogue Flow Definition (`app/flows/definitions.py`)
The `MAIN_DIALOGUE_FLOW` defines the high-level logic for the dialogue system using a "Switch" pattern based on the routing result.

#### Routing Tiers
1.  **FAST (Direct Response)**
    - **Trigger**: Regex match (e.g., greetings, simple questions).
    - **Flow**: Direct call to `generation.chat`.
    - **Latency**: Low.

2.  **STANDARD (Persona-based)**
    - **Trigger**: General conversation requiring persona but no deep memory.
    - **Flow**:
        1.  `persona.select`: Choose personality based on emotion/context.
        2.  `persona.build_system_prompt`: Construct prompt with persona instructions.
        3.  `generation.chat`: Generate response using the constructed system prompt.
    - **Latency**: Medium.

3.  **DEEP (Memory-enhanced)**
    - **Trigger**: Complex queries requiring long-term memory or emotional depth.
    - **Flow**:
        1.  `reflexion.retrieve_exemplars`: Fetch relevant memories from Qdrant.
        2.  `persona.select`: Choose persona, informed by retrieved context.
        3.  `persona.build_system_prompt`: Construct deep prompt with context.
        4.  `generation.chat`: Generate response.
    - **Latency**: High (due to vector search and complex context).

## Verification
- **Unit Tests**: `tests/test_orchestrator_flow.py` validates the FAST, STANDARD, and DEEP paths using mocked skill executors.
- **Integration**: The orchestrator is designed to work with the real `SkillExecutor` which interfaces with the `SkillLoader` and actual skill implementations.

## Usage Example
```python
from runtime.orchestrator import SkillOrchestrator
from app.flows.definitions import MAIN_DIALOGUE_FLOW

# Initialize
orchestrator = SkillOrchestrator(skill_executor)

# Initial State
initial_input = {
    "user_input": "Hello Daisy",
    "user_id": "user_123",
    "session_id": "session_abc"
}

# Execute
final_state = await orchestrator.execute_flow(MAIN_DIALOGUE_FLOW, initial_input)

# Result
response = final_state.get("response")
print(response["content"])
```

## Next Steps
- Integrate with the API layer (`app/api/server.py` or similar) to expose the orchestrator via HTTP endpoints.
- Enhance the `router` skill to tune the LLM judge for better discrimination between STANDARD and DEEP cases.
- Add more specialized flows (e.g., "Proactive" flow for unsolicited interactions).
