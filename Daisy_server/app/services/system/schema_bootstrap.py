"""
数据库表结构引导。

放在 services 而非 core:建表要知道"有哪些模型",而 core 是最底层、不应认识
业务实体 —— 原先 core/database.py 直接 import 全部模型,构成 core ↔ models 循环。
把引导逻辑上提后,core 只剩纯基础设施(engine / SessionLocal / Base)。
"""

from sqlalchemy import inspect, text

from app.core.database import Base, engine
from app import models  # noqa: F401  — 导入即注册模型到 Base.metadata,勿删


def _add_missing_columns():
    """
    给已存在的表补上模型里新增的列。

    为什么需要:项目没有 Alembic,而 create_all 只建**不存在的表**,对已存在的表
    不会加列。桌面版用户的库是升级安装时保留下来的 —— 新版本加一个字段,老库就会
    在第一次查询时炸 "no such column",且没有任何自愈路径。

    只做加列(SQLite 支持 ALTER TABLE ADD COLUMN),不改类型、不删列 —— 这类破坏性
    变更必须显式处理,不该由自动逻辑代劳。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all 已经按最新结构建好了
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                # 加列必须可空:已有行没有值可填
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                ))
                print(f"[db] 已为表 {table.name} 补充列 {column.name}")


def init_db():
    """
    初始化数据库表结构。

    这里**必须**先导入 app.models:create_all 只会建 Base.metadata 里已注册的表,
    而注册发生在模型类被定义(即模块被导入)时。若依赖"调用方碰巧先导入过",
    表会**静默漏建**,直到第一次查询才炸,且错误信息离根因很远。
    延迟到函数内导入是为了保持 core 不在模块层依赖 models(那会形成循环)。
    """
    from app import models  # noqa: F401  — 触发模型注册,勿删

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def init_db():
    """初始化数据库表结构(建表 + 为老库补列)。"""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
