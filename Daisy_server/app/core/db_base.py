"""
SQLAlchemy 声明式基类。

放在 core 而非 models:Base 是持久化**基础设施**,models 是业务实体。
原先 Base 住在 models 里,导致 core/database.py 必须反向 import models 才能建表,
形成 core ↔ models 循环。现在方向单一:models → core。
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
