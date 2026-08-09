from typing import Any, Optional
import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core import security
from ..core.config import settings
from app.services.system.whitelist import load_whitelist
from app.services.system.default_settings import load_default_settings
from ..core.database import get_db, SessionLocal
from ..models import UserDB, CommonSettingsDB, RoleProfileDB
from ..services.system.init_data import INITIAL_PROFILES
from ..prompts import CommonSettings
from ..services.dialogue.generation import generate_deep_character_card
from . import deps

logger = structlog.get_logger()

router = APIRouter()

# 本地单用户的固定用户名(嵌入模式)。数据全在本机,无需真实账号体系。
LOCAL_USER_NAME = "local"
# 本地桌面会话的令牌有效期(天)。见 local_session 内注释。
LOCAL_SESSION_TOKEN_DAYS = 365

def ensure_user_settings(db: Session, user: UserDB, user_gender: str = "male"):
    """
    确保用户拥有默认设置 (AI 伴侣) 和角色画像。
    如果用户是新注册的，将为其创建默认的性格设置和角色配置。
    
    Args:
        db: 数据库会话
        user: 用户对象
        user_gender: 用户性别 ("male" 或 "female")，用于选择默认模板。默认为 "male"。
    """
    # 1. 通用设置 (Common Settings)
    if not user.settings:
        # 为该用户创建默认设置
        default_settings = load_default_settings(user_gender)
        settings = CommonSettingsDB(
            user_id=user.id,
            **default_settings
        )
        db.add(settings)
    
    # 2. 角色画像 (Role Profiles)
    # 检查用户是否有画像。如果没有，从 INITIAL_PROFILES 复制
    user_profiles_count = db.query(RoleProfileDB).filter(RoleProfileDB.user_id == user.id).count()
    if user_profiles_count == 0:
        for profile in INITIAL_PROFILES:
            db_obj = RoleProfileDB(
                user_id=user.id,
                name=profile.name,
                description=profile.description,
                style=profile.style,
                constraints=profile.constraints,
            )
            db.add(db_obj)
            
    db.commit()
    db.refresh(user)

class UserCreate(BaseModel):
    username: str
    password: str
    # gender: str = "male" # 已移除，性别现在由白名单控制

class UserUpdatePassword(BaseModel):
    old_password: str
    new_password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    is_superuser: bool = False


class LocalSessionRequest(BaseModel):
    """本地会话请求。未设隐私锁时 password 可省略。"""
    password: Optional[str] = None


@router.post("/local_session", response_model=Token)
def local_session(
    background_tasks: BackgroundTasks,
    payload: Optional[LocalSessionRequest] = None,
    db: Session = Depends(get_db),
) -> Any:
    """
    桌面版本地会话:打开即用,无需注册/登录。

    为什么需要它:本应用数据完全存放在用户自己的机器上,不存在服务端,
    要求用户"注册账号"是 server 部署遗留的思维;而且 /register 有白名单校验
    (用户名不在 whitelist.json 即 403),真实用户装了根本注册不了。

    嵌入模式(EMBEDDED_MODE)下本端点自动创建/复用唯一本地用户并签发令牌;
    非嵌入模式返回 404,避免绕过 server 部署的正常认证。

    隐私锁(见 services/local_lock.py)是**可选**的:
      未设锁 → 行为与从前完全一致,直接签发令牌;
      已设锁 → 需要正确密码,否则 401。
    401 与 404 语义分明:401 是"密码不对,请重试",404 才是"这里没有这个功能"。
    前端据此区分,不会再把可重试的失败误当成部署形态(那正是上次死路的成因)。
    """
    if not settings.EMBEDDED_MODE:
        raise HTTPException(status_code=404, detail="Not available in server mode")

    from ..services.system import local_lock

    if local_lock.is_lock_enabled():
        if not local_lock.verify(payload.password if payload else None):
            raise HTTPException(status_code=401, detail="本地密码不正确")

    import secrets

    user = db.query(UserDB).filter(UserDB.username == LOCAL_USER_NAME).first()
    if not user:
        # 本地用户不走密码登录,这里的随机口令仅用于满足字段非空约束
        user = UserDB(
            username=LOCAL_USER_NAME,
            hashed_password=security.get_password_hash(secrets.token_urlsafe(32)),
            is_active=True,
            is_superuser=True,  # 本机用户即拥有者,应能访问全部设置
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created local desktop user")
    elif not user.is_superuser:
        user.is_superuser = True  # 兼容早期版本创建的本地用户
        db.add(user)
        db.commit()
        db.refresh(user)

    ensure_user_settings(db, user, user_gender="male")

    # 仅在"已配置 LLM 且尚无角色卡"时调度生成。
    # 未配置时生成必然失败,而本端点可能被前端多次调用(重连/竞态),
    # 无条件调度会反复刷屏日志且毫无意义 —— 此时应由前端引导用户去配置。
    if user.settings and not user.settings.character_card_json:
        from ..core.llm_config import is_any_llm_configured
        if is_any_llm_configured():
            background_tasks.add_task(generate_card_background, user.id)

    # 本地会话签发长效令牌:桌面版没有服务端,令牌从不离开本机,
    # 短 TTL 带不来任何安全收益,却会让应用开着超过 30 分钟后所有请求变 401
    # (前端只能一直重试同一个死令牌 —— 表现为满屏报错)。
    from datetime import timedelta
    access_token = security.create_access_token(
        subject=user.username,
        expires_delta=timedelta(days=LOCAL_SESSION_TOKEN_DAYS),
    )
    return {"access_token": access_token, "token_type": "bearer", "is_superuser": True}


@router.post("/register", response_model=Token, dependencies=[Depends(deps.require_server_mode)])
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db)
) -> Any:
    """
    注册新用户。
    需要用户名在白名单中，且密码符合复杂度要求。
    """
    # 动态白名单检查 (无需重启)
    # 重新加载白名单以获取最新配置
    whitelist_config = load_whitelist()
    allowed_users = whitelist_config.get("users", [])
    superusers = whitelist_config.get("admins", [])
    
    # 检查用户名是否在白名单中，并获取对应的性别
    is_allowed = False
    user_gender = "male" # 默认性别
    
    for allowed_user in allowed_users:
        if isinstance(allowed_user, str):
            if allowed_user == user_in.username:
                is_allowed = True
                break
        elif isinstance(allowed_user, dict):
            if allowed_user.get("username") == user_in.username:
                is_allowed = True
                user_gender = allowed_user.get("gender", "male")
                break
    
    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail="Username not in whitelist"
        )
    
    user = db.query(UserDB).filter(UserDB.username == user_in.username).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
        
    if not security.validate_password_complexity(user_in.password):
        raise HTTPException(
            status_code=400,
            detail="Password does not meet complexity requirements (min 8 chars, uppercase, lowercase, number, special char)"
        )
    
    # 根据配置确定超级用户状态
    is_superuser = user_in.username in superusers
    
    user = UserDB(
        username=user_in.username,
        hashed_password=security.get_password_hash(user_in.password),
        is_superuser=is_superuser
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 初始化默认设置
    ensure_user_settings(db, user, user_gender=user_gender)
    
    access_token = security.create_access_token(subject=user.username)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_superuser": user.is_superuser
    }

async def generate_card_background(user_id: int):
    """
    后台任务：为用户生成深度角色卡

    重要设计:深度角色卡是"增强",不是"进入门槛"。
    前端用 has_character_card 做门禁,而深度生成是一次大 Prompt 的慢 LLM 调用
    (无固定耗时,实测可达数分钟且可能挂住)。若让门禁等它,用户首次打开会长时间
    面对加载动画 —— 因此这里的顺序是:
      1) 未配置 LLM  → 什么都不写,让前端引导用户去填 API Key
      2) 已配置 LLM  → **先立即写入默认角色卡**,用户马上可以开始对话
      3) 然后再后台尝试深度生成,成功则静默升级为更丰富的人格
    """
    logger.info(f"Starting background Deep Character Card generation for user_id={user_id}")
    try:
        # Create new session
        with SessionLocal() as db:
            user_settings = db.query(CommonSettingsDB).filter(CommonSettingsDB.user_id == user_id).first()
            if not user_settings:
                logger.warning(f"User {user_id} has no settings, skipping card generation")
                return

            # 未配置 LLM:不写卡,由前端显示配置引导(深度生成此时必然失败)
            from ..core.llm_config import is_any_llm_configured
            if not is_any_llm_configured():
                logger.warning(
                    f"No LLM configured; skipping card generation for user_id={user_id} "
                    f"so the frontend can guide the user to configure a provider."
                )
                return

            # 已配置:先落默认卡解除门禁,让用户立刻能用
            if not user_settings.character_card_json:
                try:
                    from ..services.persona.character_card import load_default_character_card
                    baseline = load_default_character_card()
                    if baseline:
                        user_settings.character_card_json = baseline.model_dump()
                        db.commit()
                        logger.info(
                            f"Applied default character card for user_id={user_id} "
                            f"(unblocks chat immediately; deep card will upgrade it in background)"
                        )
                except Exception as e:
                    logger.error(f"Failed to apply baseline character card: {e}")

            # Convert DB model to Pydantic
            # Note: We construct it manually to ensure all fields are mapped correctly
            common = CommonSettings(
                name=user_settings.name,
                gender=user_settings.gender,
                age=user_settings.age,
                occupation=user_settings.occupation,
                relationship=user_settings.relationship,
                backstory=user_settings.backstory,
                world_setting=user_settings.world_setting,
                # Copy other fields if needed, but these are the core ones for generation
                llm_provider=user_settings.llm_provider,
                llm_model_name=user_settings.llm_model_name,
                llm_base_url=user_settings.llm_base_url,
                llm_api_key=user_settings.llm_api_key
            )
            
            # 深度生成:加超时上限。原实现无超时,LLM 挂住会让任务永久悬空
            # (实测首次运行时该请求发出后既不返回也不报错)。此处超时后保留上面
            # 已写入的默认卡,用户不受影响。
            import asyncio
            try:
                card = await asyncio.wait_for(
                    generate_deep_character_card(common),
                    timeout=settings.DEEP_CARD_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Deep Character Card generation timed out after "
                    f"{settings.DEEP_CARD_TIMEOUT_SEC}s for user_id={user_id}; "
                    f"keeping default card (user is unaffected)."
                )
                card = None

            if card:
                user_settings.character_card_json = card.model_dump()
                db.commit()
                logger.info(f"Successfully generated and saved Deep Character Card for user_id={user_id}")
            else:
                # 无需再兜底:默认卡已在本函数开头写入,用户不会被门禁挡住
                logger.warning(
                    f"Deep Character Card unavailable for user_id={user_id}; "
                    f"default card remains in effect."
                )

    except Exception as e:
        logger.error(f"Background card generation failed for user_id={user_id}: {e}")

@router.post("/login", response_model=Token, dependencies=[Depends(deps.require_server_mode)])
async def login(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 兼容的令牌登录，获取访问令牌以进行后续请求。
    """
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Incorrect username or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    # 登录时从白名单配置同步超级用户状态
    whitelist_config = load_whitelist()
    superusers = whitelist_config.get("admins", [])
    
    should_be_superuser = user.username in superusers
    if user.is_superuser != should_be_superuser:
        user.is_superuser = should_be_superuser
        db.add(user)
        db.commit()
        db.refresh(user)

    # 确保已有设置 (兼容老用户，或登录时才初始化的场景，默认用 male -> 女 AI)
    ensure_user_settings(db, user, user_gender="male")
    
    # 检查是否需要生成深度角色卡
    if user.settings and not user.settings.character_card_json:
        logger.info(f"User {user.username} missing character card, scheduling background generation.")
        background_tasks.add_task(generate_card_background, user.id)
        
    access_token = security.create_access_token(subject=user.username)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_superuser": user.is_superuser
    }

@router.post("/change-password", response_model=dict, dependencies=[Depends(deps.require_server_mode)])
def change_password(
    password_in: UserUpdatePassword,
    current_user: UserDB = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    修改当前用户的密码。
    """
    if not security.verify_password(password_in.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Incorrect old password"
        )
        
    if not security.validate_password_complexity(password_in.new_password):
        raise HTTPException(
            status_code=400,
            detail="New password does not meet complexity requirements"
        )
        
    current_user.hashed_password = security.get_password_hash(password_in.new_password)
    db.add(current_user)
    db.commit()
    
    return {"message": "Password updated successfully"}


# ---- 本地隐私锁(桌面版专有,与 server 的注册/登录无关)----
# 见 services/local_lock.py 的说明:这是数据保护,不是准入控制。

class LocalLockSet(BaseModel):
    password: str
    current_password: Optional[str] = None   # 已设锁时改密码需提供旧密码


@router.get("/local_lock", dependencies=[Depends(deps.require_embedded_mode)])
def get_local_lock_status() -> Any:
    """是否已设置本地锁。前端据此决定要不要显示密码输入。"""
    from ..services.system import local_lock
    return local_lock.status()


@router.post("/local_lock", dependencies=[Depends(deps.require_embedded_mode)])
def set_local_lock(payload: LocalLockSet) -> Any:
    """设置或修改本地锁。已设锁时必须先验旧密码,否则任何人都能改掉它。"""
    from ..services.system import local_lock

    if local_lock.is_lock_enabled() and not local_lock.verify(payload.current_password):
        raise HTTPException(status_code=401, detail="当前密码不正确")
    try:
        local_lock.set_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "lock_enabled": True}


@router.delete("/local_lock", dependencies=[Depends(deps.require_embedded_mode)])
def remove_local_lock(current_password: str) -> Any:
    """关闭本地锁。必须验证当前密码 —— 否则锁形同虚设。"""
    from ..services.system import local_lock

    if not local_lock.verify(current_password):
        raise HTTPException(status_code=401, detail="当前密码不正确")
    local_lock.disable_lock()
    return {"status": "ok", "lock_enabled": False}
