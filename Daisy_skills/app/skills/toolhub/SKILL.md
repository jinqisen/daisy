---
name: toolhub
version: 1.0.0
description: 对外工具封装能力，支持搜索、计算等外部工具调用
author: Daisy Team
license: MIT
category: tools
tags:
  - tools
  - search
  - calculation
  - external
dependencies: []
allowed_tools:
  - toolhub.search
  - toolhub.calculate
  - toolhub.weather
---

# ToolHub Skill

## 概述

ToolHub Skill 提供对外工具封装能力，支持网络搜索、数学计算等外部工具调用，为对话系统提供扩展能力。

## 能力

### 基础能力
- 网络搜索
- 数学计算
- 基础工具调用

### 中级能力
- 搜索结果过滤
- 计算表达式验证
- 工具结果缓存

### 高级能力
- 多工具组合
- 工具链执行
- 工具结果聚合

### 专家能力
- 自定义工具注册
- 工具性能优化
- 工具错误恢复

## 操作

### search

执行网络搜索。

**输入参数：**
- `query` (string, 必填): 搜索关键词
- `top_k` (integer, 可选): 返回数量，默认 5
- `locale` (string, 可选): 地域/语言

**输出：**
- `results` (array): 搜索结果列表
- `query_used` (string): 实际搜索词
- `total_count` (integer): 结果总数

### calculate

计算数学表达式。

**输入参数：**
- `expression` (string, 必填): 数学表达式

**输出：**
- `value` (string): 计算结果
- `expression` (string): 原始表达式

### weather

查询天气信息。

**输入参数：**
- `location` (string, 必填): 地点名称
- `days` (integer, 可选): 查询天数，默认 1

**输出：**
- `weather` (object): 天气信息
- `location` (string): 查询地点

## 使用示例

```python
# 网络搜索
result = await skill_executor.execute(
    skill_name="toolhub",
    operation="search",
    input_data={
        "query": "人工智能最新进展",
        "top_k": 5
    }
)

# 数学计算
result = await skill_executor.execute(
    skill_name="toolhub",
    operation="calculate",
    input_data={
        "expression": "2 + 3 * 4"
    }
)
```

## 注意事项

- 搜索功能需要配置 API 密钥
- 计算表达式仅支持基本数学运算
- 工具调用可能有网络延迟
