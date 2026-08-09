"""
默认通用设置的装载(default_settings.json)。

从 core/config.py 拆出:它读的是**角色/用户的默认人设**,属于种子数据,
与"进程如何取得配置"是两件事。core 不该认识"用户性别""默认人设"这类概念。
"""

import json
import logging
import os

# <root>/Daisy_server
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def load_default_settings(user_gender: str = "male") -> dict:
    """
    加载默认的用户/角色通用设置。
    从 default_settings.json 加载。
    """
    try:
        base_dir = _base_dir
        settings_path = os.path.join(base_dir, "default_settings.json")
        
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # 检查是否是新的多模板结构
                if user_gender in data:
                    return data[user_gender]
                
                # 兼容旧的单层结构 (视为默认 male 模板)
                if "name" in data:
                     return data
                     
                # 如果找不到对应性别的模板，尝试使用 'male' 作为默认
                if "male" in data:
                    return data["male"]
    except Exception as e:
        logging.warning(f"Failed to load default_settings.json: {e}")
        
    # Minimal fallback to avoid crash, but encourages using the file
    return {
        "name": "Default",
        "gender": "Unknown",
        "core_system_prompt": "Please configure default_settings.json"
    }
