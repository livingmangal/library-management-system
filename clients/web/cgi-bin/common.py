"""Helpers shared by the CGI scripts."""

import html
import json
import os
import socket
import sys
import urllib.parse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.config import DEFAULT_HOST, DEFAULT_PORT
    HOST = os.environ.get("LIBRARY_HOST", DEFAULT_HOST)
    PORT = int(os.environ.get("LIBRARY_PORT", DEFAULT_PORT))
except Exception:
    HOST = os.environ.get("LIBRARY_HOST", "127.0.0.1")
    PORT = int(os.environ.get("LIBRARY_PORT", 5050))

sys.stdout.reconfigure(encoding="utf-8")


def form_data():
    """Read submitted form fields from the query string (GET) or the body (POST)."""
    if os.environ.get("REQUEST_METHOD", "GET") == "POST":
        length = int(os.environ.get("CONTENT_LENGTH") or 0)
        raw = sys.stdin.buffer.read(length).decode("utf-8")
    else:
        raw = os.environ.get("QUERY_STRING", "")
    return {key: values[0] for key, values in urllib.parse.parse_qs(raw).items()}


def ask_server(cmd, **args):
    """The CGI script is itself a client of the library TCP server."""
    with socket.create_connection((HOST, PORT), timeout=5) as sock:
        stream = sock.makefile("rw", encoding="utf-8", newline="\n")
        stream.write(json.dumps({"cmd": cmd, "args": args}) + "\n")
        stream.flush()
        reply = json.loads(stream.readline())
    if not reply["ok"]:
        raise ValueError(reply["error"])
    return reply["data"]


def esc(value):
    """Escape user-supplied text before putting it in HTML."""
    return html.escape(str(value))


def page(title, body):
    """Print the CGI header (Content-Type, blank line) followed by a full HTML page."""
    print("Content-Type: text/html; charset=utf-8")
    print()
    print(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; background: #f4f1ea; color: #222; }}
  h1 {{ background: #2c3e50; color: white; padding: .6rem 1rem; border-radius: 4px; }}
  table {{ border-collapse: collapse; width: 100%; background: white; margin-top: 1rem; border-radius: 4px; overflow: hidden; }}
  th, td {{ border: 1px solid #ccc; padding: .5rem .7rem; text-align: left; }}
  th {{ background: #e0dcd0; font-weight: bold; }}
  .none {{ color: #777; font-style: italic; }} .error {{ color: #c0392b; font-weight: bold; }} .ok {{ color: #1e8449; font-weight: bold; }}
  a {{ color: #2980b9; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>{esc(title)}</h1>
{body}
<p><a href="/index.html">&larr; Back to the library home page</a></p>
</body>
</html>""")
