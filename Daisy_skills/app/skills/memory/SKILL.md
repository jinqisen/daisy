---
name: memory
version: 1.0.0
description: 向量记忆检索与写入能力，支持短期和长期记忆管理
author: Daisy Team
license: MIT
category: storage
tags:
  - memory
  - storage
  - retrieval
  - vector
dependencies: []
allowed_tools:
  - memory.search
  - memory.add
  - memory.update_policy
---

# Memory Skill

## 概述

Memory Skill 提供记忆存储和检索能力，支持短期和长期记忆管理，能够根据查询内容检索相关记忆，并支持去重写入。

## 能力

### 基础能力
- 记忆写入
- 记忆检索
- 去重机制

### 中级能力
- 短期/长期记忆分离
- 相似度阈值控制
- 元数据过滤

### 高级能力
- 向量相似度检索
- 记忆聚合
- 记忆过期管理

### 专家能力
- 自定义检索策略
- 记忆压缩
- 记忆迁移

## 操作

### search

根据查询内容检索相关记忆。

**输入参数：**
- `query` (string, 必填): 检索查询内容
- `user_id` (string, 必填): 用户标识
- `limit` (integer, 可选): 返回条数上限，默认 5
- `topic_summary` (string, 可选): 当前话题摘要
- `session_id` (string, 可选): 会话标识
- `filters` (object, 可选): 过滤条件，如时间范围或标签

**输出：**
- `memories` (array): 记忆列表，包含 text、score、metadata
- `query_used` (string): 实际执行的查询文本
- `total_count` (integer): 匹配的总数量

### add

写入新的记忆。

**输入参数：**
- `text` (string, 必填): 写入记忆文本
- `user_id` (string, 必填): 用户标识
- `metadata` (object, 可选): 结构化元数据
- `session_id` (string, 可选): 会话标识
- `memory_type` (string, 可选): 记忆类型，如 short/long

**输出：**
- `success` (boolean): 是否成功写入
- `dedup_key` (string): 去重键
- `message` (string): 结果消息

### update_policy

更新记忆策略配置。

**输入参数：**
- `short_term_k` (integer, 可选): 短期检索数量
- `long_term_k` (integer, 可选): 长期检索数量
- `similarity_threshold` (number, 可选): 相似度阈值
- `write_strategy` (string, 可选): 写入策略，如 append/merge

**输出：**
- `status` (string): 更新状态
- `updated_fields` (array): 实际更新的字段列表
- `current_policy` (object): 当前策略配置

## 使用示例

```python
# 添加记忆
result = await skill_executor.execute(
    skill_name="memory",
    operation="add",
    input_data={
        "text": "用户喜欢编程和人工智能",
        "user_id": "user123",
        "session_id": "session456",
        "metadata": {"topic": "interests"}
    }
)

# 检索记忆
result = await skill_executor.execute(
    skill_name="memory",
    operation="search",
    input_data={
        "query": "编程",
        "user_id": "user123",
        "limit": 5
    }
)
```

## 注意事项

- 记忆写入会自动去重，相同内容不会重复存储
- 检索结果按相似度排序
- 支持元数据过滤和查询
