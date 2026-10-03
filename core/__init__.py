"""Core package containing shared models, database logic, and configuration."""

from core.database import Library
from core.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    WEB_PORT,
    DB_FILE,
    LOAN_DAYS,
    MAX_LOANS,
    FINE_PER_DAY,
    CAT2_SUBJECTS,
    CAT2_SLOTS,
    SLOT_EXAM_DAYS,
)

__all__ = [
    "Library",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "WEB_PORT",
    "DB_FILE",
    "LOAN_DAYS",
    "MAX_LOANS",
    "FINE_PER_DAY",
    "CAT2_SUBJECTS",
    "CAT2_SLOTS",
    "SLOT_EXAM_DAYS",
]
