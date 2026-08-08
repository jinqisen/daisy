# DESIGN_Prompt_Management.md

## 1. 整体架构
```mermaid
graph TD
    A[Daisy_prompts (YAML/Jinja2)] -->|Load on Startup| B[PromptManager (Singleton)]
    B -->|Render(template_name, vars)| C[Daisy_server Services]
    D[Admin API] -->|Refresh| B
```

## 2. 文件结构设计 (Daisy_prompts)
```text
Daisy_prompts/
├── core/
│   ├── system_instructions.yaml  # 核心系统指令
│   └── persona_context.yaml      # 角色上下文构建
├── generation/
│   ├── portrait.yaml             # 角色画像生成
│   └── prompt_engineer.yaml      # CO-STAR Prompt 生成
├── analysis/
│   ├── style.yaml                # 风格分析
│   ├── topic.yaml                # 话题总结
│   └── translation.yaml          # 翻译
└── strategy/
    ├── selection.yaml            # 策略选择
    └── memory_search.yaml        # 记忆搜索
```

## 3. YAML 文件规范
```yaml
name: "get_strategy_selection_prompt"
version: "1.0.0"
description: "生成策略选择的 Prompt"
variables:
  - context_text
  - top_emotions
template: |
  你是一位情感沟通心理学专家。
  用户输入（带上下文）："{{ context_text }}"
  检测到的情绪 (Ekman)：{{ top_emotions }}
  ...
```

## 4. 接口设计 (Daisy_server)
创建一个 `PromptService` 或 `PromptLoader`：
- `load_prompts(dir_path)`: 递归加载 YAML。
- `get_prompt(name, **kwargs)`: 获取并渲染 Prompt。
- `get_system_prompt(name)`: 获取 System Prompt（通常是静态的）。

## 5. 迁移计划
1. **建立基础**: 创建 `Daisy_prompts` 目录和基础 YAML。
2. **实现加载器**: 在 `Daisy_server/app/core/prompt_loader.py` 中实现加载逻辑。
3. **逐步替换**: 修改 `app/prompts/templates.py`，让其调用加载器。
