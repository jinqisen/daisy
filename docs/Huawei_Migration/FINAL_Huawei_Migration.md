# Huawei Cloud ModelArts Migration Report

## 1. 任务概述
本任务旨在将除了 `CrewAI` 模块以外的所有 LLM 调用迁移至华为云 ModelArts 服务。

## 2. 修改内容

### 2.1 配置文件 (.env / .local_env)
增加了华为云相关的配置项：
- `HUAWEI_API_KEY`
- `HUAWEI_BASE_URL` (Chat)
- `HUAWEI_EMBEDDING_BASE_URL` (Embeddings)
- `HUAWEI_MODEL_NAME` (deepseek-v3.2)
- `HUAWEI_EMBEDDING_MODEL_NAME` (bge-m3)

### 2.2 代码变更

#### `app/core/config.py`
- 在 `Settings` 类中增加了对应的华为云配置字段。

#### `app/services/llm.py`
- 修改了 `get_llm` 方法。
- **逻辑变更**: 如果未显式提供 API Key，且配置了 `HUAWEI_API_KEY`，则默认使用华为云配置作为系统默认 LLM。
- **特性支持**: 针对华为云 DeepSeek 模型，自动添加了 `thinking: { type: "enabled" }` 参数。
- **兼容性**: 如果未配置华为云，则回退到原有的 SiliconFlow/OpenAI 配置，确保不破坏现有环境。

#### `app/services/memory.py`
- 修改了 `MemoryService` 初始化逻辑。
- **Embedding**: 如果配置了 `HUAWEI_API_KEY`，则 `embedder` 和 `llm` (用于记忆处理) 均切换至华为云。
- **环境变量**: 显式设置 `os.environ["OPENAI_API_KEY"]` 为 `settings.OPENAI_API_KEY` (SiliconFlow)，以确保 `CrewService` (依赖环境变量或默认行为) 继续使用 SiliconFlow，满足"除 Crew 外"的需求。

## 3. 验证结果
- **LLMService**: 默认调用已指向华为云 endpoint (`https://api.modelarts-maas.com/v2`)。
- **Thinking 参数**: 已正确注入。
- **CrewService**: 保持使用 SiliconFlow 配置 (通过保留原有环境变量和 `LLM_MODEL_NAME` 设置)。

## 4. 待办事项 (TODO)
- [ ] 在生产环境中验证华为云 API 的稳定性和延迟。
- [ ] 监控华为云 Embedding 服务的向量维度是否与原有数据兼容 (BGE-M3 通常为 1024，需确认)。
