from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Union, Optional
from ..core.config import load_whitelist, save_whitelist
from ..models import UserDB
from .deps import get_current_user
import structlog

logger = structlog.get_logger()

router = APIRouter()

class WhitelistUserAdd(BaseModel):
    username: str
    gender: str = "male"

class WhitelistResponse(BaseModel):
    users: List[Union[str, dict]]
    admins: List[str]

def check_superuser(current_user: UserDB = Depends(get_current_user)) -> UserDB:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

@router.get("/whitelist", response_model=WhitelistResponse)
async def get_whitelist(
    current_user: UserDB = Depends(check_superuser)
):
    """
    获取白名单列表。
    """
    return load_whitelist()

@router.post("/whitelist/user")
async def add_whitelist_user(
    user_in: WhitelistUserAdd,
    current_user: UserDB = Depends(check_superuser)
):
    """
    添加用户到白名单。
    """
    data = load_whitelist()
    users = data.get("users", [])
    
    # 检查是否存在
    for u in users:
        if isinstance(u, str):
            if u == user_in.username:
                raise HTTPException(status_code=400, detail="User already exists in whitelist")
        elif isinstance(u, dict):
            if u.get("username") == user_in.username:
                raise HTTPException(status_code=400, detail="User already exists in whitelist")
    
    # 添加新用户
    # 统一使用对象格式
    new_user = {"username": user_in.username, "gender": user_in.gender}
    users.append(new_user)
    data["users"] = users
    
    if save_whitelist(data):
        logger.info(f"Admin {current_user.username} added {user_in.username} to whitelist")
        return {"status": "success", "message": f"User {user_in.username} added to whitelist"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save whitelist")

@router.delete("/whitelist/user/{username}")
async def delete_whitelist_user(
    username: str,
    current_user: UserDB = Depends(check_superuser)
):
    """
    从白名单删除用户。
    """
    data = load_whitelist()
    users = data.get("users", [])
    
    new_users = []
    found = False
    for u in users:
        u_name = u if isinstance(u, str) else u.get("username")
        if u_name == username:
            found = True
            continue # Skip adding this user
        new_users.append(u)
        
    if not found:
        raise HTTPException(status_code=404, detail="User not found in whitelist")
        
    data["users"] = new_users
    
    if save_whitelist(data):
        logger.info(f"Admin {current_user.username} removed {username} from whitelist")
        return {"status": "success", "message": f"User {username} removed from whitelist"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save whitelist")
