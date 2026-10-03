"""Tkinter Desktop GUI client package."""

from clients.gui.client_api import LibraryClient, LibraryError, ServerUnavailable
from clients.gui.app import App, main

__all__ = ["LibraryClient", "LibraryError", "ServerUnavailable", "App", "main"]
