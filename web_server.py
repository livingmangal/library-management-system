#!/usr/bin/env python3
"""Tiny web server: serves index.html and runs the scripts in ./cgi-bin as CGI programs.

Run:  python3 web_server.py      then open http://localhost:8000
(The library TCP server, server.py, must also be running.)

Note: http.server's CGI support is deprecated in Python 3.13 and removed in 3.15.
It is fine for learning; a real site would use a framework such as Flask.
"""

import argparse
import os
import warnings
from http.server import CGIHTTPRequestHandler, ThreadingHTTPServer

warnings.filterwarnings("ignore", category=DeprecationWarning)


class Handler(CGIHTTPRequestHandler):
    cgi_directories = ["/cgi-bin"]      # any .py file under here is executed, not downloaded
    have_fork = False                   # run scripts via the Python interpreter, so they need
                                        # no "chmod +x" and behave the same on Windows/macOS/Linux


def main():
    parser = argparse.ArgumentParser(description="Web front end for the library")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Web server on http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
