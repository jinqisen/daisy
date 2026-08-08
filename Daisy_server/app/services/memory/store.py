import os
import logging
import warnings
from functools import lru_cache
from typing import Any, Dict, List, Optional

import structlog

# Disable Mem0 Telemetry (PostHog) to prevent timeouts
os.environ["MEM0_TELEMETRY"] = "False"

# mem0 把自己的工作目录硬编码在 ~/.mem0(history.db + migrations_qdrant)。
# 打包版无权写入那里,于是每次写记忆都甩一条
# "Error processing memory action ... attempt to write a readonly database" ——
# 而向量写入是成功的,所以表面看记忆正常,只有 mem0 的变更历史悄悄丢失,
# 属于最难发现的"一半成功"故障。
#
# 注意:MEM0_TELEMETRY=False 只关掉 PostHog 上报,**不阻止**它创建
# migrations_qdrant 目录(那段代码无条件执行),所以关遥测解决不了这个问题。
# mem0 认 MEM0_DIR,用它把工作目录整体迁到应用数据目录,与上传/日志/向量库同处一地。
# 必须在 import mem0 之前设置 —— mem0/memory/setup.py 在模块导入时就读取并建目录。
def _init_mem0_home() -> None:
    """
    把 mem0 的工作目录（history.db + migrations_qdrant）整体迁到应用数据目录。

    根因:
      mem0 1.0.1 的 mem0/memory/setup.py 在模块导入时按
        mem0_dir = os.environ.get("MEM0_DIR") or ~/.mem0
      只读一次环境变量，之后任何运行时改 MEM0_DIR 都无效。
      一旦该模块被任何更早的 import 链路（间接依赖、app.main 顶层 import、
      其它服务模块等）抢先载入，mem0_dir 就会被钉死成 ~/.mem0。
      macOS 桌面版受 SIP 限制对 ~/.mem0 不可写，于是构造 Memory(...) 时
      触发 `attempt to write a readonly database`，表现为
      "Error processing memory action" —— 这正是当前打包版的报错。
    修正:
      1) 先在 MEM0_DIR 已设置时直接返回，让测试/打包脚本能注入；
      2) 否则把 MEM0_DIR 指向应用数据目录；
      3) 强制 reload `mem0.memory.setup`，让 mem0_dir 重新解析环境变量
         并用我们指定的目录建立 migrations_qdrant/history.db；
         若 reload 失败（极端情况），至少把模块全局 mem0_dir 强制覆盖。
    """
    from app.core.config import get_writable_data_dir

    if not os.environ.get("MEM0_DIR"):
        target = os.path.join(get_writable_data_dir(), "mem0")
        os.makedirs(target, exist_ok=True)
        os.environ["MEM0_DIR"] = target

    target_dir = os.environ["MEM0_DIR"]
    try:
        import importlib
        from mem0.memory import setup as _mem0_setup

        # 之前若有别的 import 链已经把它固化在 ~/.mem0，这里强制重读
        importlib.reload(_mem0_setup)
        # 重载后再保险一次：确保模块常量与目录都跟随我们的目标
        _mem0_setup.mem0_dir = target_dir
        os.makedirs(_mem0_setup.mem0_dir, exist_ok=True)
    except Exception as _exc:  # pragma: no cover - 运行环境兜底
        # 退而求其次：把环境里也写一份，让后续 import 至少拿到对的字符串
        os.environ["MEM0_DIR"] = target_dir
        os.makedirs(target_dir, exist_ok=True)


_init_mem0_home()

# Suppress HuggingFace Mistral tokenizer warning (False positive for BGE-M3/XLM-Roberta)
# The warning suggests setting fix_mistral_regex=True, but that causes a crash with XLM-Roberta's Metaspace pre-tokenizer.
warnings.filterwarnings("ignore", message=".*fix_mistral_regex=True.*")

# Suppress Transformers logging
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.tokenization_utils").setLevel(logging.ERROR)
logging.getLogger("transformers.tokenization_utils_base").setLevel(logging.ERROR)

# Suppress Mem0 and Qdrant initialization logs (Index creation info)
logging.getLogger("mem0").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING) # Suppress HTTP request logs if any


from mem0 import Memory
from mem0.embeddings.openai import OpenAIEmbedding as _OpenAIEmbedding

from app.core.config import settings, resolve_local_model
from app.core.constants import MEMORY_LLM_MAX_TOKENS, MEMORY_LLM_TEMPERATURE
from app.core.llm_config import llm_config_manager

@lru_cache()
def get_memory_service() -> "MemoryService":
    return MemoryService()

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Monkeypatch: mem0's OpenAIEmbedding.embed() 无条件发送 `dimensions` 参数
# (见 mem0/embeddings/openai.py)。`dimensions` 仅是 OpenAI text-embedding-3-*
# 模型的专有参数；SiliconFlow 的 BAAI/bge-m3 输出维度固定为 1024，不接受该参数，
# 收到后会直接以 `400 code:20015 The parameter is invalid` 拒绝整个请求。
# 由于 add 与 search 共用同一个 embed()，两者都会失败，导致长期记忆完全不工作。
# 这里仅在目标 base_url 确实是官方 OpenAI 时才透传 dimensions，其余情况一律省略。
# ---------------------------------------------------------------------------
def _embed_without_invalid_dimensions(self, text, memory_action=None):
    text = text.replace("\n", " ")
    base_url = str(getattr(self.client, "base_url", "") or "")
    create_kwargs = {"input": [text], "model": self.config.model}
    if "api.openai.com" in base_url and self.config.embedding_dims:
        create_kwargs["dimensions"] = self.config.embedding_dims
    return self.client.embeddings.create(**create_kwargs).data[0].embedding


_OpenAIEmbedding.embed = _embed_without_invalid_dimensions


def _history_db_path() -> str:
    """
    mem0 变更历史库的位置。

    mem0 默认写 ~/.mem0/history.db。打包版写不进去(实测 "attempt to write a
    readonly database"),而且用户数据散落到家目录隐藏文件夹也不合适 ——
    统一收进应用数据目录,与上传/日志/向量库同处一地,卸载时一并清理。
    """
    from app.core.config import get_writable_data_dir

    base = os.path.join(get_writable_data_dir(), "mem0")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "history.db")


def _user_selected_provider() -> Optional[str]:
    """
    用户在设置里选定的对话 provider(common_settings.llm_provider)。

    这才是对话实际使用的服务商 —— llm.py 就是读它(见 llm.py:341/433)。
    `llm_config_manager.get_current_provider()` 只是 DEFAULT_LLM_PROVIDER 的静态快照,
    用它会造成"对话走硅基流动、记忆走华为云"的分裂。
    桌面版是单用户,取第一条设置即可。
    """
    try:
        from app.core.database import SessionLocal
        from app.models import CommonSettingsDB

        with SessionLocal() as db:
            row = (db.query(CommonSettingsDB)
                     .filter(CommonSettingsDB.llm_provider.isnot(None))
                     .order_by(CommonSettingsDB.user_id.asc())
                     .first())
            return row.llm_provider if row else None
    except Exception as e:
        logger.warning(f"MemoryService: 读取用户 provider 失败,回落到默认: {e}")
        return None


def _first_configured_provider(exclude: Optional[str] = None):
    """
    找一个可用的聊天 provider 作为记忆抽取的 LLM。

    只看"密钥是否可用"(而非"是否非空")—— 失效密钥不应被当成可用的回落目标,
    否则记忆功能会带着一把已被拒绝的密钥反复失败。
    """
    from app.core.llm_config import is_key_usable

    for name in llm_config_manager.list_providers():
        if name == exclude:
            continue
        cfg = llm_config_manager.get_provider_config(name)
        if not cfg or not cfg.get("api_key"):
            continue
        env_name = cfg.get("api_key_env")
        if env_name and not is_key_usable(env_name):
            continue
        return name, cfg
    return None


class MemoryService:
    def __init__(self):
        self.memory: Optional[Memory] = None

        # 确定 Embedder 配置
        embedding_provider = settings.EMBEDDING_PROVIDER
        
        # 默认配置 (OpenAI)
        embedder_config = {
            "provider": "openai",
            "config": {
                "model": settings.EMBEDDING_MODEL_NAME,
                "embedding_dims": settings.EMBEDDING_DIMS
            }
        }

        # 0. 最高优先级:随包分发的本地模型(构建期已拉好,见 packaging/fetch_models.py)。
        #    原先只认绝对路径,而配置里写的是 HF Hub ID "BAAI/bge-large-zh-v1.5",
        #    于是运行时按需下载 —— 用户第一次用长期记忆要等 1.3GB,断网直接失败。
        _bundled = resolve_local_model(settings.EMBEDDING_MODEL_NAME.split("/")[-1])
        if _bundled:
            logger.info(f"使用随包嵌入模型: {_bundled}")
            embedder_config = {
                "provider": "huggingface",
                "config": {"model": _bundled},
            }
        # 1. 其次检查是否为本地模型路径
        elif os.path.exists(settings.EMBEDDING_MODEL_NAME):
             logger.info(f"使用本地嵌入模型: {settings.EMBEDDING_MODEL_NAME}")
             embedder_config = {
                "provider": "huggingface",
                "config": {
                    "model": settings.EMBEDDING_MODEL_NAME,
                    # "embedding_dims": 1024 # HuggingFace provider might infer this
                }
            }
        # 2. 处理 HuggingFace / Local (非路径，可能是 HF Hub ID)
        elif embedding_provider in ["huggingface", "local"]:
             logger.info(f"使用 HuggingFace 嵌入模型: {settings.EMBEDDING_MODEL_NAME}")
             embedder_config = {
                "provider": "huggingface",
                "config": {
                    "model": settings.EMBEDDING_MODEL_NAME
                }
            }
        else:
             # 默认或者暂存配置，后面会针对 SiliconFlow再次检查
             embedder_config = {
                "provider": "huggingface",
                "config": {
                    "model": settings.EMBEDDING_MODEL_NAME
                }
            }

        # 维度必须与嵌入模型实际输出一致,否则 Qdrant 拒绝写入、长期记忆静默失效。
        # 换模型时同步改 settings.EMBEDDING_DIMS(见 config.py 注释)。
        _dims = settings.EMBEDDING_DIMS
        qdrant_config = {
             "path": settings.VECTOR_DB_PATH,  # Local path for Qdrant
             "embedding_model_dims": _dims,
        }
        
        if settings.QDRANT_HOST:
             logger.info(f"连接到 Qdrant，地址 {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
             qdrant_config = {
                 "host": settings.QDRANT_HOST,
                 "port": settings.QDRANT_PORT,
                 "embedding_model_dims": _dims,
             }
        else:
             logger.warning(f"未设置 QDRANT_HOST，使用本地路径: {settings.VECTOR_DB_PATH}")

        # 记忆抽取用的 LLM:**跟随用户选定的对话 provider**。
        #
        # 原实现硬编码 target_provider = "siliconflow",理由写的是"规避 ModelArts 风控"。
        # 这个理由站不住:没有证据表明记忆抽取会被风控误杀,而代价是实打实的 ——
        #   1. 用户选了华为云,记忆却去调硅基流动:凭空多要一把密钥、多一份账单;
        #   2. 没有那把密钥时直接 raise,长期记忆的检索与写入两端全废,
        #      而用户收不到任何提示,只会觉得"她不记得我说过的话"。
        # 记忆是对话的一部分,应当和对话用同一个模型,行为才可预期。
        target_provider = _user_selected_provider() or llm_config_manager.get_current_provider()
        provider_config = (
            llm_config_manager.get_provider_config(target_provider) if target_provider else None
        )

        if provider_config and provider_config.get("api_key"):
            logger.info(f"MemoryService: 跟随对话 provider '{target_provider}'。")
        else:
            fallback = _first_configured_provider()
            if not fallback:
                # 首次运行(用户尚未填密钥)会走到这里,属预期流程 —— 用 info 而非 error,
                # 否则正常的首次启动日志里会出现吓人的 ERROR。
                logger.info("MemoryService: 尚未配置任何 LLM,长期记忆待配置后启用。")
                raise ValueError("MemoryService: no usable LLM provider is configured.")
            target_provider, provider_config = fallback
            logger.warning(
                f"MemoryService: 当前对话 provider 不可用,回落到 '{target_provider}'。"
            )

        llm_api_key = provider_config.get("api_key")
        llm_base_url = provider_config.get("base_url")
        llm_model_name = provider_config.get("model")

        if not llm_api_key:
             raise ValueError("LLM API Key is missing in the provider configuration.")

        # 注意：不要设置全局 os.environ["OPENAI_API_KEY"]，以避免污染 Embedder 的配置
        # Mem0 允许在 config 中显式指定 LLM 和 Embedder 的配置

        # 远程嵌入(SiliconFlow,OpenAI 协议)。
        #
        # 仅在**没有随包本地模型**时才走这条路 —— 本地模型已随安装包分发,
        # 用它既不花钱也不依赖网络。原实现无条件覆盖:哪怕本地模型就在手边,
        # 只要 EMBEDDING_PROVIDER=siliconflow 就改走远程,而没有那把密钥时
        # 干脆 raise,把整个长期记忆废掉。
        if not _bundled and embedding_provider == "siliconflow":
            # settings 是启动时快照;桌面版用户在运行期通过 /config/llm_keys 填入的密钥
            # 只进了 os.environ,故优先读环境变量,再回退 settings。
            sf_api_key = os.environ.get("SILICONFLOW_API_KEY") or settings.SILICONFLOW_API_KEY
            if sf_api_key:
                logger.info(f"使用 SiliconFlow 嵌入模型: {settings.EMBEDDING_MODEL_NAME}")
                # Mem0 的 BaseEmbedderConfig 使用 openai_base_url 参数
                embedder_config = {
                    "provider": "openai",
                    "config": {
                        "model": settings.EMBEDDING_MODEL_NAME,
                        "embedding_dims": settings.EMBEDDING_DIMS,
                        "api_key": sf_api_key,
                        "openai_base_url": "https://api.siliconflow.cn/v1"
                    }
                }
            else:
                # 既没有本地模型也没有远程密钥 —— 只能明确报错,但要说清怎么办
                logger.error(
                    "嵌入模型不可用:安装包内未找到本地模型,也未配置 SILICONFLOW_API_KEY。"
                    "正常安装包应自带模型(见 packaging/fetch_models.py)。"
                )
                raise ValueError("No embedding model available: neither bundled model nor SILICONFLOW_API_KEY.")

        # 3. 构建最终配置
        # Mem0 的 OpenAIConfig 使用 openai_base_url 参数
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": qdrant_config
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": llm_model_name,
                    "temperature": MEMORY_LLM_TEMPERATURE,
                    "max_tokens": MEMORY_LLM_MAX_TOKENS,
                    "api_key": llm_api_key,
                    "openai_base_url": llm_base_url,
                    # 华为云 ModelArts 敏感信息屏蔽处理
                    # Error code 403: ModelArts.81011 (May contain sensitive information)
                    # 当模型认为输入/输出包含敏感信息时会报错。
                    # Mem0 默认会提取"事实"、"偏好"等，可能会被过度风控。
                    # 暂时无法在 Mem0 层直接控制 Prompt，但可以通过降低 temperature 和 max_tokens 减少生成内容的不可控性。
                    # 或者，如果可能，切换到风控较松的模型。
                    # 另外，确保 llm_base_url 正确。
                }
            },
            "embedder": embedder_config,
            # mem0 的历史库默认落在 ~/.mem0/history.db —— 打包版写不进去,
            # 报 "attempt to write a readonly database"。向量写入照常成功,
            # 所以表面看记忆是好的,只有 mem0 内部的变更历史悄悄丢了。
            # 用户数据统一放应用数据目录(与上传/日志/向量库一致),不再依赖家目录隐藏文件夹。
            "history_db_path": _history_db_path(),
        }
        
        # 针对华为云/ModelArts 的特殊处理：
        # 如果当前 Provider 是 huaweicloud，且遇到 403 敏感信息错误，
        # 建议用户检查 llm_providers.json 中的模型配置，或尝试切换到 siliconflow。
        # 这里我们无法自动切换，只能记录日志。
        self.memory = Memory.from_config(config)
        try:
            logger.info(
                "MemoryService history db",
                db_path=getattr(getattr(self.memory, "db", None), "db_path", None),
            )
        except Exception:
            pass
        logger.info(f"MemoryService initialized with provider: {target_provider}, model: {llm_model_name}")
        self._initialized = True

    def _require_memory(self) -> Memory:
        memory = self.memory
        if memory is None:
            raise ValueError("Memory service not initialized")
        return memory

    @staticmethod
    def _build_metadata(
        session_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged_metadata = dict(metadata or {})
        if session_id:
            merged_metadata.setdefault("session_id", session_id)
        return merged_metadata

    @staticmethod
    def _extract_memories(results: Any) -> List[str]:
        if isinstance(results, dict) and "results" in results:
            results = results["results"]

        if not isinstance(results, list):
            return []

        memories: List[str] = []
        for item in results:
            if isinstance(item, dict):
                memory_text = item.get("memory") or item.get("text") or ""
            else:
                memory_text = getattr(item, "memory", getattr(item, "text", ""))
                if not memory_text:
                    memory_text = str(item)

            if isinstance(memory_text, str) and memory_text:
                memories.append(memory_text)
        return memories

    def add_memory(
        self,
        text: str,
        user_id: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        向向量数据库添加新的记忆。
        """
        user_id = str(user_id)
        memory = self._require_memory()
        
        try:
            memory.add(
                text,
                user_id=user_id,
                agent_id=agent_id,
                metadata=self._build_metadata(session_id, metadata),
            )
            logger.info(f"已为用户 {user_id} 添加记忆")
        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            raise

    def search_memory(self, query: str, user_id: str, limit: int = 5) -> List[str]:
        """
        根据查询搜索相关记忆。
        """
        user_id = str(user_id)
        memory = self._require_memory()
        
        try:
            results = memory.search(query, user_id=user_id, limit=limit)
            return self._extract_memories(results)
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            raise

    def get_all_memories(self, user_id: str) -> List[str]:
        """
        获取指定用户的所有记忆。
        """
        user_id = str(user_id)
        memory = self._require_memory()
        try:
            results = memory.get_all(user_id=user_id)
            return self._extract_memories(results)
        except Exception as e:
            logger.error(f"获取所有记忆失败: {e}")
            raise
