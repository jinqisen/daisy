---
name: router
version: 1.0.0
description: Three-tier routing architecture that selects FAST/STANDARD/DEEP processing paths based on user input complexity.
author: Daisy Team
license: MIT
category: routing
tags:
  - router
  - routing
  - dialogue-flow
  - intelligent-routing
dependencies:
  - name: emotion
    version: ">=1.0.0"
  - name: persona
    version: ">=1.0.0"
  - name: llm_service
    version: ">=1.0.0"
allowed_tools:
  - router.route_input
  - router.get_route_info
  - router.update_route_patterns
---

## Operations

### route_input

Routes user input to the appropriate processing path (FAST, STANDARD, or DEEP).

**Parameters:**
- `user_input` (string, required): The user's input text.
- `user_id` (string, required): The user's ID.
- `session_id` (string, required): The session ID.
- `context` (object, optional): Additional context information.

**Returns:**
- `route` (string): The determined route ("FAST", "STANDARD", "DEEP").
- `confidence` (number): Confidence score of the routing decision (0.0 to 1.0).
- `reasoning` (string): Explanation for the routing decision.

**Example:**
```json
{
  "route": "STANDARD",
  "confidence": 0.85,
  "reasoning": "User input contains emotional expression, requiring standard processing."
}
```

### get_route_info

Retrieves current routing configuration and statistics.

**Parameters:**
- None

**Returns:**
- `routes` (array): List of available routes.
- `fast_patterns` (array): List of regex patterns for FAST path.
- `thresholds` (object): Routing thresholds for STANDARD and DEEP paths.

### update_route_patterns

Updates the regex patterns used for the FAST routing path.

**Parameters:**
- `patterns` (array, required): List of new regex patterns.

**Returns:**
- `success` (boolean): True if update was successful.
- `count` (number): Number of patterns updated.
