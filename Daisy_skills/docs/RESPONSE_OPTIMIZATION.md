# 响应速度优化说明

## 背景

Daisy 每次请求的 LLM 调用链路原本包含 4-5 次 LLM 调用，总延迟 12-28s。经 2026-08 对比测试，以下三次调用对回复质量影响极小，但显著增加延迟：

| 调用 | 作用 | 耗时 | 默认 |
|------|------|------|:----:|
| `_analyze_style` + `_agent_thoughts` | 动态生成沟通风格规则和内在思考 | +2-6s | **关闭** |
| `_refine_response` | 主 LLM 后的二次润色 | +2-5s | **关闭** |
| `_compress_response_to_limit` | 超 2 句时压缩（条件触发） | +1-2s | **关闭** |

## 测试结论

2026-08 对比测试（5 个典型场景 × 5 个方案，华为云 MAAS DeepSeek-V3.2）：

- 关闭动态分析 + refine 后，回复质量**无明显下降**，部分场景反而更自然
- 角色卡（Jingwen system prompt）已足够详细，模型能直接理解人设
- 平均延迟从 ~57s 降至 ~17s（**降低 70%**）

## 开关配置

三个开关位于 `config.py`（或通过同名环境变量设置）：

```python
# 默认全部关闭（快速模式）
ENABLE_DYNAMIC_STYLE_ANALYSIS = False  # _analyze_style + _agent_thoughts
ENABLE_REFINE_RESPONSE = False         # _refine_response
ENABLE_COMPRESS_RESPONSE = False       # _compress_response_to_limit
```

### 回滚方式

如需恢复完整链路，在 `.env` 中设置：

```bash
ENABLE_DYNAMIC_STYLE_ANALYSIS=true
ENABLE_REFINE_RESPONSE=true
ENABLE_COMPRESS_RESPONSE=true
```

或直接修改 `config.py` 中对应 `Field` 的默认值改为 `True`。

### 渐进式开启

也可以只开启部分，例如只保留 refine 但关闭动态分析：

```bash
ENABLE_DYNAMIC_STYLE_ANALYSIS=false
ENABLE_REFINE_RESPONSE=true
ENABLE_COMPRESS_RESPONSE=false
```

## 代码变更

- **config.py**: 新增 3 个 `Field(bool)` 开关
- **generation.py**: 6 处 `if settings.ENABLE_XXX:` 守卫，不删除原代码
- **state.py**: 新增 `emotion_data` 字段（消除 emotion 重复分析）

## 相关文件

- `app/core/config.py` — 开关定义
- `app/workflow/nodes/generation.py` — 守卫逻辑
- `app/workflow/state.py` — emotion 去重
- `app/workflow/graph.py` — emotion 结果存入 state

## 补充：`_analyze_style` + `_agent_thoughts` 合并

### 背景

原是两次独立 LLM 调用（`_analyze_style` 生成风格规则，`_agent_thoughts` 生成意图/策略/边界）。经 2026-08 对照测试，合并为一次调用（`_analyze_context`）后：

- 输出更简洁结构化，不会被 max_tokens 截断
- 拆分可靠性 100%（`【风格规则】` / `【内在思考】` 标记）
- 每次开启时节省 1 次 API roundtrip（~30-50%）

### 合并函数

`_analyze_context(user_input, history, context_data) -> (style_rules, agent_thoughts)`

位于 `generation.py` 第 201 行。原 `_analyze_style` 和 `_agent_thoughts` 函数保留但不再调用。

### 回滚

恢复为两次独立调用：将 `_collect_context` 中的 `_analyze_context` 调用改回分别调用 `_analyze_style` 和 `_agent_thoughts` 即可。
