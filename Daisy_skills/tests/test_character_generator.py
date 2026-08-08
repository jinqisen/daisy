import pytest
from app.skills.character_generator.scripts.generator import character_generator
from app.skills.character_generator.scripts.models import CharacterCard
from app.skills.character_generator.scripts import generate_deep_card, build_prompt_addendum, validate_card

def test_imports():
    assert character_generator is not None
    assert CharacterCard is not None
    assert generate_deep_card.execute is not None
    assert build_prompt_addendum.execute is not None
    assert validate_card.execute is not None

def test_validate_card_logic():
    # Test valid
    valid_data = {
        "identity": {
            "name": "Test", "gender": "F", "age": 20, "occupation": "Tester"
        },
        "personality": {
            "description": "Desc", "core_traits": ["T1"]
        },
        "language_style": {
            "tone": "Tone", "quirks": [], "common_phrases": {}
        },
        "context": {
            "backstory": "Back", "world_setting": "World"
        },
        "constraints": [],
        "behavior": {
            "push_pull_pattern": {
                "description": "P", "pull_behaviors": [], "push_behaviors": []
            }
        },
        "relationship_dynamics": [],
        "dialogue_examples": [],
        "inner_monologue_patterns": []
    }
    
    import asyncio
    result = asyncio.run(validate_card.execute({"card_data": valid_data}, None))
    assert result["valid"] is True
    assert result["card"]["identity"]["name"] == "Test"

    # Test invalid
    result = asyncio.run(validate_card.execute({"card_data": {}}, None))
    assert result["valid"] is False
