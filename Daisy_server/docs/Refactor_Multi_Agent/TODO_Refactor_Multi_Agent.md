# TODO: Multi-Agent Refactoring Follow-up

## 1. Immediate Actions
- [ ] **Infrastructure Check**: Ensure Redis is running and accessible to fully test the `ProactiveService` runtime flow.
- [ ] **Chat Service Migration**: Refactor `app/workflow/nodes/generation.py` to call `AgentManager.get_agent(id).get_system_prompt()` directly instead of using `templates.py` helper functions. This was left as "Partial" to reduce risk.

## 2. Future Expansion
- [ ] **Dynamic Agent Loading**: Implement a mechanism to load agents from a database or YAML files dynamically, rather than hardcoding `DaisyAgent` in `manager.py`.
- [ ] **Context Awareness**: Enhance `AgentContext` to include more "World" information for novel-based RP.
- [ ] **Multi-Agent Router**: Implement a "Router Agent" that decides *which* character should respond in a group chat setting.
