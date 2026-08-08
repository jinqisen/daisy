from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from .config import settings
from .logging import get_logger


@dataclass
class Whitelist:
    allowed_users: Set[str] = field(default_factory=set)
    superusers: Set[str] = field(default_factory=set)

    def is_user_allowed(self, user_id: str) -> bool:
        return user_id in self.allowed_users

    def is_superuser(self, user_id: str) -> bool:
        return user_id in self.superusers

    def add_user(self, user_id: str, is_superuser: bool = False):
        if is_superuser:
            self.superusers.add(user_id)
        self.allowed_users.add(user_id)

    def remove_user(self, user_id: str):
        self.allowed_users.discard(user_id)
        self.superusers.discard(user_id)

    def to_dict(self) -> dict:
        return {
            "users": sorted(self.allowed_users),
            "admins": sorted(self.superusers),
        }


class WhitelistManager:
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = Path(file_path) if file_path else Path.cwd() / "whitelist.json"
        self._whitelist = Whitelist()
        self._load()

    def _load(self):
        logger = get_logger()
        if not self.file_path.exists():
            logger.info("whitelist_file_not_found", path=str(self.file_path))
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self._whitelist.allowed_users = set(data)
                self._whitelist.superusers = set()
            elif isinstance(data, dict):
                users = data.get("users", [])
                admins = data.get("admins", [])
                self._whitelist.allowed_users = set(users)
                self._whitelist.superusers = set(admins)
            else:
                logger.warning("whitelist_invalid_format", path=str(self.file_path))

            logger.info(
                "whitelist_loaded",
                path=str(self.file_path),
                users_count=len(self._whitelist.allowed_users),
                admins_count=len(self._whitelist.superusers),
            )
        except Exception as e:
            logger.error("whitelist_load_failed", path=str(self.file_path), error=str(e))

    def reload(self):
        self._whitelist = Whitelist()
        self._load()
        logger = get_logger()
        logger.info("whitelist_reloaded", admin=True, action="whitelist_reload")

    def is_user_allowed(self, user_id: str) -> bool:
        return self._whitelist.is_user_allowed(user_id)

    def is_superuser(self, user_id: str) -> bool:
        return self._whitelist.is_superuser(user_id)

    def add_user(self, user_id: str, is_superuser: bool = False):
        self._whitelist.add_user(user_id, is_superuser)
        logger = get_logger()
        logger.info(
            "whitelist_user_added",
            admin=True,
            action="whitelist_add",
            user_id=user_id,
            is_superuser=is_superuser,
        )

    def remove_user(self, user_id: str):
        self._whitelist.remove_user(user_id)
        logger = get_logger()
        logger.info(
            "whitelist_user_removed",
            admin=True,
            action="whitelist_remove",
            user_id=user_id,
        )

    def get_whitelist(self) -> dict:
        return self._whitelist.to_dict()

    def save(self):
        try:
            data = self._whitelist.to_dict()
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger = get_logger()
            logger.info(
                "whitelist_saved",
                admin=True,
                action="whitelist_save",
                path=str(self.file_path),
            )
        except Exception as e:
            logger = get_logger()
            logger.error(
                "whitelist_save_failed",
                admin=True,
                action="whitelist_save",
                path=str(self.file_path),
                error=str(e),
            )


_whitelist_manager: Optional[WhitelistManager] = None


def get_whitelist_manager() -> WhitelistManager:
    global _whitelist_manager
    if _whitelist_manager is None:
        _whitelist_manager = WhitelistManager()
    return _whitelist_manager


def is_user_allowed(user_id: str) -> bool:
    return get_whitelist_manager().is_user_allowed(user_id)


def is_superuser(user_id: str) -> bool:
    return get_whitelist_manager().is_superuser(user_id)
