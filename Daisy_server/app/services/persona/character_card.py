import os
import json
from typing import Optional
import structlog
from app.core.config import settings
from app.core.paths import resolve_bundled_asset
from app.agents.daisy.character_card import CharacterCard
from app.core.database import SessionLocal
from app.models import UserDB

logger = structlog.get_logger()

def load_default_character_card() -> Optional[CharacterCard]:
    """
    Load the default character card from the configured JSON file.
    """
    try:
        # 配置里的路径相对 cwd,从别处启动或打包后都会落空 —— 交给统一解析
        path = resolve_bundled_asset(settings.DEFAULT_CHARACTER_CARD_PATH)
        if not path:
            logger.error(
                f"Default character card not found at {settings.DEFAULT_CHARACTER_CARD_PATH} "
                f"(cwd={os.getcwd()})"
            )
            return None


        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return CharacterCard(**data)
    except Exception as e:
        logger.error(f"Failed to load default character card: {e}")
        return None

def get_character_card(user_id: str) -> CharacterCard:
    """
    Get the character card for a user.
    Priority:
    1. DB (User Settings -> character_card_json)
    2. Default Static File (Jingwen)
    """
    # 1. Try DB
    try:
        with SessionLocal() as db:
            user = db.query(UserDB).filter(UserDB.username == user_id).first()
            if user and user.settings and user.settings.character_card_json:
                logger.info(f"Loaded character card from DB for user {user_id}")
                return CharacterCard(**user.settings.character_card_json)
    except Exception as e:
        logger.warning(f"Failed to load character card from DB: {e}")

    # 2. Fallback to Default File
    card = load_default_character_card()
    if card:
        logger.info(f"Using default character card (Jingwen) for user {user_id}")
        return card
    
    # 3. Critical Failure
    error_msg = f"CRITICAL: Failed to load any character card for user {user_id}. Default file missing at {settings.DEFAULT_CHARACTER_CARD_PATH}."
    logger.critical(error_msg)
    raise ValueError(error_msg)

def infer_relationship_stage(common_relationship: Optional[str]) -> str:
    rel = (common_relationship or "").strip()
    if not rel:
        return "acquaintance"
    if "恋人" in rel or "暧昧" in rel or "对象" in rel:
        return "bond"
    if "朋友" in rel or "知己" in rel:
        return "trust"
    return "acquaintance"

def build_channel_prompt_addendum(card: CharacterCard, route: str, user_input: str, relationship_stage: str) -> str:
    """
    Generate prompt addendum based on CharacterCard object and route.
    """
    route = (route or "").upper()
    
    # Extract fields from Pydantic model
    name = card.identity.name
    
    if route == "FAST":
        # 规格 §4.2:快速通道加载 language_style.quirks(口癖)+ common_phrases(常用语)。
        # 这些是让极简回复仍带角色辨识度的最小必要信息;此前误用 personality.description,
        # 既更长又不含说话习惯,与规格不符。
        quirks = card.language_style.quirks or []
        quirk_lines = "\n".join(f"- {q}" for q in quirks[:4]) or "(none)"

        phrase_lines = []
        for kind, phrases in (card.language_style.common_phrases or {}).items():
            if phrases:
                phrase_lines.append(f"- {kind}: {' / '.join(phrases[:3])}")
        phrases_text = "\n".join(phrase_lines) or "(none)"

        addendum = f"""# [Character Essence]
Name: {name}
Tone: {card.language_style.tone}

# [Speech Quirks]
{quirk_lines}

# [Common Phrases]
{phrases_text}"""
        return addendum.strip()

    if route == "STANDARD":
        # 规格 §4.2:标准通道 = 完整 language_style + personality.description
        #                      + **当前关系等级**的 relationship_dynamics
        #                      + 1-2 个 dialogue_examples
        description = card.personality.description
        style = card.language_style

        quirks = "\n".join(f"- {q}" for q in (style.quirks or [])[:4]) or "(none)"

        # 关系阶段 → 等级映射。此前 infer_relationship_stage 已算出阶段却未被使用
        # (原注释:"if we had logic for it"),导致不同亲密度加载相同内容。
        stage_to_level = {"acquaintance": 1, "trust": 2, "bond": 3}
        target_level = stage_to_level.get((relationship_stage or "").lower(), 1)
        dynamics = card.relationship_dynamics or []
        current = next((d for d in dynamics if d.level == target_level), None)
        if current is None and dynamics:
            # 找不到精确等级时退到不超过目标等级的最高档
            lower = [d for d in dynamics if d.level <= target_level]
            current = max(lower, key=lambda d: d.level) if lower else dynamics[0]

        if current:
            rel_text = f"Stage: {current.name} (level {current.level})\n{current.description}\n{current.prompt_addon}"
        else:
            rel_text = "(none)"

        pattern = ""
        if card.behavior.push_pull_pattern:
            pattern = card.behavior.push_pull_pattern.description

        # 对话示例:规格要求 1-2 个,给出具象的说话方式参照
        examples = (card.dialogue_examples or [])[:2]
        example_text = "\n".join(
            f"- [{ex.scene}]\n  User: {ex.user}\n  You: {ex.agent}" for ex in examples
        ) or "(none)"

        addendum = f"""# [Character Persona]
Description: {description}
Tone: {style.tone}

# [Speech Quirks]
{quirks}

# [Relationship Dynamics]
{rel_text}
Pattern: {pattern}

# [Dialogue Examples]
{example_text}"""
        return addendum.strip()

    if route == "DEEP":
        # Deep path: Constraints + Inner Monologue Patterns
        constraints_list = [f"- {c.description}" for c in card.constraints]
        monologues = [f"- [{m.emotion}]: {m.pattern}" for m in card.inner_monologue_patterns]
        
        addendum = f"""# [Constraints]
{chr(10).join(constraints_list) if constraints_list else "(none)"}

# [Inner Monologue Patterns]
{chr(10).join(monologues) if monologues else "(none)"}"""
        return addendum.strip()

    return ""
