from fastapi import APIRouter
from app.api.routers import (chat, workflow, session, upload,
                             llm_config, common_settings, profiles)

router = APIRouter()

router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
# 原先是单个 config.router(431 行、11 端点、三类关注点)。拆成三个后
# **仍挂同一前缀**,URL 路径逐字不变,前端无需改动。
router.include_router(llm_config.router, prefix="/config", tags=["config"])
router.include_router(common_settings.router, prefix="/config", tags=["config"])
router.include_router(profiles.router, prefix="/config", tags=["config"])
router.include_router(session.router, prefix="/session", tags=["session"])
router.include_router(upload.router, prefix="/upload", tags=["upload"])
