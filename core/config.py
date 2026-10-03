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

# CAT-2 Open Book Collaborative Lending Configuration
# Subject mapping based on university timetable
CAT2_SUBJECTS = {
    "CSE2004": "Python Programming",
    "ECE2002": "C++ & Data Structures",
    "MAT2002": "Discrete Mathematics",
    "CSE3011": "Theory of Computation (TOC)",
    "MGT2003": "Engineering Economics & Management",
    "PLA1004": "Professional Learning & Aptitude",
}

# University theory slots and relative exam day offsets
# Slot A1 on Day 1, B1 on Day 2, C1 on Day 3, D1 on Day 4, E1 on Day 5, F1 on Day 6,
# A2 on Day 7, B2 on Day 8, C2 on Day 9, D2 on Day 10, E2 on Day 11, F2 on Day 12
CAT2_SLOTS = ["A1", "B1", "C1", "D1", "E1", "F1", "A2", "B2", "C2", "D2", "E2", "F2"]

SLOT_EXAM_DAYS = {
    "A1": 1,
    "B1": 2,
    "C1": 3,
    "D1": 4,
    "E1": 5,
    "F1": 6,
    "A2": 7,
    "B2": 8,
    "C2": 9,
    "D2": 10,
    "E2": 11,
    "F2": 12,
}
