"""Persistent connection client library used by GUI and CGI components."""

import json
import socket
import sys
import threading
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import DEFAULT_HOST, DEFAULT_PORT


class LibraryError(Exception):
    """The server understood the request but refused it (e.g. 'No copies available')."""


class ServerUnavailable(LibraryError):
    """The server could not be reached."""


class LibraryClient:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=5):
        self.host, self.port, self.timeout = host, port, timeout
        self._stream = None
        self._lock = threading.Lock()      # several worker threads may call request()

    @property
    def connected(self):
        return self._stream is not None

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._stream = sock.makefile("rw", encoding="utf-8", newline="\n")
        sock.close()                        # the file object keeps its own reference

    def close(self):
        if self._stream:
            try:
                self._stream.close()
            except OSError:
                pass
        self._stream = None

    def request(self, cmd, **args):
        """Send one command and return the server's data (or raise LibraryError)."""
        message = json.dumps({"cmd": cmd, "args": args}) + "\n"
        with self._lock:
            for attempt in range(2):
                try:
                    if self._stream is None:
                        self._connect()
                    self._stream.write(message)
                    self._stream.flush()
                    line = self._stream.readline()
                    if not line:
                        raise ConnectionError("server closed the connection")
                    break
                except ConnectionError:
                    # Stale connection (e.g. server restarted): reconnect once.
                    self.close()
                    if attempt == 1:
                        raise ServerUnavailable("Cannot reach the library server.")
                except OSError as e:          # timeouts etc. - do not resend, it may have run
                    self.close()
                    raise ServerUnavailable(f"Cannot reach the library server ({e}).")
        reply = json.loads(line)
        if not reply["ok"]:
            raise LibraryError(reply["error"])
        return reply["data"]
