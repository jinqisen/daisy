# ALIGNMENT_Local_LLM

## 1. 项目上下文分析
- **现状**: 当前项目 `Daisy_server` 使用 `langchain_openai.ChatOpenAI` 封装了 LLM 调用，通过 `llm_providers.json` 配置了远程服务商（Huawei Cloud, SiliconFlow）。
- **需求**: 用户希望引入本地小模型或本地微调模型，以替代或补充远程大模型的调用，降低成本并提高响应速度（在网络不佳时）或数据隐私。
- **约束**: 
  - 当前不修改代码，仅探讨方案。
  - 运行环境为 Windows。
  - 需要兼容现有的 OpenAI 接口格式，以便最小化代码改动。

## 2. 需求理解确认
- **核心目标**: 能够运行本地模型，并且该本地模型能被现有的 `LLMService` 调用。
- **扩展目标**: 支持加载自定义微调的 Adapter (LoRA) 或 Merged Model。
- **技术选型方向**: 
  - 推理引擎：Ollama, LM Studio, vLLM (WSL), LocalAI。
  - 模型格式：GGUF (CPU/GPU 混合推理), SafeTensors (纯 GPU)。

## 3. 方案探讨与决策策略

### 关键问题 1: 如何在 Windows 上最简单地运行并提供 OpenAI 兼容接口？
- **选项 A: Ollama**
  - **优点**: 安装极其简单，原生支持 Windows，命令行体验好，模型库丰富（GGUF），原生支持 OpenAI API。
  - **缺点**: 对某些自定义架构模型支持稍慢，微调模型需要转换 Modelfile。
- **选项 B: LM Studio**
  - **优点**: GUI 界面友好，直接搜索 HuggingFace 下载 GGUF，开启 Server 很方便。
  - **缺点**: 主要面向桌面用户，作为后台服务不如 Ollama 轻量（但在开发调试阶段很棒）。
- **选项 C: vLLM (WSL)**
  - **优点**: 吞吐量极高，支持并发好。
  - **缺点**: Windows 下需要 WSL2，配置复杂，主要用于生产环境部署。

**决策**: 推荐 **Ollama** 作为首选 CLI/服务方案，**LM Studio** 作为可视化调试辅助。两者都完美支持 OpenAI 接口。

### 关键问题 2: 如何支持微调模型？
- **方案**: 
  1. 使用 Unsloth/Axolotl 等工具在本地或云端进行微调。
  2. 将微调后的模型（LoRA）合并（Merge）到基座模型，或者转换为 GGUF 格式。
  3. 在 Ollama 中创建 `Modelfile` 指向该 GGUF 文件。
  4. 现有代码只需将 `model` 参数指向自定义的模型名称即可。

## 4. 待确认事项
- 用户的硬件配置（显存大小），决定了能跑多大的模型（7B, 14B, 32B?）。
- 是否已经有微调好的模型权重？还是需要从头开始微调？

## 5. 预期产出
- 一个详细的集成指南（CONSENSUS 文档）。
- 修改后的 `llm_providers.json` 示例（展示如何配置本地 Provider）。
