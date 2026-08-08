from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class Identity(BaseModel):
    name: str
    gender: str
    age: int
    occupation: str
    mbti: Optional[str] = None
    avatar_path: Optional[str] = None

class Personality(BaseModel):
    description: str
    core_traits: List[str]

class LanguageStyle(BaseModel):
    tone: str
    quirks: List[str]
    common_phrases: Dict[str, List[str]]

class Context(BaseModel):
    backstory: str
    world_setting: str

class Constraint(BaseModel):
    type: str
    description: str
    coping_strategy: List[str]

class PushPullPattern(BaseModel):
    description: str
    pull_behaviors: List[str]
    push_behaviors: List[str]

class Behavior(BaseModel):
    push_pull_pattern: PushPullPattern

class RelationshipDynamic(BaseModel):
    level: int
    name: str
    description: str
    prompt_addon: str

class DialogueExample(BaseModel):
    scene: str
    user: str
    agent: str

class InnerMonologuePattern(BaseModel):
    emotion: str
    pattern: str

class CharacterCard(BaseModel):
    identity: Identity
    personality: Personality
    language_style: LanguageStyle
    context: Context
    constraints: List[Constraint]
    behavior: Behavior
    relationship_dynamics: List[RelationshipDynamic]
    dialogue_examples: List[DialogueExample]
    inner_monologue_patterns: List[InnerMonologuePattern]
