import json
import structlog
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm import LLMService
from app.prompts import RoleProfile

logger = structlog.get_logger()

class PersonalityFusionEngine:
    def __init__(self):
        self.llm_service = LLMService()

    async def run(self, state: Dict[str, Any], active_profiles: Dict[str, RoleProfile]) -> Dict[str, Any]:
        """
        Executes the personality fusion process using a single LLM call.
        """
        user_input = state.get('user_input', '')
        # 配置定义在 core/config.py。这里曾误写成 services.config，
        # 打包后运行时会抛 `No module named 'app.services.config'`，
        # 迫使整条融合路径退回到 MultiAgentService。
        from app.core.config import settings
        
        # Select model based on route
        # For now we rely on the default LLM, but conceptually:
        # if route == 'DEEP': use stronger model
        # if route == 'STANDARD': use faster model
        
        # Fix: Explicitly load provider config to ensure API Key is present
        provider_config = None
        if settings.DEFAULT_LLM_PROVIDER:
             # Accessing internal method to reuse loading logic
             provider_config = await self.llm_service._load_provider_config_async(settings.DEFAULT_LLM_PROVIDER)
        
        llm = self.llm_service.get_llm(provider_config=provider_config)
        if not llm:
            logger.error("LLM not available for Personality Fusion")
            return {}

        # Construct the prompt
        profiles_text = ""
        for name, profile in active_profiles.items():
            style_str = ", ".join(profile.style) if profile.style else ""
            profiles_text += f"- **{name}**: {profile.description}\n  Style: {style_str}\n\n"

        prompt = f"""
        You are the Personality Fusion Engine for a complex AI character.
        Your goal is to simulate the internal thought processes of multiple personality facets and fuse them into a coherent state.

        **Active Personality Facets**:
        {profiles_text}

        **User Input**:
        "{user_input}"

        **Task**:
        1. For EACH active facet, generate a distinct internal monologue (thought) reacting to the user input.
           - The thought should reflect the specific traits, style, and goal of that facet.
           - Include a [Strategy] tag (e.g., Empathetic_Support, Playful_Teasing, etc.) if applicable.
        2. Determine a "Fusion Strategy" to integrate these divergent thoughts.
        3. Summarize the "Final Internal State" of the character.

        **Output Format**:
        You MUST return a valid JSON object with the following structure:
        {{
            "internal_monologues": {{
                "FacetName1": "[Strategy]: ... [Thought]: ...",
                "FacetName2": "..."
            }},
            "fusion_strategy": "Description of how to merge these thoughts...",
            "final_internal_state": "Summary of the final emotional/cognitive state..."
        }}
        """

        try:
            response = await llm.ainvoke([
                SystemMessage(content="You are an expert in personality simulation and cognitive fusion. Output valid JSON."),
                HumanMessage(content=prompt)
            ], config={"response_format": {"type": "json_object"}})
            
            content = response.content
            # Clean up markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            
            # Log the result
            logger.info("Personality Fusion Result", fusion_strategy=result.get("fusion_strategy"))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Personality Fusion Engine: {e}", response_content=response.content)
            # Fallback: try to return a basic structure
            return {
                "internal_monologues": {name: "Error parsing thoughts." for name in active_profiles},
                "fusion_strategy": "Fallback due to error",
                "final_internal_state": "Error state"
            }
        except Exception as e:
            logger.error(f"Personality Fusion Engine error: {e}", exc_info=True)
            return {}

fusion_engine = PersonalityFusionEngine()
