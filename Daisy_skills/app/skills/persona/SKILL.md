---
name: persona
version: 1.0.0
description: 人格选择与目标情绪输出能力，支持基于情绪分析的人格匹配
author: Daisy Team
license: MIT
category: personality
tags:
  - persona
  - personality
  - emotion
  - character
dependencies: []
allowed_tools:
  - persona.select
  - persona.update_strategy
  - persona.build_system_prompt
  - persona.get_profile
---

# Persona Skill

## 概述

Persona Skill 提供人格选择和角色画像能力，能够根据用户的情绪状态选择合适的人格，并生成相应的系统提示词。

## 能力

### 基础能力
- 人格选择
- 情绪到人格映射
- 目标情绪输出

### 中级能力
- 人格权重分配
- 上下文感知选择
- 策略模式切换

### 高级能力
- 自定义人格配置
- 人格组合
- 动态人格调整

### 专家能力
- 人格学习
- 人格演化
- 多人格管理

## 操作

### select

根据情绪分析结果选择合适的人格。

**输入参数：**
- `user_id` (string, 必填): 用户标识
- `emotion_scores` (object, 必填): 情绪分析结果
- `ekman_scores` (object, 可选): Ekman 映射结果
- `mode` (string, 可选): 选择策略，如 rule/llm
- `context_summary` (string, 可选): 上下文摘要

**输出：**
- `selected_personality` (string): 选定人格标识
- `weights` (object): 人格权重分配
- `target_emotion` (string): 目标情绪输出
- `metadata` (object): 决策元信息

### update_strategy

更新人格选择策略。

**输入参数：**
- `mode` (string, 可选): 选择策略
- `weight_overrides` (object, 可选): 权重覆盖配置

**输出：**
- `status` (string): 更新状态
- `updated_fields` (array): 实际更新的字段列表
- `current_strategy` (object): 当前策略配置

### build_system_prompt

构建人格化的系统提示词。

**输入参数：**
- `persona_id` (string, 必填): 人格标识
- `core_system_prompt` (string, 必填): 核心系统提示词
- `metadata` (object, 可选): 额外元数据

**输出：**
- `system_prompt` (string): 构建的系统提示词
- `persona_info` (object): 人格信息

### get_profile

获取人格配置信息。

**输入参数：**
- `persona_id` (string, 必填): 人格标识

**输出：**
- `profile` (object): 人格配置信息

## 使用示例

```python
# 选择人格
result = await skill_executor.execute(
    skill_name="persona",
    operation="select",
    input_data={
        "user_id": "user123",
        "emotion_scores": {"joy": 0.8, "sadness": 0.1, "anger": 0.1},
        "mode": "rule"
    }
)

# 构建系统提示词
result = await skill_executor.execute(
    skill_name="persona",
    operation="build_system_prompt",
    input_data={
        "persona_id": "cheerful",
        "core_system_prompt": "You are a helpful assistant."
    }
)
```

## 注意事项

- 支持的人格类型：neutral, cheerful, comfort, calm, supportive, curious, gentle
- 默认使用规则模式进行人格选择
- 人格选择基于情绪分析结果
