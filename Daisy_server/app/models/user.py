from sqlalchemy import Column, Integer, String, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship as sa_relationship
from .base import Base

class UserDB(Base):
    """
    用户数据库模型
    存储用户的基本认证信息和状态。
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # 关联关系
    settings = sa_relationship("CommonSettingsDB", back_populates="user", uselist=False)
    profiles = sa_relationship("RoleProfileDB", back_populates="user")
    chat_history = sa_relationship("ChatHistoryDB", back_populates="user")

class RoleProfileDB(Base):
    """
    角色画像数据库模型
    存储角色的性格、风格、示例等详细设定。
    """
    __tablename__ = "role_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # nullable=True 为了向后兼容或模板
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=False)
    # 基础信息移到了 CommonSettingsDB
    style = Column(JSON, nullable=False)  # 存储为 JSON 列表
    constraints = Column(JSON, nullable=False)  # 存储为 JSON 列表

    user = sa_relationship("UserDB", back_populates="profiles")

from ..core.config import settings

class CommonSettingsDB(Base):
    """
    通用设置数据库模型
    存储用户的全局设置，包括角色基础信息、LLM 配置等。
    """
    __tablename__ = "common_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    name = Column(String, default="Android") # 角色名称
    gender = Column(String, nullable=True)
    age = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    relationship = Column(String, nullable=True, default="Friend") # 与用户的关系
    backstory = Column(Text, nullable=True)
    portrait = Column(Text, nullable=True) # 生成的角色头像 (Task 1 缓存)
    avatar_path = Column(Text, nullable=True) # AI 角色的头像路径(人格编辑器里上传)
    user_avatar_path = Column(Text, nullable=True) # 用户自己的头像路径(对话中右侧气泡)
    background_image_path = Column(Text, nullable=True) # 聊天背景图片路径
    world_setting = Column(Text, nullable=True)
    system_prompt_template = Column(Text, nullable=True) # 用户自定义/动态提示词模板
    core_system_prompt = Column(Text, nullable=True) # 静态/核心系统提示词
    
    # 深度角色卡存储 (JSON)
    # 存储 Phase 1 生成的 CharacterCard JSON 结构
    character_card_json = Column(JSON, nullable=True)

    # LLM 配置
    llm_provider = Column(String, default=settings.DEFAULT_LLM_PROVIDER) # openai, siliconflow, huaweicloud 等
    llm_api_key = Column(String, nullable=True)
    llm_base_url = Column(String, default=settings.DEFAULT_LLM_BASE_URL)
    llm_model_name = Column(String, default=settings.DEFAULT_LLM_MODEL_NAME) # 默认模型
    
    # Embedding 配置
    embedding_provider = Column(String, default=settings.EMBEDDING_PROVIDER)
    embedding_model_name = Column(String, default=settings.EMBEDDING_MODEL_NAME)
    
    # Local LLM 配置 (保留字段以防将来需要，但默认关闭)
    local_llm_use_gpu = Column(Boolean, default=False)
    local_llm_gpu_id = Column(Integer, default=0)
    task_summarize_use_local = Column(Boolean, default=False)

    @property
    def has_character_card(self) -> bool:
        return self.character_card_json is not None

    user = sa_relationship("UserDB", back_populates="settings")
