import json
import structlog
from typing import Optional, Dict, Any
from .models import CharacterCard
from ....services.llm import get_llm_service

logger = structlog.get_logger()

class CharacterCardGenerator:
    def __init__(self):
        self.llm = get_llm_service()
    
    async def generate_deep_card(
        self,
        name: str,
        gender: str,
        age: int,
        occupation: str,
        backstory: str = "",
        world_setting: str = "Modern Realism",
        avatar_path: Optional[str] = None
    ) -> Optional[CharacterCard]:
        system_prompt = """
# Role: Deep Character Profiler & Novelist
你是一位擅长心理侧写的小说家。你的任务是将用户提供的简单人物设定（姓名、职业、年龄）扩写成一份具有文学深度、逻辑自洽的完整角色档案。

# Core Philosophy
1. **Anti-Cliché (反套路)**: 不要默认高官就是霸道，医生就是洁癖。寻找"意料之外，情理之中"的设定。
2. **Logical Deduction (逻辑推演)**: 每一个性格特征必须有来源 (Backstory)。如果他冷漠，是因为受过伤，还是天生迟钝？
3. **Complexity (复杂性)**: 人是矛盾的。为角色设计"表层面具"和"深层底色"的反差。

# Output Format
你必须输出一个符合特定 JSON Schema 的 JSON 对象。不要包含任何 Markdown 格式（如 ```json）。

# Schema Definition
{
  "identity": {
    "name": "...", "gender": "...", "age": 25, 
    "occupation": "...", "mbti": "..."
  },
  "personality": {
    "description": "...", "core_traits": ["..."]
  },
  "language_style": {
    "tone": "...", "quirks": ["..."], 
    "common_phrases": {
        "greeting": ["..."], 
        "agreement": ["..."], 
        "thinking": ["..."]
    }
  },
  "context": {
    "backstory": "...", "world_setting": "..."
  },
  "constraints": [
    {"type": "...", "description": "...", "coping_strategy": ["..."]}
  ],
  "behavior": {
    "push_pull_pattern": {
        "description": "...", 
        "pull_behaviors": ["..."], 
        "push_behaviors": ["..."]
    }
  },
  "relationship_dynamics": [
    {"level": 1, "name": "...", "description": "...", "prompt_addon": "..."}
  ],
  "dialogue_examples": [
    {"scene": "...", "user": "...", "agent": "..."}
  ],
  "inner_monologue_patterns": [
    {"emotion": "...", "pattern": "..."}
  ]
}
"""
        
        user_input = f"""
请基于以下种子信息生成角色卡：
- Name: {name}
- Gender: {gender}
- Age: {age}
- Occupation: {occupation}
- Backstory Hint: {backstory or "N/A"}
- World Setting: {world_setting}
"""
        
        try:
            response_text = await self.llm.generate_response_async(
                system_prompt=system_prompt,
                user_input=user_input,
                context="",
                metadata={"agent_name": "DeepCharacterGenerator"}
            )
            
            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            
            data = json.loads(json_str)
            
            if avatar_path and "identity" in data:
                data["identity"]["avatar_path"] = avatar_path

            card = CharacterCard(**data)
            logger.info(f"Generated deep character card for {name}")
            return card
            
        except Exception as e:
            logger.error(f"Failed to generate deep character card: {e}")
            return None
    
    async def generate_portrait(
        self,
        user_id: str,
        name: str,
        gender: str,
        age: int,
        occupation: str,
        backstory: str = "",
        world_setting: str = "Modern Realism"
    ) -> str:
        raw_info = f"""
Name: {name}
Gender: {gender}
Age: {age}
Occupation: {occupation}
World Setting: {world_setting}
Backstory: {backstory}
"""
        
        portrait_prompt = f"""
基于以下原始信息合成一个"角色画像"。

**原始信息**:
{raw_info}

**目标**:
创建一个简洁、整合的段落（约100-150字），捕捉角色的本质。
将事实（年龄、工作、学校）与背景故事中提到的个性特征和矛盾融合在一起。

**示例输出风格**:
"静雯是一位24岁的心理学家，生活在2025年的武汉。她将小镇出身的温柔与顶尖医学院的学术严谨相结合..."

用中文输出角色画像。
"""
        
        try:
            portrait = await self.llm.generate_response_async(
                system_prompt="你是一位专家级的人物画像分析师。",
                user_input=portrait_prompt,
                context="",
                metadata={"agent_name": "ProfileAgent", "user_id": user_id}
            )
            return portrait
        except Exception as e:
            logger.error(f"Failed to generate portrait: {e}")
            return f"{name} is a {age}-year-old {gender} {occupation}."
    
    def build_prompt_addendum(
        self,
        card: CharacterCard,
        route: str,
        user_input: str,
        relationship_stage: str
    ) -> str:
        route = (route or "").upper()
        name = card.identity.name
        
        if route == "FAST":
            core_concept = card.personality.description
            style = card.language_style.tone
            
            addendum = f"""# [Character Essence]
Name: {name}
Concept: {core_concept}
Style: {style}"""
            return addendum.strip()

        if route == "STANDARD":
            description = card.personality.description
            pattern = ""
            if card.behavior.push_pull_pattern:
                pattern = card.behavior.push_pull_pattern.description
                
            addendum = f"""# [Character Persona]
Description: {description}

# [Relationship Dynamics]
Pattern: {pattern}"""
            return addendum.strip()

        if route == "DEEP":
            constraints_list = [f"- {c.description}" for c in card.constraints]
            monologues = [f"- [{m.emotion}]: {m.pattern}" for m in card.inner_monologue_patterns]
            
            addendum = f"""# [Constraints]
{chr(10).join(constraints_list) if constraints_list else "(none)"}

# [Inner Monologue Patterns]
{chr(10).join(monologues) if monologues else "(none)"}"""
            return addendum.strip()

        return ""

character_generator = CharacterCardGenerator()
