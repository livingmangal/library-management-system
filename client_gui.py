#!/usr/bin/env python3
"""Root client_gui entrypoint - delegates to clients.gui.app."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.gui.app import App, main

__all__ = ["App", "main"]

if __name__ == "__main__":
    main()
