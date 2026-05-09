"""模型层枚举常量。"""

from enum import Enum


class DocumentStatus(str, Enum):
    """Document.status 取值。"""
    UPLOADED = "uploaded"
    PARSING = "parsing"
    EXTRACTED = "extracted"
    WRITTEN = "written"
    FAILED = "failed"


class UserRole(str, Enum):
    """User.role 取值。"""
    ADMIN = "admin"
    OPERATOR = "operator"


class ExtractionRunStatus(str, Enum):
    """ExtractionRun.status 取值。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"