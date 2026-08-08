---
name: portrait
version: 1.0.0
description: 角色画像与角色卡生成能力，支持基于对话历史的角色画像构建
author: Daisy Team
license: MIT
category: generation
tags:
  - portrait
  - character
  - profile
  - generation
dependencies: []
allowed_tools:
  - portrait.generate
  - portrait.update
  - portrait.get
---

# Portrait Skill

## 概述

Portrait Skill 提供角色画像和角色卡生成能力，能够根据对话历史和配置信息生成角色画像描述和结构化角色卡。

## 能力

### 基础能力
- 角色画像生成
- 角色卡构建
- 基础信息提取

### 中级能力
- 对话历史分析
- 个性化画像
- 风格适配

### 高级能力
- 多维度画像
- 画像演化
- 画像对比

### 专家能力
- 自定义画像模型
- 画像预测
- 画像干预建议

## 操作

### generate

生成角色画像和角色卡。

**输入参数：**
- `user_id` (string, 必填): 用户标识
- `common_settings` (object, 必填): 画像与角色生成配置
- `history` (array, 可选): 最近对话片段
- `persona_id` (string, 可选): 指定人格标识

**输出：**
- `portrait_text` (string): 画像描述文本
- `character_card` (object): 角色卡结构化数据
- `metadata` (object): 元数据信息

### update

更新角色画像配置。

**输入参数：**
- `user_id` (string, 必填): 用户标识
- `settings` (object, 必填): 更新的配置信息

**输出：**
- `status` (string): 更新状态
- `updated_fields` (array): 实际更新的字段列表

### get

获取角色画像信息。

**输入参数：**
- `user_id` (string, 必填): 用户标识

**输出：**
- `portrait` (object): 角色画像信息

## 使用示例

```python
# 生成角色画像
result = await skill_executor.execute(
    skill_name="portrait",
    operation="generate",
    input_data={
        "user_id": "user123",
        "common_settings": {
            "name": "Daisy",
            "relationship": "friend",
            "style": ["friendly", "helpful"]
        },
        "history": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么我可以帮助你的吗？"}
        ]
    }
)
```

## 注意事项

- 角色画像基于对话历史和配置信息生成
- 支持自定义角色名称、关系和风格
- 角色卡包含结构化的角色信息
