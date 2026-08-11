from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from .config import settings
from .constants import DEFAULT_LLM_TEMPERATURE
from .database import SessionLocal
from .llm_config import llm_config_manager
from .cache import redis_client
from .metrics import estimate_tokens
import structlog
import threading

logger = structlog.get_logger()

class LLMService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LLMService, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    @staticmethod
    def _normalize_api_key(api_key: str | None) -> str | None:
        if api_key is None:
            return None
        key = str(api_key).strip()
        if not key:
            return ""

        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1].strip()

        lower = key.lower()
        if lower.startswith("authorization:"):
            key = key.split(":", 1)[1].strip()
            lower = key.lower()

        if lower.startswith("bearer "):
            key = key[7:].strip()

        return key

    @staticmethod
    def _normalize_base_url(url: str | None) -> str | None:
        if not url:
            return url
        
        # 移除常见的包裹字符和末尾逗号
        # 这种方式比 startswith/endswith 更健壮，能处理嵌套情况
        # 例如: `https://.../v1,` -> https://.../v1
        return str(url).strip().strip("',`\" ").rstrip(",").strip("',`\" ")

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._llm_cache = {}
        self._initialized = True

    def _log_trace(self, user_settings, metadata, system_prompt, user_input, response, error=None):
        try:
            user_id = None
            agent_name = None
            if user_settings:
                user_id = getattr(user_settings, 'user_id', None)
                agent_name = getattr(user_settings, 'name', None)

            # Allow metadata to override agent_name
            if metadata:
                if 'agent_name' in metadata:
                    agent_name = metadata['agent_name']
                if 'user_id' in metadata:
                    user_id = metadata['user_id']

            trigger_message = metadata.get('trigger_message') if metadata else None
            trigger_message_id = metadata.get('trigger_message_id') if metadata else None
            
            # 经由可插拔 sink 落库(见 core/trace_sink.py):core 不认识具体表,
            # 否则最底层会反向依赖 models。
            from .trace_sink import write_llm_trace
            write_llm_trace(
                user_id=user_id,
                agent_name=agent_name,
                trigger_message=trigger_message,
                trigger_message_id=trigger_message_id,
                system_prompt=system_prompt,
                user_input=user_input,
                response=response,
                error=error,
            )
        except Exception as e:
            logger.error(f"Failed to log LLM trace: {e}")

    @staticmethod
    def _mark_key_invalid_if_auth_error(error: Exception, provider_config: dict = None) -> None:
        """
        把「认证失败」与其它错误区分开,标记对应密钥不可用。

        为什么需要:密钥过期/被撤销后环境变量仍然非空,若配置状态只看"有没有值",
        前端就不会引导用户重新填写,而每次对话又必然 401 —— 用户卡在
        "角色卡生成中" 且无处可改。标记后 llm_status.configured 变 False,
        前端会重新显示配置引导。
        """
        text = str(error).lower()
        is_auth = (
            "authenticationerror" in type(error).__name__.lower()
            or "401" in text
            or "invalid authorization" in text
            or "invalid api key" in text
            or "unauthorized" in text
        )
        if not is_auth:
            return
        try:
            from .llm_config import mark_key_invalid, OPENAI_API_KEY_ENV
            env_name = OPENAI_API_KEY_ENV
            if env_name:
                mark_key_invalid(env_name)
        except Exception:
            pass

    async def _record_llm_metrics_async(self, route: str, model_name: str, prompt_text: str, completion_text: str, execution_id: str = None):
        try:
            if not redis_client.enabled or not redis_client.redis:
                return
            in_tokens = estimate_tokens(prompt_text, settings.TOKEN_EST_CHARS_PER_TOKEN)
            out_tokens = estimate_tokens(completion_text, settings.TOKEN_EST_CHARS_PER_TOKEN)
            cost = 0.0
            if settings.EST_COST_PER_1K_INPUT_USD is not None or settings.EST_COST_PER_1K_OUTPUT_USD is not None:
                if settings.EST_COST_PER_1K_INPUT_USD is not None:
                    cost += (in_tokens / 1000.0) * float(settings.EST_COST_PER_1K_INPUT_USD)
                if settings.EST_COST_PER_1K_OUTPUT_USD is not None:
                    cost += (out_tokens / 1000.0) * float(settings.EST_COST_PER_1K_OUTPUT_USD)

            # 落库而不是累加 Redis 计数器:这些是**累计量**,而嵌入模式的 Redis
            # 重启即空 —— 原先每次重启总调用数/总成本归零,面板只反映本次运行。
            from .metrics_sink import KIND_LLM, record_metric
            record_metric(kind=KIND_LLM, route=route or "UNKNOWN",
                          model_name=model_name or None,
                          in_tokens=in_tokens, out_tokens=out_tokens, cost_usd=cost)
            # 工作流级账本(core/budget.py):按 execution_id 累计,供预算控制点消费
            from ..core.budget import record_llm_usage
            await record_llm_usage(execution_id, in_tokens, out_tokens, cost)
        except Exception:
            return

    def get_lightweight_llm(self):
        """
        获取轻量级 LLM 实例 (用于 Router, ReAct 等低延迟场景)
        """
        lightweight_model = settings.LIGHTWEIGHT_LLM_MODEL_NAME
        
        # 使用当前默认 Provider 的配置
        default_provider = llm_config_manager.get_current_provider()
        provider_config = None
        if default_provider:
             provider_config = self._load_provider_config_sync(default_provider)
             
        # 如果未配置轻量级模型，回退到默认 get_llm，但传入 provider_config
        if not lightweight_model:
            return self.get_llm(provider_config=provider_config)

        # 创建实例，强制指定 model 参数
        return self.get_llm(model=lightweight_model, provider_config=provider_config)

    def get_standard_llm(self):
        model_name = settings.STANDARD_LLM_MODEL_NAME
        
        default_provider = llm_config_manager.get_current_provider()
        provider_config = None
        if default_provider:
            provider_config = self._load_provider_config_sync(default_provider)
            
        if not model_name:
            return self.get_llm(provider_config=provider_config)
            
        return self.get_llm(model=model_name, provider_config=provider_config)

    def get_deep_llm(self):
        model_name = settings.DEEP_LLM_MODEL_NAME
        
        default_provider = llm_config_manager.get_current_provider()
        provider_config = None
        if default_provider:
            provider_config = self._load_provider_config_sync(default_provider)
            
        if not model_name:
            # 如果没有配置深度模型，回退到标准模型 (或者直接使用 provider 默认)
            # 这里我们选择直接使用 provider 默认，这通常就是标准模型
            return self.get_llm(provider_config=provider_config)
            
        return self.get_llm(model=model_name, provider_config=provider_config)

    def get_llm(self, api_key: str = None, base_url: str = None, model: str = None, provider_config: dict = None, request_timeout: int = None, max_retries: int = None, streaming: bool = False):
        """
        获取 LLM 实例，支持动态配置和缓存
        """
        import os

        # 如果未提供 provider_config，尝试加载默认 Provider 配置
        if not provider_config:
            default_provider = llm_config_manager.get_current_provider()
            if default_provider:
                provider_config = self._load_provider_config_sync(default_provider)

        # 确定最终配置
        final_api_key = api_key
        final_base_url = base_url
        final_model = model

        # 如果提供了 provider_config，优先使用（除了显式传入的参数）
        if provider_config:
            if not final_api_key:
                final_api_key = provider_config.get("api_key")
            if not final_base_url:
                final_base_url = provider_config.get("base_url")
            if not final_model:
                final_model = provider_config.get("model")
        
        final_api_key = self._normalize_api_key(final_api_key)
        final_base_url = self._normalize_base_url(final_base_url)

        if not final_api_key:
            logger.error("LLM API Key not found in user settings or provider config.")
            raise ValueError("LLM API Key not found in configuration.")

        # 默认超时和重试
        final_timeout = request_timeout if request_timeout is not None else 60
        final_retries = max_retries if max_retries is not None else 1
        
        # Qwen3 系列默认启用内置 thinking,会额外生成大量不可见的 reasoning_content
        # (实测占 45% completion_tokens),而 prompt 中显式要求的 CoT 不受影响。
        # 关闭后提速 27-48%。详见 config.DISABLE_QWEN_THINKING 的说明。
        extra_body = None
        if settings.DISABLE_QWEN_THINKING and final_model and "qwen3" in final_model.lower():
            extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

        # 生成缓存键(含 thinking 开关,避免不同设置复用同一实例)
        cache_key = f"{final_model}:{final_base_url}:{final_api_key[:10]}:{final_timeout}:{final_retries}:{streaming}:{bool(extra_body)}"

        # 检查缓存
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        # 调试日志：显示最终加载的配置 (仅在未命中缓存时)
        masked_key = final_api_key[:4] + "***" + final_api_key[-4:] if final_api_key and len(final_api_key) > 8 else "***"
        logger.info(f"Initializing LLM: Model={final_model}, BaseURL={final_base_url}, APIKey={masked_key}, Streaming={streaming}, NoThinking={bool(extra_body)}")

        try:
            kwargs = dict(
                model=final_model,
                temperature=DEFAULT_LLM_TEMPERATURE,
                api_key=final_api_key,
                base_url=final_base_url,
                request_timeout=final_timeout,
                max_retries=final_retries,
                streaming=streaming
            )
            if extra_body:
                kwargs["extra_body"] = extra_body
            llm_instance = ChatOpenAI(**kwargs)
            # 存入缓存
            self._llm_cache[cache_key] = llm_instance
            return llm_instance
        except Exception as e:
            logger.error(f"Error creating LLM instance: {e}")
            raise e

    def _load_provider_config(self, provider_name: str) -> dict:
        """
        从 Redis 加载 Provider 配置。
        如果 Redis 中不存在，尝试从文件重新加载到 Redis (自愈逻辑)。
        """
        import json
        from .cache import redis_client
        
        redis_key = f"system:llm:provider:{provider_name}"
        
        # 1. 尝试异步获取 (如果是异步上下文)
        # 注意: 这里有一个棘手的问题，_load_provider_config 目前被同步调用。
        # 但 redis_client 是异步的 (redis.asyncio)。
        # 简单起见，我们在这里使用同步方式或仅在 async 方法中支持。
        # 考虑到 generate_response 是同步的，我们需要同步访问 Redis 或者缓存。
        # 方案 A: 既然 generate_response 是同步的，我们无法在这里 await redis。
        # 方案 B: 在 LLMService 初始化时预加载所有配置？不，这不支持动态性。
        # 方案 C: 临时使用同步 Redis 客户端？不推荐混用。
        # 方案 D: (由于架构限制) 对于同步方法，我们可能不得不保留文件读取作为后备，或者要求调用者使用 async。
        # 但 generate_response 是核心同步方法。
        
        # 修正方案: 鉴于当前架构混合了同步/异步，且 Redis 客户端是异步的。
        # 为了不破坏现有同步代码结构，我们可以在同步方法中保留文件读取作为兜底，
        # 而在异步方法 generate_response_async 中使用 Redis。
        # 或者，我们可以使用 async_to_sync 转换，但这引入了复杂性。
        
        # 更好的方案: 将配置加载逻辑解耦。
        # 实际上，为了满足用户 "从 Redis 获取" 的要求，我们需要一个同步的方式来访问 Redis，
        # 或者接受在同步路径中无法使用 Redis 的事实。
        # 这里的权宜之计是：在同步方法中，我们依然读文件（或者内存缓存）；
        # 只有在异步路径中才真正读 Redis。
        # 但为了完全符合用户要求，我们将尝试实现一个伪同步或确保主要调用路径是异步的。
        # 检查代码发现 generate_response 被广泛使用。
        
        # 让我们修改策略：
        # 1. _load_provider_config_async: 真正的 Redis 读取。
        # 2. _load_provider_config_sync: 降级为文件读取 (为了兼容性)。
        
        pass

    async def _load_provider_config_async(self, provider_name: str) -> dict:
        """
        从内存配置加载 Provider 配置 (异步接口)。
        """
        return llm_config_manager.get_provider_config(provider_name)

    def _load_provider_config_sync(self, provider_name: str) -> dict:
        """
        从内存配置加载 Provider 配置。
        """
        return llm_config_manager.get_provider_config(provider_name)

    def generate_response(self, system_prompt: str, user_input: str, context: str, user_settings=None, metadata: dict = None, request_timeout: int = None, max_retries: int = None) -> str:
        # 同步版本：使用同步配置加载
        # 从 user_settings 或环境变量确定配置
        api_key = None
        base_url = None
        model = None
        provider_config = None
        
        if user_settings:
            # 优先获取用户自定义设置
            api_key = getattr(user_settings, 'llm_api_key', None)
            base_url = getattr(user_settings, 'llm_base_url', None)
            model = getattr(user_settings, 'llm_model_name', None)

            # 检查是否有 provider 设置
            llm_provider = getattr(user_settings, 'llm_provider', None)
            if llm_provider:
                 provider_config = self._load_provider_config_sync(llm_provider)
                 if not provider_config:
                     raise ValueError(f"Configuration for LLM Provider '{llm_provider}' not found.")
        
        route = metadata.get("route") if metadata else None
        # 内部系统任务(JSON 分类、查询改写等)强制走轻量模型:这类任务不面向用户人格,
        # 不应受 user_settings.llm_model_name 约束。必须放在 `if not model` 之前——
        # 用户设置了 llm_model_name 时 model 已非空,route 映射会被整体短路。
        if metadata and metadata.get("force_lightweight") and settings.LIGHTWEIGHT_LLM_MODEL_NAME:
            model = settings.LIGHTWEIGHT_LLM_MODEL_NAME
        elif not model:
            if route == "DEEP" and settings.DEEP_LLM_MODEL_NAME:
                model = settings.DEEP_LLM_MODEL_NAME
            elif route == "STANDARD" and settings.STANDARD_LLM_MODEL_NAME:
                model = settings.STANDARD_LLM_MODEL_NAME
            elif route == "FAST" and settings.LIGHTWEIGHT_LLM_MODEL_NAME:
                model = settings.LIGHTWEIGHT_LLM_MODEL_NAME
            
        # 如果尚未确定配置，尝试使用系统默认提供商
        if not provider_config and not api_key:
            default_provider = settings.DEFAULT_LLM_PROVIDER
            if default_provider:
                provider_config = self._load_provider_config_sync(default_provider)
                logger.info(f"Using default LLM provider: {default_provider}")
        
        llm = self.get_llm(api_key, base_url, model, provider_config, request_timeout=request_timeout, max_retries=max_retries)
        
        if not llm:
            logger.error("LLM Service not initialized. Missing API Key.")
            raise ValueError("LLM_NOT_CONFIGURED")
        
        # 构建内容：仅当提供 user_input 时追加
        content = context
        if user_input:
            if content:
                content += f"\n\nUser Input: {user_input}"
            else:
                content = user_input
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content)
        ]
        
        # 记录完整的提示结构以进行调试
        agent_name = "Unknown"
        if metadata and "agent_name" in metadata:
            agent_name = metadata["agent_name"]

        logger.info(f"LLM Request [{agent_name}]", system_prompt=system_prompt[:200] + "...", user_message_length=len(content))
        
        try:
            response = llm.invoke(messages)
            self._log_trace(user_settings, metadata, system_prompt, content, response.content)
            try:
                prompt_text = f"{system_prompt}\n\n{content}"
                model_name = model or getattr(user_settings, "llm_model_name", None) or settings.DEFAULT_LLM_MODEL_NAME
                import asyncio as _asyncio
                try:
                    loop = _asyncio.get_running_loop()
                    loop.create_task(self._record_llm_metrics_async(route or "UNKNOWN", model_name, prompt_text, response.content or "", execution_id=metadata.get("execution_id") if metadata else None))
                except RuntimeError:
                    pass
            except Exception:
                pass
            return response.content
        except Exception as e:
            logger.error("LLM Generation Failed", error=str(e))
            self._mark_key_invalid_if_auth_error(e, provider_config)
            self._log_trace(user_settings, metadata, system_prompt, content, None, error=str(e))
            return f"Error generating response: {e}"

    async def generate_response_async(self, system_prompt: str, user_input: str, context: str, user_settings=None, metadata: dict = None, request_timeout: int = None, max_retries: int = None, streaming: bool = False) -> str:
        """
        使用 ainvoke 的 generate_response 异步版本。
        优先使用 Redis 配置。
        """
        # 从 user_settings 或环境变量确定配置
        api_key = None
        base_url = None
        model = None
        provider_config = None
        
        if user_settings:
            # 优先获取用户自定义设置
            api_key = getattr(user_settings, 'llm_api_key', None)
            base_url = getattr(user_settings, 'llm_base_url', None)
            model = getattr(user_settings, 'llm_model_name', None)

            # 检查是否有 provider 设置
            llm_provider = getattr(user_settings, 'llm_provider', None)
            if llm_provider:
                 provider_config = await self._load_provider_config_async(llm_provider)
                 if not provider_config:
                     # 尝试同步读取作为后备 (虽然现在我们倾向于严格，但保持对文件系统的兼容性)
                     provider_config = self._load_provider_config_sync(llm_provider)
                 
                 if not provider_config:
                     raise ValueError(f"Configuration for LLM Provider '{llm_provider}' not found.")

            # 如果没有 provider config，尝试直接使用 user_settings 中的值 (自定义模式)
            # (此逻辑已由上述 provider_config 覆盖，或如果 provider_config 仍为空)
            
        route = metadata.get("route") if metadata else None
        # 内部系统任务(JSON 分类、查询改写等)强制走轻量模型:这类任务不面向用户人格,
        # 不应受 user_settings.llm_model_name 约束。必须放在 `if not model` 之前——
        # 用户设置了 llm_model_name 时 model 已非空,route 映射会被整体短路。
        if metadata and metadata.get("force_lightweight") and settings.LIGHTWEIGHT_LLM_MODEL_NAME:
            model = settings.LIGHTWEIGHT_LLM_MODEL_NAME
        elif not model:
            if route == "DEEP" and settings.DEEP_LLM_MODEL_NAME:
                model = settings.DEEP_LLM_MODEL_NAME
            elif route == "STANDARD" and settings.STANDARD_LLM_MODEL_NAME:
                model = settings.STANDARD_LLM_MODEL_NAME
            elif route == "FAST" and settings.LIGHTWEIGHT_LLM_MODEL_NAME:
                model = settings.LIGHTWEIGHT_LLM_MODEL_NAME
        
        # 如果尚未确定配置，尝试使用系统默认提供商
        if not provider_config and not api_key:
            default_provider = settings.DEFAULT_LLM_PROVIDER
            if default_provider:
                provider_config = await self._load_provider_config_async(default_provider)
                if not provider_config:
                     provider_config = self._load_provider_config_sync(default_provider)
                logger.info(f"Using default LLM provider: {default_provider} (Async)")
        
        llm = self.get_llm(api_key, base_url, model, provider_config, request_timeout=request_timeout, max_retries=max_retries, streaming=streaming)
        
        if not llm:
            logger.error("LLM Service not initialized. Missing API Key.")
            raise ValueError("LLM_NOT_CONFIGURED")
        
        # 构建内容：仅当提供 user_input 时追加
        content = context
        if user_input:
            if content:
                content += f"\n\nUser Input: {user_input}"
            else:
                content = user_input
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=content)
        ]
        
        # 记录完整的提示结构以进行调试
        agent_name = "Unknown"
        if metadata and "agent_name" in metadata:
            agent_name = metadata["agent_name"]
            
        logger.info(f"Async LLM Request [{agent_name}]", system_prompt=system_prompt[:200] + "...", user_message_length=len(content))
        
        try:
            response = await llm.ainvoke(messages)
            self._log_trace(user_settings, metadata, system_prompt, content, response.content)
            prompt_text = f"{system_prompt}\n\n{content}"
            model_name = model or getattr(user_settings, "llm_model_name", None) or settings.DEFAULT_LLM_MODEL_NAME
            await self._record_llm_metrics_async(route or "UNKNOWN", model_name, prompt_text, response.content or "", execution_id=metadata.get("execution_id") if metadata else None)
            return response.content
        except Exception as e:
            logger.error("Async LLM Generation Failed", error=str(e))
            self._mark_key_invalid_if_auth_error(e, provider_config)
            self._log_trace(user_settings, metadata, system_prompt, content, None, error=str(e))
            return f"Error generating response: {e}"

llm_service = LLMService()

def get_llm_service():
    return llm_service
