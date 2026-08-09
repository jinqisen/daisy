"""
注册白名单:谁有资格注册这个服务。

从 core/config.py 拆出,因为这是**业务规则**而非基础设施 ——
core 的判断标准是"不含任何业务概念,换个产品也能用",白名单显然不符合。

另:Settings 里原有 `ALLOWED_USERS` / `SUPERUSERS` 两个字段,在**类定义时**
就调用 load_whitelist() 固化了内容。两个问题——全库零使用者,
且即便有人用,管理接口改完白名单后它们也不会更新。已一并删除。
"""

import json
import logging
import os

# 后端根目录用共享常量 —— 数 dirname 层数的写法会被文件移动静默改坏
# (init_data.py 就这样在本轮拆分中指向了错误目录,见 tests/test_path_resolution.py)
from app.core.paths import SERVER_DIR

_base_dir = SERVER_DIR


def load_whitelist() -> dict:
    """
    加载白名单配置。
    返回一个包含 'users' (允许的用户名列表或对象列表) 和 'admins' (超级用户列表) 的字典。
    """
    try:
        base_dir = _base_dir
        whitelist_path = os.path.join(base_dir, "whitelist.json")
        
        if os.path.exists(whitelist_path):
            with open(whitelist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    # 向后兼容：所有用户视为普通用户，管理员硬编码或在其他地方处理
                    return {"users": data, "admins": ["admin"]}
                return data
        return {"users": ["admin", "test_user"], "admins": ["admin"]}
    except Exception as e:
        # 使用标准日志记录，因为 structlog 可能尚未配置
        logging.warning(f"Failed to load whitelist.json: {e}")
        return {"users": ["admin", "test_user"], "admins": ["admin"]}

def save_whitelist(data: dict) -> bool:
    """
    保存白名单配置到 whitelist.json。
    """
    try:
        base_dir = _base_dir
        whitelist_path = os.path.join(base_dir, "whitelist.json")
        
        with open(whitelist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logging.error(f"Failed to save whitelist.json: {e}")
        return False
