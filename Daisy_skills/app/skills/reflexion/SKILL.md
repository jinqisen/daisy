---
name: reflexion
version: 1.0.0
description: Reflexion 学习系统，通过对话质量评估和用户反馈实现自我进化
author: Daisy Team
license: MIT
category: learning
tags:
  - reflexion
  - learning
  - self-improvement
  - metrics
dependencies:
  - name: emotion
    version: ">=1.0.0"
  - name: memory
    version: ">=1.0.0"
allowed_tools:
  - reflexion.enqueue_event
  - reflexion.get_metrics
  - reflexion.get_patches
  - reflexion.retrieve_exemplars
resources:
  - type: script
    name: enqueue_event
    path: scripts/enqueue_event.py
  - type: script
    name: get_metrics
    path: scripts/get_metrics.py
  - type: script
    name: get_patches
    path: scripts/get_patches.py
  - type: script
    name: retrieve_exemplars
    path: scripts/retrieve_exemplars.py
---

# Reflexion 学习系统

## 概述
Reflexion 是一个异步学习系统，通过分析对话质量、用户参与度和关系深度，实现 AI 伴侣的自我进化。

## 核心能力

### 1. 对话质量评估 (Q_I)
- 评估回复的情感一致性
- 检测回复的连贯性
- 计算回复的多样性

### 2. 用户参与度评估 (E_U)
- 分析用户回复长度
- 计算响应时间
- 检测情感提升

### 3. 关系深度评估 (D_R)
- 统计会话频率
- 计算留存率
- 追踪记忆更新

### 4. 自我进化机制
- 高质量对话 → 存储为范例 (RAG)
- 低质量对话 → 生成指令补丁

## 操作定义

### enqueue_event
将对话事件加入 Reflexion 处理队列。

**输入参数:**
```json
{
  "user_id": "string",
  "session_id": "string",
  "user_input": "string",
  "agent_response": "string",
  "agent_emotion": {
    "joy": 0.8,
    "sadness": 0.1
  },
  "target_emotion": {
    "joy": 0.7,
    "sadness": 0.2
  },
  "user_emotion": {
    "joy": 0.6,
    "sadness": 0.3
  },
  "history": ["string"]
}
```

**输出结果:**
```json
{
  "success": true,
  "message": "Event enqueued successfully",
  "queue_size": 5
}
```

### get_metrics
获取用户的 Reflexion 指标。

**输入参数:**
```json
{
  "user_id": "string",
  "session_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "metrics": {
    "Q_I": 0.85,
    "E_U": 0.72,
    "D_R": 0.90,
    "S_total": 0.82
  }
}
```

### get_patches
获取用户的活跃指令补丁。

**输入参数:**
```json
{
  "user_id": "string"
}
```

**输出结果:**
```json
{
  "success": true,
  "patches": {
    "global": [
      "避免使用过于正式的语言"
    ],
    "personal": [
      "用户偏好简洁的回复",
      "用户不喜欢过多的表情符号"
    ]
  }
}
```

### retrieve_exemplars
检索相似的高质量对话范例。

**输入参数:**
```json
{
  "query_text": "string",
  "limit": 3
}
```

**输出结果:**
```json
{
  "success": true,
  "exemplars": [
    {
      "text": "用户输入示例",
      "agent_response": "AI 回复示例",
      "score": 0.92,
      "metadata": {}
    }
  ]
}
```

## 使用示例

```python
# 在对话流程中集成 Reflexion
from runtime.orchestrator import SkillOrchestrator

orchestrator = SkillOrchestrator()

# 对话完成后，将事件加入 Reflexion 队列
await orchestrator.execute(
    skill="reflexion",
    operation="enqueue_event",
    input={
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
        "agent_response": agent_response,
        "agent_emotion": agent_emotion,
        "target_emotion": target_emotion,
        "user_emotion": user_emotion,
        "history": history
    }
)

# 获取指令补丁用于生成
patches_result = await orchestrator.execute(
    skill="reflexion",
    operation="get_patches",
    input={"user_id": user_id}
)
```

## 配置要求

- Redis: 用于存储待处理的 Reflexion 事件 (TTL 24h)
- Qdrant: 用于存储高质量对话范例 (向量检索)
- 数据库: 用于存储 Reflexion 日志和补丁记录

## 性能指标

- 队列处理延迟: < 5s
- 指标计算延迟: < 1s
- 向量检索延迟: < 500ms
