# TASK_Prompt_Management.md

## 1. 原子任务列表

### Task 1: 初始化项目结构
- **输入**: 无
- **操作**: 创建 `Daisy_prompts` 目录结构。
- **输出**: 空的目录结构。

### Task 2: 迁移 Core Prompts
- **输入**: `templates.py` 中的 `get_core_system_instructions`, `construct_persona_context` 等。
- **操作**: 创建 `Daisy_prompts/core/*.yaml` 并填充内容。
- **输出**: YAML 文件。

### Task 3: 迁移 Generation Prompts
- **输入**: `templates.py` 中的 `get_system_prompt_generator_meta`, `get_character_portrait_prompt`, `get_costar_prompt`。
- **操作**: 创建 `Daisy_prompts/generation/*.yaml`。
- **输出**: YAML 文件。

### Task 4: 迁移 Analysis & Strategy Prompts
- **输入**: 其余所有 Prompt 函数。
- **操作**: 创建 `Daisy_prompts/analysis/*.yaml` 和 `Daisy_prompts/strategy/*.yaml`。
- **输出**: YAML 文件。

### Task 5: 实现 PromptLoader (Server端)
- **输入**: `Daisy_server` 代码库。
- **操作**: 
    - 添加 `pyyaml` 和 `jinja2` 依赖。
    - 创建 `app/core/prompt_loader.py`。
    - 实现单例模式加载和渲染逻辑。
- **输出**: Python 模块。

### Task 6: 重构 templates.py
- **输入**: `app/prompts/templates.py`, `PromptLoader`。
- **操作**: 修改所有函数，使其调用 `PromptLoader.get_instance().render(...)`。
- **输出**: 更新后的 `templates.py`。

### Task 7: 验证与测试
- **输入**: 运行 `Daisy_server`。
- **操作**: 执行几个典型的 API 调用（如聊天、生成画像），验证 Prompt 是否正确渲染。
- **输出**: 验证报告。

## 2. 依赖关系
Task 1 -> Task 2,3,4 -> Task 5 -> Task 6 -> Task 7
