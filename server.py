#!/usr/bin/env python3
"""Root server entrypoint - delegates to server package."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.server import DEMO_BOOKS, DEMO_MEMBERS, LibraryServer, main, seed_demo_data

__all__ = ["LibraryServer", "seed_demo_data", "DEMO_BOOKS", "DEMO_MEMBERS", "main"]

if __name__ == "__main__":
    main()
