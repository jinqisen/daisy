# DESIGN: 节假日感知架构设计

## 1. 核心模块: `app/core/holidays.py`

```python
class HolidayManager:
    # 公历节日 (MM-DD)
    SOLAR_HOLIDAYS = {
        "01-01": "元旦",
        "02-14": "情人节",
        "03-08": "妇女节",
        "04-01": "愚人节",
        "05-01": "劳动节",
        "05-04": "青年节",
        "05-20": "520情人节",
        "06-01": "儿童节",
        "07-01": "建党节",
        "08-01": "建军节",
        "09-10": "教师节",
        "10-01": "国庆节",
        "10-31": "万圣节前夜",
        "11-11": "光棍节",
        "12-24": "平安夜",
        "12-25": "圣诞节",
    }

    # 农历节日 (YYYY-MM-DD, 预置)
    LUNAR_HOLIDAYS = {
        # 2024 (龙年)
        "2024-02-09": "除夕",
        "2024-02-10": "春节",
        "2024-02-24": "元宵节",
        "2024-04-04": "清明节", # 清明通常按阳历算，但每年略有不同，这里作为特例
        "2024-06-10": "端午节",
        "2024-08-10": "七夕节",
        "2024-09-17": "中秋节",
        "2024-10-11": "重阳节",
        
        # 2025 (蛇年)
        "2025-01-28": "除夕",
        "2025-01-29": "春节",
        "2025-02-12": "元宵节",
        "2025-04-04": "清明节",
        "2025-05-31": "端午节",
        "2025-08-29": "七夕节",
        "2025-10-06": "中秋节",
        "2025-10-29": "重阳节",

         # 2026 (马年) - 补充常见
        "2026-02-16": "除夕",
        "2026-02-17": "春节",
        "2026-06-19": "端午节",
        "2026-09-25": "中秋节",
    }

    @staticmethod
    def get_holiday(date_obj) -> str | None:
        # 1. 查农历表 (优先级高)
        date_str = date_obj.strftime("%Y-%m-%d")
        if date_str in HolidayManager.LUNAR_HOLIDAYS:
            return HolidayManager.LUNAR_HOLIDAYS[date_str]
        
        # 2. 查公历表
        md_str = date_obj.strftime("%m-%d")
        if md_str in HolidayManager.SOLAR_HOLIDAYS:
            return HolidayManager.SOLAR_HOLIDAYS[md_str]
            
        return None
```

## 2. 集成设计
- 在 `app/workflow/nodes/generation.py` 的 `_generate_costar_instruction` 中：
    - 调用 `HolidayManager.get_holiday(now)`。
    - 如果有节日，注入 Context 和 Constraint。

## 3. Prompt 模板变更
- **Context**: `当前时间：2024-12-25 (圣诞节) (深夜)`
- **Constraint**:
    ```
    - **节日感知**：今天是 **{holiday}**。
      * 请在回复中自然地融入节日氛围（如祝福、询问过节计划）。
      * 注意不要每一句都重复节日快乐，保持自然。
    ```
