from typing import Generator, Optional
from fastapi import Depends, HTTPException, status


def require_server_mode():
    """
    仅 server 部署可用的端点守卫。

    桌面版是单机应用:账号注册/登录、白名单管理这些概念不存在,而端点若仍开放,
    本机上任意进程都能访问 —— 属无谓攻击面。这里统一在嵌入模式下返回 404,
    对外表现为"该功能不存在",而非"存在但被禁止"。
    """
    from ..core.config import settings
    if settings.EMBEDDED_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    return True


def require_embedded_mode():
    """
    仅桌面版(嵌入模式)可用的端点守卫 —— require_server_mode 的镜像。

    本地隐私锁属于此类:它保护的是本机数据,在 server 部署下毫无意义
    (那里该用真正的账号体系)。同样返回 404 而非 403,不暴露"存在但被禁止"。
    """
    from ..core.config import settings
    if not settings.EMBEDDED_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    return True
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from ..core.config import settings
from ..core.database import get_db
from ..models import UserDB
from ..core import security

# OAuth2 方案，指定 Token 获取 URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> UserDB:
    """
    获取当前登录用户。
    验证 JWT Token 并从数据库中查找用户。
    """
    try:
        # 解码 JWT
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 查找用户
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

def get_current_user_from_token_param(
    token: str,
    db: Session = Depends(get_db)
) -> UserDB:
    """
    从 Query Parameter 获取 Token (用于 SSE/WebSocket)
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except (JWTError, ValidationError):
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user
