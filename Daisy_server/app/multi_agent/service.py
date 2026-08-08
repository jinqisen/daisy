from typing import List, Dict, Any, Optional
import asyncio
import structlog
from ..core.config import settings
from ..core.database import SessionLocal
from ..models import RoleProfileDB, CommonSettingsDB, UserDB
from ..core.llm import get_llm_service
from ..prompts.templates import (
    get_multi_agent_agent_goal, 
    get_multi_agent_agent_backstory, 
    get_multi_agent_task_description,
    get_multi_agent_system_prompt,
    get_multi_agent_user_prompt,
    CommonSettings, 
    RoleProfile
)
from ..agents.strategies import EmotionalStrategy
from ..agents.rubrics import QualityRubric

logger = structlog.get_logger()

class MultiAgentService:
    """
    Lite implementation of MultiAgentService.
    Uses direct LLM calls with asyncio for parallelism.
    """
    def __init__(self):
        pass

    async def consult_personalities_async(self, user_input: str, active_profiles: List[str], user_id: str, context_text: str = "", portrait_text: str = "", trigger_message_id: int = None, execution_id: str = None) -> Dict[str, str]:
        """
        Asynchronously consult multiple personalities (agents) to generate thoughts, strategic intent, AND rubric checks (MOA).
        """
        if not active_profiles:
            return {}

        loop = asyncio.get_running_loop()

        # 1. Fetch Data (Run blocking DB operations in thread pool)
        try:
            user_data = await loop.run_in_executor(None, self._fetch_user_data_sync, user_id, active_profiles)
        except Exception as e:
            logger.error(f"Failed to fetch user data for thoughts: {e}")
            return {}

        if not user_data:
            logger.warning(f"No user data found for {user_id}")
            return {}

        common: CommonSettings = user_data['common']
        profiles_map: Dict[str, RoleProfile] = user_data['profiles']

        # 2. Prepare Tasks
        tasks = []
        llm_service = get_llm_service()
        
        # 策略描述字符串
        strategy_desc = "\n".join([f"- {s.value}: {EmotionalStrategy.get_description(s)}" for s in EmotionalStrategy])
        
        # 评分标准描述字符串 (MOA)
        rubric_desc = QualityRubric.get_all_descriptions()

        for name in active_profiles:
            profile = profiles_map.get(name)
            if not profile:
                continue

            # Construct Prompts
            # Goal + Backstory as System Prompt
            goal = get_multi_agent_agent_goal(profile.description)
            backstory = get_multi_agent_agent_backstory(common.backstory or "", name, ', '.join(profile.style))
            
            # 使用 templates.py 中的统一模板
            system_prompt = get_multi_agent_system_prompt(
                backstory=backstory,
                goal=goal,
                strategy_desc=strategy_desc,
                rubric_desc=rubric_desc
            )

            # Task Description as User Input
            task_description = get_multi_agent_task_description(user_input, portrait_text, context_text, name)
            user_prompt = get_multi_agent_user_prompt(task_description)

            # Metadata
            metadata = {
                "agent_name": f"Thought_{name}",
                "user_id": user_id,
                "trigger_message_id": trigger_message_id,
                "execution_id": execution_id,
            }

            # Create Coroutine
            tasks.append(
                self._generate_single_thought(
                    llm_service, 
                    system_prompt, 
                    user_prompt, 
                    common, 
                    metadata,
                    name
                )
            )

        # 3. Execute in Parallel
        if not tasks:
            return {}

        logger.info(f"Generating thoughts for {len(tasks)} personas in parallel (Async)...")
        results = await asyncio.gather(*tasks)
        
        # 4. Format Results
        thoughts = {name: content for name, content in results if content}
        return thoughts

    def _fetch_user_data_sync(self, user_id: str, active_profiles: List[str]) -> Optional[Dict[str, Any]]:
        """
        Synchronous DB fetcher, returns Pydantic models to avoid detached instance issues.
        """
        with SessionLocal() as db:
            user = None
            # Try to interpret as ID first if it looks like an integer
            if str(user_id).isdigit():
                 user = db.query(UserDB).filter(UserDB.id == int(user_id)).first()
            
            # Fallback to username if not found or not digit
            if not user:
                user = db.query(UserDB).filter(UserDB.username == str(user_id)).first()

            if not user:
                return None
            
            common_db = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == user.id).first()
            if not common_db:
                # Should not happen for valid user, but handle gracefully
                common_db = CommonSettingsDB(user_id=user.id) # Dummy

            # Convert to Pydantic CommonSettings
            # Note: Explicitly mapping fields to avoid issues if Pydantic model structure differs slightly or DB has extra internal fields
            common = CommonSettings(
                name=common_db.name,
                gender=common_db.gender,
                age=common_db.age,
                occupation=common_db.occupation,
                relationship=common_db.relationship,
                backstory=common_db.backstory,
                portrait=common_db.portrait,
                world_setting=common_db.world_setting,
                system_prompt_template=common_db.system_prompt_template,
                core_system_prompt=common_db.core_system_prompt,
                llm_provider=common_db.llm_provider,
                llm_api_key=common_db.llm_api_key,
                llm_base_url=common_db.llm_base_url,
                llm_model_name=common_db.llm_model_name
            )
            
            profiles = {}
            for name in active_profiles:
                p_db = db.query(RoleProfileDB).filter(RoleProfileDB.name == name, RoleProfileDB.user_id == user.id).first()
                if p_db:
                    # Convert to Pydantic RoleProfile
                    profiles[name] = RoleProfile(
                        name=p_db.name,
                        description=p_db.description,
                        style=p_db.style, # DB stores JSON list, SQLAlchemy JSON type handles conversion to list
                        constraints=p_db.constraints,
                    )
            
            return {"common": common, "profiles": profiles}

    async def _generate_single_thought(self, llm_service, system_prompt, user_prompt, common, metadata, name):
        try:
            # Check if LLM service has async support (it should)
            if hasattr(llm_service, "generate_response_async"):
                response = await llm_service.generate_response_async(
                    system_prompt=system_prompt,
                    user_input=user_prompt,
                    context="",
                    user_settings=common,
                    metadata=metadata
                )
            else:
                # Fallback to sync run in executor if async not available (unlikely for our stack)
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None, 
                    llm_service.generate_response, 
                    system_prompt, 
                    user_prompt, 
                    "",
                    common,
                    metadata
                )
            return name, response
        except Exception as e:
            logger.error(f"Error generating thought for {name}: {e}")
            return name, ""

# Singleton instance
multi_agent_service = MultiAgentService()
