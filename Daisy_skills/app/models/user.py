from sqlalchemy import Column, Integer, String, Boolean, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship as sa_relationship
from .base import Base
from ..core.config import settings

class UserDB(Base):
    """
    User Database Model
    Stores basic user authentication info and status.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # Relationships
    settings = sa_relationship("CommonSettingsDB", back_populates="user", uselist=False)
    profiles = sa_relationship("RoleProfileDB", back_populates="user")
    chat_history = sa_relationship("ChatHistoryDB", back_populates="user")

class RoleProfileDB(Base):
    """
    Role Profile Database Model
    Stores detailed role settings like personality, style, examples.
    """
    __tablename__ = "role_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=False)
    style = Column(JSON, nullable=False)  # Stored as JSON list
    constraints = Column(JSON, nullable=False)  # Stored as JSON list

    user = sa_relationship("UserDB", back_populates="profiles")

class CommonSettingsDB(Base):
    """
    Common Settings Database Model
    Stores user global settings, including role basics and LLM config.
    """
    __tablename__ = "common_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)
    name = Column(String, default="Android") # Role name
    gender = Column(String, nullable=True)
    age = Column(String, nullable=True)
    occupation = Column(String, nullable=True)
    relationship = Column(String, nullable=True, default="Friend")
    backstory = Column(Text, nullable=True)
    portrait = Column(Text, nullable=True)
    avatar_path = Column(Text, nullable=True)
    background_image_path = Column(Text, nullable=True)
    world_setting = Column(Text, nullable=True)
    system_prompt_template = Column(Text, nullable=True)
    core_system_prompt = Column(Text, nullable=True)
    
    # Deep Character Card Storage (JSON)
    character_card_json = Column(JSON, nullable=True)

    # LLM Config
    llm_provider = Column(String, default=settings.DEFAULT_LLM_PROVIDER)
    llm_api_key = Column(String, nullable=True)
    llm_base_url = Column(String, default=settings.DEFAULT_LLM_BASE_URL)
    llm_model_name = Column(String, default=settings.DEFAULT_LLM_MODEL_NAME)
    
    # Embedding Config
    embedding_provider = Column(String, default=settings.EMBEDDING_PROVIDER)
    embedding_model_name = Column(String, default=settings.EMBEDDING_MODEL_NAME)
    
    # Local LLM Config
    local_llm_use_gpu = Column(Boolean, default=False)
    local_llm_gpu_id = Column(Integer, default=0)
    task_summarize_use_local = Column(Boolean, default=False)

    @property
    def has_character_card(self) -> bool:
        return self.character_card_json is not None

    user = sa_relationship("UserDB", back_populates="settings")
