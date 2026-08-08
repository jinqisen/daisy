"""向后兼容的转发:Base 已下沉到 core/db_base(见其中说明)。"""

from ..core.db_base import Base

__all__ = ["Base"]
