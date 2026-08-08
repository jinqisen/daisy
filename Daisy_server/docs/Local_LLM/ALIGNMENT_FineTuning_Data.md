# ALIGNMENT_FineTuning_Data

## 1. 目标
为 Daisy 项目的本地模型微调准备高质量的训练数据。
目标是让小模型（如 Qwen2.5-7B）习得 Daisy 的：
1.  **人设与语气**（温暖、共情、专业心理咨询）。
2.  **业务逻辑**（理解情感状态、遵循咨询流程）。

## 2. 数据格式标准
为了兼容主流微调框架（如 LLaMA-Factory, Unsloth），推荐使用 **ShareGPT 格式**（支持多轮对话）或 **Alpaca 格式**（指令-输入-输出）。

### 推荐：ShareGPT 格式 (JSONL)
最适合多轮对话微调。
```json
{
  "conversations": [
    {
      "from": "system",
      "value": "你叫Daisy，是一个富有同理心的心理咨询助手..."
    },
    {
      "from": "user",
      "value": "我最近感觉很累，不想工作。"
    },
    {
      "from": "assistant",
      "value": "听到你这么说我很难过。这种疲惫感持续很久了吗？是身体上的累还是心里的累呢？"
    }
  ]
}
```

## 3. 数据来源策略

### 策略 A: 现有数据导出 (High Value)
利用 `Daisy_server` 中现有的数据库记录。
- **源表**: `llm_traces` (LLMTraceDB) 和 `chat_history` (ChatHistoryDB)。
- **优势**: 真实的用户交互数据，最贴合实际场景。
- **操作**: 编写脚本将数据库记录转换为 JSONL 格式。

### 策略 B: 大模型蒸馏/合成 (High Volume)
利用现有的高性能远程模型（DeepSeek/GPT-4）生成数据。
- **方法**: 编写 Prompt 让大模型模拟 "用户" 和 "Daisy" 进行左右互搏，或者让大模型改写现有的普通对话。
- **Prompt 示例**: "请生成 10 组心理咨询对话，咨询师叫 Daisy，风格温柔专业..."

### 策略 C: 开源数据集补充 (General Ability)
使用公开的心理咨询数据集增强基础能力。
- **示例**: PsyQA, SmileChat 等中文心理咨询数据集。
- **注意**: 需要清洗，加上 System Prompt 以统一口吻。

## 4. 数据清洗与质量控制
- **去重**: 删除完全重复的对话。
- **隐私**: 必须移除用户真实姓名、ID 等敏感信息（PII）。
- **格式修正**: 确保 JSON 语法正确，去除乱码。

## 5. 交付物
- 数据导出脚本: `scripts/export_training_data.py`
- 数据准备指南文档。
