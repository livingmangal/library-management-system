#!/usr/bin/env python3
"""Web server: serves index.html and runs CGI programs under ./cgi-bin.

Run:  python -m clients.web.web_server [--port 8000]
"""

import argparse
import os
import sys
import warnings
from http.server import CGIHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import WEB_PORT

warnings.filterwarnings("ignore", category=DeprecationWarning)


class Handler(CGIHTTPRequestHandler):
    cgi_directories = ["/cgi-bin"]      # any .py file under here is executed, not downloaded
    have_fork = False                   # run scripts via the Python interpreter


def main(args=None):
    parser = argparse.ArgumentParser(description="Web front end for the library")
    parser.add_argument("--port", type=int, default=WEB_PORT)
    parsed_args = parser.parse_args(args)

    web_dir = Path(__file__).resolve().parent
    os.chdir(str(web_dir))
    server = ThreadingHTTPServer(("127.0.0.1", parsed_args.port), Handler)
    print(f"Web server on http://localhost:{parsed_args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
