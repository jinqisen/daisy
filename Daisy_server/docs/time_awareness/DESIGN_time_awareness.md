# DESIGN: 时间感知能力架构设计

## 1. 核心逻辑流
```mermaid
graph TD
    A[开始生成回复] --> B[获取 Common Settings & State]
    B --> C[生成 Task 1-4 输出 (Portrait, Style, OS, History)]
    C --> D{获取当前系统时间}
    D --> E[计算时间段描述 (Time of Day)]
    E --> F[构建增强版 CO-STAR Prompt]
    F --> G[注入隐性约束层 (Constraint Layer)]
    G --> H[调用 LLM 生成回复]
```

## 2. Prompt 设计细节

### 2.1 时间计算函数
在 `generation.py` 中新增 `_get_time_context()` 辅助函数：
```python
def _get_time_context() -> dict:
    now = datetime.now()
    hour = now.hour
    
    if 0 <= hour < 5: period = "深夜"
    elif 5 <= hour < 9: period = "清晨"
    elif 9 <= hour < 12: period = "上午"
    elif 12 <= hour < 14: period = "中午"
    elif 14 <= hour < 18: period = "下午"
    elif 18 <= hour < 23: period = "晚上"
    else: period = "深夜"
    
    return {
        "str": now.strftime("%Y-%m-%d %H:%M"),
        "period": period,
        "hour": hour
    }
```

### 2.2 CO-STAR 模板变更

**Location**: `_generate_costar_instruction`

**Change**:

在 `## C (Context)` 下添加：
```
当前时间：{time_str} ({time_period})
```

在 `## O (Objective) -> 2. 隐性约束层` 下添加：
```
   - **时间感知**：当前是 **{time_period}** ({time_str})。
     * 你的建议必须符合当前作息规律（例如：深夜不建议喝咖啡/剧烈运动，应建议休息）。
     * 你的语气应适配当前时间氛围（例如：深夜更轻柔私密，清晨更清新活力）。
```

## 3. 接口变动
无外部 API 变动。仅内部 `_generate_costar_instruction` 函数签名可能不需要变动（时间在函数内部获取），或者传入 `time_info`。为保持纯函数特性，建议在函数内部获取，或者作为参数传入。鉴于 `generation.py` 已经是 `async` 且依赖 `state`，直接在函数内获取最简单。

## 4. 异常处理
- 获取时间失败：默认不显示时间或默认为“白天”，不阻断流程。
