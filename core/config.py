"""Central configuration and constants for the Library Management System."""

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = os.environ.get("LIBRARY_DB", str(BASE_DIR / "library.db"))

# Network Defaults
DEFAULT_HOST = os.environ.get("LIBRARY_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("LIBRARY_PORT", 5050))
WEB_PORT = int(os.environ.get("LIBRARY_WEB_PORT", 8000))

# Business Rules
LOAN_DAYS = int(os.environ.get("LIBRARY_LOAN_DAYS", 14))
MAX_LOANS = int(os.environ.get("LIBRARY_MAX_LOANS", 3))
FINE_PER_DAY = float(os.environ.get("LIBRARY_FINE_PER_DAY", 0.50))
