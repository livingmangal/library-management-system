#!/usr/bin/env python3
"""Library entrypoint - backward compatibility shim and direct CLI launcher."""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import DB_FILE, FINE_PER_DAY, LOAN_DAYS, MAX_LOANS
from core.database import Library
from clients.cli import main

__all__ = ["Library", "DB_FILE", "LOAN_DAYS", "MAX_LOANS", "FINE_PER_DAY", "main"]

if __name__ == "__main__":
    main()
