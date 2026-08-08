---
name: generation
version: 1.0.0
description: Core text generation capabilities using LLM
author: Daisy Team
license: MIT
category: core
tags:
  - generation
  - chat
  - llm
dependencies:
  - name: llm_service
    version: ">=1.0.0"
allowed_tools:
  - generation.chat
  - generation.generate
---

# Generation Skill

## 概述

Generation Skill 提供基于 LLM 的文本生成能力，支持对话、补全等模式。

## 操作

### chat

执行对话生成。

**输入参数：**
- `messages` (list, 可选): 消息历史列表 [{"role": "user", "content": "..."}]
- `system_prompt` (string, 可选): 系统提示词
- `user_input` (string, 可选): 用户当前输入 (如果提供了 messages，此项会被添加到末尾)
- `temperature` (float, 可选): 温度
- `max_tokens` (integer, 可选): 最大 token 数

**输出：**
- `content` (string): 生成的内容
- `role` (string): 角色 (assistant)
- `usage` (object): Token 使用情况

### generate

执行文本补全/生成。

**输入参数：**
- `prompt` (string, 必填): 提示词
- `temperature` (float, 可选): 温度

**输出：**
- `text` (string): 生成的文本
