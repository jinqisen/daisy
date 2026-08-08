from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from .db_base import Base

# SQLite 数据库文件路径
# 桌面打包(冻结)环境下 __file__ 不可写,优先用 DAISY_DB_PATH 指向用户数据目录;
# 否则回退到源码树 Daisy_server/sqlite.db(开发/server 部署行为不变)。
DB_PATH = os.environ.get("DAISY_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "sqlite.db"
)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# 创建数据库引擎
# check_same_thread=False 仅用于 SQLite，允许在不同线程中使用连接
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    获取数据库会话生成器
    用于 FastAPI 的依赖注入。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
