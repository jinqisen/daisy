from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from ..models.base import Base
# Import all models to ensure they are registered in Base.metadata
from ..models import UserDB, RoleProfileDB, CommonSettingsDB, ChatHistoryDB, WorkflowTraceDB, LLMTraceDB, ReflexionLogDB

# Path to Daisy_server/sqlite.db (Shared DB for seamless migration)
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # Daisy_skills/
_server_dir = os.path.join(os.path.dirname(_base_dir), "Daisy_server")
DB_PATH = os.path.join(_server_dir, "sqlite.db")

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create database engine
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
