from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class SkillStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class ResourceType(Enum):
    SCRIPT = "script"
    REFERENCE = "reference"
    ASSET = "asset"
    CONFIG = "config"


@dataclass
class SkillMetadata:
    name: str
    description: str
    version: str
    license: str
    author: str
    category: str
    tags: List[str]
    dependencies: List[str]
    allowed_tools: List[str]
    status: SkillStatus = SkillStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class SkillInstruction:
    content: str
    sections: Dict[str, str] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SkillResource:
    type: ResourceType
    path: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    metadata: SkillMetadata
    instruction: SkillInstruction
    resources: List[SkillResource]
    path: str


@dataclass
class SkillContext:
    user_id: str
    session_id: str
    conversation_id: Optional[str] = None
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillResult:
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: Optional[float] = None


@dataclass
class SkillError:
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionConfig:
    timeout_sec: int = 30
    max_retries: int = 3
    retry_delay_sec: float = 1.0
    enable_cache: bool = True
    cache_ttl_sec: int = 300
