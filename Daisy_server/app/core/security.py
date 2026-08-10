from datetime import timedelta
from typing import Optional, Any, Union
from jose import jwt
from passlib.context import CryptContext
from .config import settings
from .time_utils import utc_now
import os
import secrets
import warnings

# 开源安全:如果 SECRET_KEY 未设置,自动生成一个随机密钥。
# 桌面版每次启动会生成新密钥(之前的 token 都会失效),server 部署请通过环境变量固定。
def _ensure_secret_key():
    from .config import settings
    if not settings.SECRET_KEY:
        generated = secrets.token_urlsafe(32)
        settings.SECRET_KEY = generated
        if os.environ.get("EMBEDDED_MODE"):
            # 桌面版:每次启动随机生成是可接受的(token 仅本机使用)
            pass
        else:
            warnings.warn(
                "SECRET_KEY 未设置,已自动生成随机密钥。"
                "服务重启后所有已签发的 token 将失效。"
                "生产环境请通过环境变量 SECRET_KEY 设置固定密钥。",
                RuntimeWarning,
            )

_ensure_secret_key()


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码。
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    获取密码哈希值。
    """
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌。
    """
    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def validate_password_complexity(password: str) -> bool:
    """
    验证密码复杂度:
    - 至少 8 个字符
    - 至少一个大写字母
    - 至少一个小写字母
    - 至少一个数字
    - 至少一个特殊字符
    """
    import re
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[ !@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False
    return True
