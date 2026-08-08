# CONSENSUS_Local_LLM

## 1. 最终共识
为了实现“一直调用远程大模型”向“本地小模型/微调模型”的平滑过渡，我们达成以下共识：

1.  **采用 Ollama 作为本地推理引擎**：
    -   **理由**：Ollama 在 Windows 上安装便捷，资源占用相对较低，且原生提供 OpenAI 兼容的 API 接口，能够直接被现有的 `langchain_openai` 客户端调用，无需修改核心代码逻辑。
2.  **保留现有架构**：
    -   不需要修改 `LLMService` 的 Python 代码。
    -   仅需在 `llm_providers.json` 中新增一个 "local" 或 "ollama" 的配置项。
3.  **微调模型支持路径**：
    -   微调后的模型应转换为 GGUF 格式。
    -   通过 Ollama 的 `Modelfile` 导入并在本地运行。

## 2. 技术实现方案

### 2.1 架构图
```mermaid
graph TD
    A[Daisy Server (Python)] -->|OpenAI Protocol| B(LLMService)
    B -->|Config: remote| C[Huawei/SiliconFlow API]
    B -->|Config: local| D[Ollama Local Server]
    D -->|Inference| E[Local GGUF Model]
    E -.->|Optional| F[Fine-tuned Adapter/Weights]
```

### 2.2 详细步骤

#### 步骤 1: 环境准备
1.  下载并安装 [Ollama for Windows](https://ollama.com/download/windows)。
2.  验证安装：在 PowerShell 中运行 `ollama --version`。

#### 步骤 2: 模型获取
推荐使用 Qwen 2.5 或 Llama 3 作为基座模型（中文能力 Qwen 更优）。
```powershell
# 拉取 7B 模型 (适合 6G-8G 显存)
ollama pull qwen2.5:7b

# 或者 14B 模型 (适合 12G+ 显存)
ollama pull qwen2.5:14b
```

#### 步骤 3: 配置集成
在 `Daisy_server/app/config/llm_providers.json` 中添加如下配置：
```json
"local_ollama": {
    "name": "Local Ollama (Qwen 2.5)",
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model": "qwen2.5:7b",
    "api_key_env": "OLLAMA_API_KEY", 
    "description": "Running locally via Ollama"
}
```
*注意：Ollama 本地调用通常不需要 API Key，但在 `ChatOpenAI` 库中可能需要非空字符串，可设置为 "ollama" 或任意值。*

#### 步骤 4: 微调模型加载 (高级)
如果用户有微调好的模型 (safetensors/bin):
1.  使用 `llama.cpp` 的转换脚本将其转换为 `.gguf` 格式。
2.  创建 `Modelfile`:
    ```dockerfile
    FROM ./my-finetuned-model.gguf
    SYSTEM "You are Daisy, a helpful AI assistant."
    ```
3.  创建模型:
    ```powershell
    ollama create my-daisy-model -f Modelfile
    ```
4.  在配置中将 `model` 字段改为 `my-daisy-model`。

## 3. 优缺点分析

| 特性 | 本地模型 (Ollama) | 远程大模型 (DeepSeek/Huawei) |
| :--- | :--- | :--- |
| **成本** | 零调用成本 (仅电费) | 按 Token 计费 |
| **隐私** | 数据不出本地，绝对安全 | 数据需上传云端 |
| **速度** | 取决于显卡，通常极快 (30-100 tok/s) | 受网络延迟影响 |
| **质量** | 7B/14B 模型逻辑能力弱于 70B+ 大模型 | 逻辑推理、复杂任务能力更强 |
| **维护** | 需自己管理硬件和模型版本 | 服务商维护 |

## 4. 验收标准
- [ ] 能够通过配置切换到本地模型。
- [ ] 系统能够正常启动并与本地 Ollama 服务通信。
- [ ] 聊天功能正常响应。
