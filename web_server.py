#!/usr/bin/env python3
"""Root web_server entrypoint - delegates to clients.web.web_server."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.web.web_server import Handler, main

__all__ = ["Handler", "main"]

if __name__ == "__main__":
    main()
