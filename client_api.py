#!/usr/bin/env python3
"""Root client_api entrypoint - delegates to clients.gui.client_api."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.gui.client_api import LibraryClient, LibraryError, ServerUnavailable

__all__ = ["LibraryClient", "LibraryError", "ServerUnavailable"]
