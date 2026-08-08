from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
import structlog

from .api import router as api_router
from .admin import router as admin_router
from .core.logging import init_logging
from .core.config import settings

init_logging(settings.LOG_LEVEL)
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup_daisy_skills")
    from .skills.reflexion.scripts import start_reflexion_worker, stop_reflexion_worker
    await start_reflexion_worker()
    yield
    await stop_reflexion_worker()
    logger.info("shutdown_daisy_skills")

app = FastAPI(title="Daisy Skills API", lifespan=lifespan)
app.include_router(api_router)
app.include_router(admin_router)

class HealthResponse(BaseModel):
    status: str
    version: str
    tools_count: int

@app.get("/health", response_model=HealthResponse)
async def health_check():
    from .core.registry import registry
    return HealthResponse(status="ok", version="1.0.0", tools_count=len(registry.list()))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
