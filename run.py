#!/usr/bin/env python3
"""Unified project runner for the Library Management System.

Usage:
    python run.py server [--demo] [--port 5050] [--host 127.0.0.1]
    python run.py gui    [--port 5050] [--host 127.0.0.1]
    python run.py web    [--port 8000]
    python run.py cli
    python run.py test
"""

import argparse
import sys
import unittest


def run_server(args):
    from server.server import main
    main(args)


def run_gui(args):
    from clients.gui.app import main
    main(args)


def run_web(args):
    from clients.web.web_server import main
    main(args)


def run_cli(args):
    from clients.cli import main
    main(args)


def run_tests(args):
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Unified runner for the Library Management System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""commands:
  server   Start the TCP backend server
  gui      Launch the Tkinter desktop GUI
  web      Start the HTTP web server and portal
  cli      Launch the interactive terminal console
  test     Execute the automated test suite
"""
    )
    subparsers = parser.add_subparsers(dest="command", help="Component to run")

    # Server parser
    server_parser = subparsers.add_parser("server", help="Run the TCP backend server")
    server_parser.add_argument("--host", default=None, help="Server host IP")
    server_parser.add_argument("--port", type=int, default=None, help="Server port")
    server_parser.add_argument("--db", default=None, help="SQLite database path")
    server_parser.add_argument("--demo", action="store_true", help="Seed sample data if database is empty")

    # GUI parser
    gui_parser = subparsers.add_parser("gui", help="Run the Tkinter desktop client")
    gui_parser.add_argument("--host", default=None, help="TCP server host to connect to")
    gui_parser.add_argument("--port", type=int, default=None, help="TCP server port")

    # Web parser
    web_parser = subparsers.add_parser("web", help="Run the HTTP web server")
    web_parser.add_argument("--port", type=int, default=None, help="HTTP web server port")

    # CLI parser
    subparsers.add_parser("cli", help="Run the interactive terminal CLI")

    # Test parser
    subparsers.add_parser("test", help="Run the test suite")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    parsed_args, remainder = parser.parse_known_args()

    commands = {
        "server": run_server,
        "gui": run_gui,
        "web": run_web,
        "cli": run_cli,
        "test": run_tests,
    }

    cmd_func = commands.get(parsed_args.command)
    if cmd_func:
        # Pass the remaining CLI arguments to the target component's main()
        # Filter out None values from parsed subparser arguments
        sub_args = []
        for key, val in vars(parsed_args).items():
            if key == "command" or val is None:
                continue
            if isinstance(val, bool):
                if val:
                    sub_args.append(f"--{key}")
            else:
                sub_args.extend([f"--{key}", str(val)])
        cmd_func(sub_args + remainder)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
