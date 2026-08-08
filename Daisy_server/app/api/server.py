from fastapi import APIRouter
from app.api.routers import chat, workflow, config, session, upload

router = APIRouter()

router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
router.include_router(config.router, prefix="/config", tags=["config"])
router.include_router(session.router, prefix="/session", tags=["session"])
router.include_router(upload.router, prefix="/upload", tags=["upload"])
