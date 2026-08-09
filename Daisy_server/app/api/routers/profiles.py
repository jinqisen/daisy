"""
人格档案(RoleProfile)的增删改与权重调整。

从原 config.py 拆出,见 llm_config.py 的说明。URL 路径不变。
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, List, Any
import json
import os
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.core.cache import redis_client
from app.models import UserDB, CommonSettingsDB, RoleProfileDB
from app.prompts import CommonSettings, RoleProfile, get_system_prompt_generator_meta
from app.api.deps import get_current_user
from app.core.llm import get_llm_service
from app.services.dialogue.generation import generate_character_portrait_async, generate_deep_character_card

logger = structlog.get_logger()
router = APIRouter()

@router.get("/profiles")
async def get_profiles(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    获取角色画像列表。
    """
    profiles = db.query(RoleProfileDB).filter(RoleProfileDB.user_id == current_user.id).all()
    result = {}
    for p in profiles:
        result[p.name] = RoleProfile(
            name=p.name,
            description=p.description,
            style=p.style,
            constraints=p.constraints,
        )
    return result

@router.delete("/profiles/{name}")
async def delete_profile(
    name: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    删除指定的角色画像。
    """
    profile = db.query(RoleProfileDB).filter(
        RoleProfileDB.name == name,
        RoleProfileDB.user_id == current_user.id
    ).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    db.delete(profile)
    db.commit()
    return {"status": "success", "message": f"Profile {name} deleted"}

@router.post("/profiles")
async def update_profile(
    profile: RoleProfile,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    """
    更新或创建角色画像。
    """
    name = profile.name
    if not name:
        raise HTTPException(status_code=400, detail="Profile name required")
    
    db_profile = db.query(RoleProfileDB).filter(
        RoleProfileDB.name == name,
        RoleProfileDB.user_id == current_user.id
    ).first()
    
    if not db_profile:
        db_profile = RoleProfileDB(name=name, user_id=current_user.id)
        db.add(db_profile)
    
    db_profile.description = profile.description
    db_profile.style = profile.style
    db_profile.constraints = profile.constraints
        
    db.commit()
    return {"status": "success"}

@router.post("/weights")
async def update_weights(weights: Dict[str, float]):
    """
    手动更新性格权重。
    """
    return {"status": "received", "weights": weights}
