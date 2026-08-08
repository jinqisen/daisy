from typing import List, Dict, Optional, Literal, Union
from pydantic import BaseModel, Field

# =============================================================================
# 1. 核心身份 (Identity)
# =============================================================================

class Identity(BaseModel):
    name: str = Field(..., description="姓名")
    gender: str = Field(..., description="性别")
    age: int = Field(..., description="年龄")
    occupation: str = Field(..., description="职业")
    mbti: Optional[str] = Field(None, description="MBTI人格类型")
    avatar_path: Optional[str] = Field(None, description="头像路径")

# =============================================================================
# 2. 核心人格 (Personality)
# =============================================================================

class Personality(BaseModel):
    description: str = Field(..., description="人格描述")
    core_traits: List[str] = Field(default_factory=list, description="核心特质")

# =============================================================================
# 3. 语言风格 (Language Style)
# =============================================================================

class LanguageStyle(BaseModel):
    tone: str = Field(..., description="语气/基调")
    quirks: List[str] = Field(default_factory=list, description="口癖/习惯")
    common_phrases: Dict[str, List[str]] = Field(default_factory=dict, description="常用语 (greeting, agreement, thinking)")

# =============================================================================
# 4. 背景与世界观 (Context)
# =============================================================================

class Context(BaseModel):
    backstory: str = Field(..., description="背景故事")
    world_setting: str = Field(..., description="世界观设定")

# =============================================================================
# 5. 约束 (Constraints)
# =============================================================================

class Constraint(BaseModel):
    type: str = Field(..., description="约束类型")
    description: str = Field(..., description="约束描述")
    coping_strategy: Optional[List[str]] = Field(None, description="应对策略")

# =============================================================================
# 6. 行为模式 (Behavior)
# =============================================================================

class PushPullPattern(BaseModel):
    description: str = Field(..., description="拉扯模式描述")
    pull_behaviors: List[str] = Field(default_factory=list, description="拉近行为")
    push_behaviors: List[str] = Field(default_factory=list, description="推开行为")

class Behavior(BaseModel):
    push_pull_pattern: Optional[PushPullPattern] = Field(None, description="极致拉扯模式")

# =============================================================================
# 7. 关系动态 (Relationship Dynamics)
# =============================================================================

class RelationshipDynamic(BaseModel):
    level: int = Field(..., description="关系等级")
    name: str = Field(..., description="阶段名称")
    description: str = Field(..., description="阶段描述")
    prompt_addon: str = Field(..., description="Prompt补充指令")

# =============================================================================
# 8. 对话示例 (Dialogue Examples)
# =============================================================================

class DialogueExample(BaseModel):
    scene: str = Field(..., description="场景")
    user: str = Field(..., description="用户输入")
    agent: str = Field(..., description="Agent回复")

# =============================================================================
# 9. 内心独白模式 (Inner Monologue Patterns)
# =============================================================================

class InnerMonologuePattern(BaseModel):
    emotion: str = Field(..., description="情绪状态")
    pattern: str = Field(..., description="独白模式")

# =============================================================================
# Main Card (Spec v3.1 Structure)
# =============================================================================

class CharacterCard(BaseModel):
    version: str = "2.0"
    identity: Identity
    personality: Personality
    language_style: LanguageStyle
    context: Context
    constraints: List[Constraint] = Field(default_factory=list)
    behavior: Behavior
    relationship_dynamics: List[RelationshipDynamic] = Field(default_factory=list)
    dialogue_examples: List[DialogueExample] = Field(default_factory=list)
    inner_monologue_patterns: List[InnerMonologuePattern] = Field(default_factory=list)
