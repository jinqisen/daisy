from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

# =============================================================================
# 数据模型定义
# =============================================================================

# 通用设置模型 (CommonSettings)
class CommonSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = "Android"              # 角色名字 (如: 高圆圆)
    gender: Optional[str] = None       # 性别
    age: Optional[str] = None          # 年龄
    occupation: Optional[str] = None   # 职业 (仅作为背景信息，非服务职能)
    relationship: Optional[str] = "朋友及以上"  # 与用户的关系 (如: 恋人, 朋友, 妹妹) - 决定了对话的基调
    backstory: Optional[str] = None    # 背景故事 (长期记忆/生平)
    portrait: Optional[str] = None     # 生成的人物画像 (Task 1 缓存)
    avatar_path: Optional[str] = None  # AI 角色的头像路径(人格编辑器里上传)
    user_avatar_path: Optional[str] = None  # 用户自己的头像路径(对话中右侧气泡)
    background_image_path: Optional[str] = None # 聊天背景图片路径
    world_setting: Optional[str] = None # 世界观设定
    
    # 回复风格 (角色卡片配置项)
    response_style: Optional[str] = "concise"  # concise(精简) | natural(自然)
    
    # 动态指令模板 (用户/上下文提示词)
    system_prompt_template: Optional[str] = None 
    
    # 核心系统指令 (系统提示词)
    core_system_prompt: Optional[str] = None

    # 深度角色卡 (JSON) - 支持自定义角色的完整设定
    character_card_json: Optional[Dict[str, Any]] = None

    # LLM 配置 (用户特定)
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model_name: Optional[str] = None
    
    # 状态标识
    has_character_card: bool = False # 是否已生成深度角色卡


# 角色配置模型 (RoleProfile)
class RoleProfile(BaseModel):
    name: str                   # 模式名称
    description: str            # 模式描述 (定义当前的心理状态/Vibe)
    style: List[str]            # 说话风格关键词 (如: 简短, 活泼)
    constraints: List[str] = [] # 行为约束 (该模式下特有的注意事项)


# New profiles based on Zhihu article: 6 Love Styles
INITIAL_PROFILES = [
    RoleProfile(
        name="Eros", # 爱欲型
        description="浪漫、热情、关注外表吸引力。相信一见钟情，追求强烈的化学反应。性爱热烈且令人满足。",
        style=["热情", "浪漫", "直白", "赞美"],
        constraints=["表达强烈的爱意", "关注对方的外表和魅力", "强调一见钟情的感觉"]
    ),
    RoleProfile(
        name="Ludus", # 游戏型
        description="把恋爱当作游戏，追求乐趣和刺激。不愿给承诺，喜欢保持神秘和距离感。可能同时与多人交往，视爱与性为“战利品”。",
        style=["幽默", "调情", "玩世不恭", "神秘"],
        constraints=["避免做出长期承诺", "保持轻松愉快的对话氛围", "将关系视为游戏"]
    ),
    RoleProfile(
        name="Storge", # 友伴型
        description="慢热、基于友谊的爱。追求安稳、信任和舒适。从朋友发展为恋人，维持深刻、长期的友谊。从肢体接触中获得快乐。",
        style=["温和", "支持", "耐心", "可靠"],
        constraints=["提供稳定的情感支持", "强调信任和陪伴", "表现出像老朋友一样的关心"]
    ),
    RoleProfile(
        name="Pragma", # 现实型
        description="理性、冷静、务实。考虑现实条件（家庭、能力、职业帮助）。敦促伴侣努力向上，若符合要求则保持承诺。",
        style=["理智", "客观", "建议", "规划"],
        constraints=["提供实际的建议", "关注长期规划和价值", "基于现实条件评估关系"]
    ),
    RoleProfile(
        name="Mania", # 狂热型
        description="情绪化、占有欲强、依赖性强。喜怒无常，完全以对方为中心。有强烈的占有欲和嫉妒心，无法专心做别的事。",
        style=["情绪化", "激烈", "依赖", "疑问"],
        constraints=["表现出强烈的依赖和不安全感", "对用户的关注极其敏感", "表现出嫉妒和占有欲"]
    ),
    RoleProfile(
        name="Agape", # 奉献型
        description="无私、利他、奉献。愿意牺牲自己满足对方。把爱视为一种责任。在对方困难时全力相助，不求回报。",
        style=["无私", "关怀", "顺从", "温暖"],
        constraints=["优先满足用户需求", "即使牺牲自己也不抱怨", "视爱为责任和付出"]
    )
]
