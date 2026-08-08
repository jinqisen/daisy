---
name: topic
version: 1.0.0
description: 话题摘要与上下文管理能力，支持对话话题识别和摘要生成
author: Daisy Team
license: MIT
category: analysis
tags:
  - topic
  - summary
  - context
  - conversation
dependencies: []
allowed_tools:
  - topic.summarize
  - topic.detect
  - topic.track
---

# Topic Skill

## 概述

Topic Skill 提供话题摘要和上下文管理能力，能够识别对话中的主要话题，生成话题摘要，并追踪话题变化。

## 能力

### 基础能力
- 话题摘要生成
- 对话上下文压缩
- 话题识别

### 中级能力
- 多话题追踪
- 话题切换检测
- 话题相关性分析

### 高级能力
- 话题聚类
- 话题演化追踪
- 话题意图识别

### 专家能力
- 自定义话题模型
- 话题预测
- 话题干预建议

## 操作

### summarize

生成对话话题摘要。

**输入参数：**
- `history` (array, 必填): 对话历史片段
- `latest_message` (string, 必填): 当前消息
- `session_id` (string, 必填): 会话标识
- `max_tokens` (integer, 可选): 摘要最大长度
- `language_hint` (string, 可选): 语言提示

**输出：**
- `summary` (string): 话题摘要
- `session_id` (string): 会话标识
- `topic_tags` (array): 话题标签
- `confidence` (number): 摘要置信度

### detect

检测对话中的主要话题。

**输入参数：**
- `messages` (array, 必填): 消息列表
- `session_id` (string, 必填): 会话标识

**输出：**
- `topics` (array): 检测到的话题列表
- `primary_topic` (string): 主要话题
- `confidence` (number): 检测置信度

### track

追踪话题变化。

**输入参数：**
- `session_id` (string, 必填): 会话标识
- `current_message` (string, 必填): 当前消息
- `previous_topic` (string, 可选): 前一个话题

**输出：**
- `current_topic` (string): 当前话题
- `topic_changed` (boolean): 话题是否变化
- `change_confidence` (number): 变化置信度

## 使用示例

```python
# 生成话题摘要
result = await skill_executor.execute(
    skill_name="topic",
    operation="summarize",
    input_data={
        "history": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么我可以帮助你的吗？"}
        ],
        "latest_message": "我想了解人工智能",
        "session_id": "session456"
    }
)
```

## 注意事项

- 摘要长度默认限制为 400 字符
- 支持中英文话题识别
- 话题追踪基于语义相似度
