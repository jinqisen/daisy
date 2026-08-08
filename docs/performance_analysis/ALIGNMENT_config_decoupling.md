# 配置解耦方案对齐文档 (LLM=Huawei, Embedding=SiliconFlow)

## 1. 核心需求
- **LLM (大模型)**: **强制**使用 **华为云 (Huawei Cloud)** 提供的 DeepSeek 服务。
- **Embedding (向量)**: **强制**使用 **SiliconFlow** 提供的 Embedding 服务。

## 2. 实施方案

### 步骤 1: 恢复环境变量 (`.local_env`)
恢复华为云 LLM 相关配置，移除华为云 Embedding 相关配置（避免混淆）。

> ⚠️ 原文此处直接粘贴了 `.env` 的真实内容,含**可用的 API Key**。
> 已脱敏。密钥不要写进任何会进版本库的文件 —— 文档也算。

```properties
# Huawei Cloud Configuration (LLM Only)
HUAWEI_API_KEY=<在 .env 或应用设置中配置>
HUAWEI_BASE_URL=https://api.modelarts-maas.com/v2
HUAWEI_MODEL_NAME=deepseek-v3.2

# SiliconFlow Configuration (Embedding + Fallback LLM)
OPENAI_API_KEY=<在 .env 或应用设置中配置>
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL_NAME=BAAI/bge-large-zh-v1.5
```

### 步骤 2: 代码重构 (`app/services/memory.py`)
修改 `MemoryService.__init__`，硬编码这种分离逻辑，不再进行“智能判断”。

**修改后逻辑**:
1.  **LLM 配置**: 
    - 检查 `settings.HUAWEI_API_KEY`。
    - 如果存在，配置 LLM Provider 为 `openai` (指向华为云 URL)。
    - 如果不存在，回退到 `settings.OPENAI_API_KEY`。
2.  **Embedding 配置**:
    - **直接**使用 `settings.OPENAI_API_KEY` 和 `settings.OPENAI_BASE_URL`。
    - 模型使用 `settings.EMBEDDING_MODEL_NAME` (即 `BAAI/bge-large-zh-v1.5`)。
    - **切断**之前“如果有华为 Key 就强制用华为 Embedding”的逻辑。

### 步骤 3: 验证
- 确认 LLM 请求发往 `api.modelarts-maas.com`。
- 确认 Embedding 请求发往 `api.siliconflow.cn`。
