from datetime import timedelta
from typing import Optional, Any, Union
from jose import jwt
from passlib.context import CryptContext
from .config import settings
from .time_utils import utc_now

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
