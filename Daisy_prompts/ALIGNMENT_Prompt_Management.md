# ALIGNMENT_Prompt_Management.md

## 1. 项目上下文分析
- **现有结构**: `Daisy_server` 使用 `app/prompts/templates.py` 硬编码 Python 函数来管理提示词。
- **目标**: 将这些硬编码的提示词提取出来，放入一个新的项目 `Daisy_prompts` 中进行版本管理（YAML/Markdown），并提供加载机制。
- **核心价值**: 解耦代码与提示词，支持非技术人员调整 Prompt，支持 Prompt 版本回滚和 A/B 测试。

## 2. 需求理解确认
- **输入**: `Daisy_server` 现有的 `templates.py`。
- **输出**: 
    1. 一个新的目录 `Daisy_prompts`。
    2. 结构化的 Prompt 文件（推荐 YAML + Jinja2 模板）。
    3. `Daisy_server` 的重构，使其从 `Daisy_prompts` 加载提示词，而不是硬编码。
- **约束**: 保持现有功能不变，确保 Prompt 渲染逻辑一致。

## 3. 智能决策策略
- **格式选择**: 使用 **YAML** 存储元数据（版本、描述、输入变量），使用 **Jinja2** 风格的字符串存储实际 Prompt 内容。
- **目录结构**: 按功能模块拆分（如 `core`, `portrait`, `strategy` 等）。
- **加载机制**: `Daisy_server` 启动时加载 YAML 文件，运行时动态渲染。

## 4. 关键决策点
- **是否保留 Python 函数封装？**: 是的，保留 Python 函数作为接口，但在函数内部改为读取配置并渲染，而不是直接返回硬编码字符串。这样对调用方（Services）透明。
- **热更新**: 暂时不要求热更新（需要重启 Server 生效），或者提供一个 API 刷新配置。建议提供 API 刷新。

## 5. 最终共识
- 创建 `Daisy_prompts` 目录作为 Prompt 的单一事实来源。
- 将 `templates.py` 中的所有 Prompt 迁移到 `Daisy_prompts` 下的 YAML 文件。
- 重构 `Daisy_server` 以适配新结构。
