---
name: character_generator
version: 1.0.0
description: Generates deep, complex character cards based on seed information using LLM.
author: Daisy Team
license: MIT
category: content_generation
tags:
  - character
  - generation
  - llm
  - persona
dependencies:
  - name: llm_service
    version: ">=1.0.0"
allowed_tools:
  - character_generator.generate_deep_card
  - character_generator.build_prompt_addendum
  - character_generator.validate_card
---

## Operations

### generate_deep_card

Generates a detailed character card from basic seed info.

**Parameters:**
- `name` (string, required): Character name
- `gender` (string, required): Character gender
- `age` (integer, required): Character age
- `occupation` (string, required): Character occupation
- `backstory` (string, optional): Initial backstory hint
- `world_setting` (string, optional): World setting context (default: "Modern Realism")
- `avatar_path` (string, optional): Path to avatar image

**Returns:**
- `identity` (object): Identity details
- `personality` (object): Personality traits
- `language_style` (object): Speech patterns
- `context` (object): Background info
- ... (Full CharacterCard model)

### build_prompt_addendum

Constructs a context-specific prompt addendum based on the active route.

**Parameters:**
- `card_data` (object, required): The CharacterCard data
- `route` (string, required): Current routing path (FAST/STANDARD/DEEP)
- `user_input` (string, optional): Current user input
- `relationship_stage` (string, optional): Current relationship stage

**Returns:**
- `addendum` (string): The constructed prompt text

### validate_card

Validates if a given dictionary conforms to the CharacterCard schema.

**Parameters:**
- `card_data` (object, required): The data to validate

**Returns:**
- `valid` (boolean): True if valid
- `card` (object): Validated card data (if valid)
- `error` (string): Error message (if invalid)
