# DATA_RESOURCES

## 1. 推荐的开源数据集 (人人对话/心理咨询)

经过检索，以下是目前最适合 Daisy 项目的开源中文心理咨询与情感对话语料库。

### 核心推荐 (心理咨询/情感支持)

| 数据集名称 | 简介 | 规模 | 适用性 | 来源 |
| :--- | :--- | :--- | :--- | :--- |
| **CPsyCoun** | 基于真实心理咨询案例重构的**多轮对话**数据集。这是目前质量极高、最贴近真实咨询流程的数据。 | ~3,134 组多轮对话 | ⭐⭐⭐⭐⭐ (强推，包含完整咨询阶段) | [GitHub](https://github.com/CAS-SIAT-XinHai/CPsyCoun) |
| **PsyQA** | 中文心理互助问答数据集，包含详细的求助描述和高质量的长回复。 | ~2.2万 问题<br>~5.6万 回复 | ⭐⭐⭐⭐ (适合训练共情回复能力) | [HuggingFace](https://huggingface.co/datasets/lsy641/PsyQA) |
| **EFAQA** | (Emotional First Aid) 心理咨询问答语料库，源自真实社区问答。 | ~2万 条 | ⭐⭐⭐⭐ (真实性高) | [GitHub](https://github.com/chatopera/efaqa-corpus-zh) |
| **SmileChat** | 包含多轮对话的心理咨询数据集，专注于情绪安抚。 | ~5.6万 轮 | ⭐⭐⭐⭐ (多轮交互强) | [GitHub](https://github.com/qiuhuachuan/smile) |

### 辅助推荐 (通用闲聊/情绪分类)

| 数据集名称 | 简介 | 适用性 | 来源 |
| :--- | :--- | :--- | :--- |
| **Natural Conv** | 腾讯发布的中文多轮人机对话数据集（基于新闻话题，非纯闲聊）。 | ⭐⭐⭐ (增强通用对话逻辑) | [GitHub](https://github.com/Tencent/NaturalConv) |
| **LCCC** | (Large-scale Cleaned Chinese Conversation) 大规模清洗后的中文对话。 | ⭐⭐⭐ (增强“人话”能力，需筛选) | [HuggingFace](https://huggingface.co/datasets/coig/lccc) |

## 2. 如何获取与使用

### 方式 A: 直接下载处理好的 JSONL (推荐)
对于 **CPsyCoun** 和 **PsyQA**，建议直接去其 GitHub/HuggingFace 页面下载。

### 方式 B: 使用 Python 脚本加载 (HuggingFace)
如果您有网络环境（或配置了代理），可以直接用代码加载。

```python
from datasets import load_dataset

# 1. 加载 PsyQA (问答对)
# 注意：PsyQA 在 HF 上可能需要申请权限或使用特定 loader
# 这里演示通用加载方式
try:
    dataset = load_dataset("lsy641/PsyQA")
    print("PsyQA loaded:", dataset)
except Exception as e:
    print(f"PsyQA load failed (check network/auth): {e}")

# 2. 如果无法自动加载，建议手动下载数据文件
# 访问 https://huggingface.co/datasets/lsy641/PsyQA/tree/main
# 下载 PsyQA_full.json
```

## 3. 数据合成策略 (Data Synthesis)

虽然有了上述开源数据，但为了让 Daisy 更像 **Daisy** (而不是一个通用的心理医生)，建议采用 **"混合微调"** 策略：

1.  **基座能力 (30%)**: 使用 **CPsyCoun** 训练模型掌握“咨询流程”（建立关系 -> 探索问题 -> 解决问题）。
2.  **共情能力 (30%)**: 使用 **PsyQA** 训练模型学会“说长文、说暖心的话”。
3.  **角色注入 (40%)**: 使用 **大模型合成的数据** (您之前的任务)，让模型记住自己叫 Daisy，性格活泼又专业，而不是刻板的医生。

## 4. 警告
*   **隐私与伦理**: 开源数据集通常已去隐私化，但在商用或公开部署前请务必再次检查（去除人名、地名）。
*   **负面情绪**: 心理咨询语料中包含大量负面情绪（想自杀、抑郁等），模型可能会“过拟合”导致自己也变得抑郁或只会安慰。**务必加入一定比例的正常闲聊数据（如清洗后的豆瓣数据）来中和。**
