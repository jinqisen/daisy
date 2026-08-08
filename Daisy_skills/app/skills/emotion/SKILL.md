---
name: emotion
version: 1.0.0
description: 情绪分析与 Ekman 映射能力，支持文本情绪识别和情绪维度映射
author: Daisy Team
license: MIT
category: analysis
tags:
  - emotion
  - sentiment
  - ekman
  - analysis
dependencies: []
allowed_tools:
  - emotion.analyze
  - emotion.update_config
---

# Emotion Skill

## 概述

Emotion Skill 提供文本情绪分析能力，能够识别文本中的情绪成分，并将其映射到 Ekman 六类基本情绪（愤怒、厌恶、恐惧、快乐、悲伤、惊讶）。

## 能力

### 基础能力
- 文本情绪识别
- 情绪维度评分
- Ekman 情绪映射

### 中级能力
- 上下文情绪分析
- 多轮对话情绪追踪
- 情绪趋势分析

### 高级能力
- 情绪强度量化
- 混合情绪识别
- 情绪变化检测

### 专家能力
- 自定义情绪模型
- 情绪预测
- 情绪干预建议

## 操作

### analyze

分析文本情绪并返回情绪评分。

**输入参数：**
- `text` (string, 必填): 待分析文本
- `user_id` (string, 必填): 用户标识
- `session_id` (string, 必填): 会话标识
- `language_hint` (string, 可选): 语言提示，如 zh/en
- `context_history` (array, 可选): 最近对话片段，用于上下文辅助

**输出：**
- `scores` (object): 情绪维度分数映射
- `ekman_scores` (object): Ekman 六类分数映射
- `top_emotions` (array): Top 情绪列表，包含 name 与 score
- `engagement_score` (number): 互动参与度评分

### update_config

更新情绪分析配置。

**输入参数：**
- `model_name` (string, 可选): 情绪模型名称
- `context_turns` (integer, 可选): 上下文轮数
- `context_max_chars` (integer, 可选): 上下文最大字符数
- `ekman_mapping_version` (string, 可选): 映射版本标识

**输出：**
- `status` (string): 更新状态
- `updated_fields` (array): 实际更新的字段列表

## 使用示例

```python
# 分析情绪
result = await skill_executor.execute(
    skill_name="emotion",
    operation="analyze",
    input_data={
        "text": "我今天很开心，因为考试得了满分！",
        "user_id": "user123",
        "session_id": "session456"
    }
)
```

## 注意事项

- 文本长度限制为 512 字符
- 支持中英文混合分析
- 上下文分析最多使用最近 3 轮对话
