#!/usr/bin/env python3
"""Multithreaded TCP server for the library system.

Every client connection gets its own thread. All database access goes through
one shared Library object protected by a lock, so threads never interleave
their reads and writes.

Protocol (one JSON object per line, UTF-8):
    request : {"cmd": "search", "args": {"term": "dune"}}
    reply   : {"ok": true,  "data": ...}
              {"ok": false, "error": "message"}

Run:  python3 server.py --demo
"""

import argparse
import json
import socket
import threading

from library import Library

DEMO_BOOKS = [
    ("Dune", "Frank Herbert", "9780441172719", 2),
    ("The Hobbit", "J.R.R. Tolkien", "9780547928227", 3),
    ("Neuromancer", "William Gibson", "9780441569595", 1),
    ("Pride and Prejudice", "Jane Austen", "9780141439518", 2),
    ("Python Crash Course", "Eric Matthes", "9781593279288", 2),
]
DEMO_MEMBERS = [("Asha Verma", "asha@example.com"), ("Ravi Patel", "ravi@example.com")]


def rows(result):
    """Turn sqlite3.Row objects into plain dicts so they can become JSON."""
    return [dict(r) for r in result]


class LibraryServer:
    def __init__(self, host, port, db_path):
        self.host, self.port = host, port
        self.lib = Library(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.commands = {
            "ping": lambda a: "pong",
            "search": lambda a: rows(self.lib.search_books(a.get("term", ""))),
            "add_book": self.add_book,
            "remove_book": lambda a: self.lib.remove_book(int(a["book_id"])),
            "list_members": lambda a: rows(self.lib.list_members()),
            "add_member": self.add_member,
            "checkout": lambda a: self.lib.checkout(
                int(a["book_id"]), int(a["member_id"])).isoformat(),
            "return": lambda a: self.lib.return_book(
                int(a["book_id"]), int(a["member_id"])),
            "loans": lambda a: rows(self.lib.active_loans()),
            "overdue": lambda a: rows(self.lib.overdue_loans()),
        }

    # -- commands that need validation ---------------------------------
    def add_book(self, a):
        title, author, isbn = (str(a[k]).strip() for k in ("title", "author", "isbn"))
        copies = int(a.get("copies", 1))
        if not (title and author and isbn) or copies < 1:
            raise ValueError("Title, author and ISBN are required; copies must be at least 1.")
        return self.lib.add_book(title, author, isbn, copies)

    def add_member(self, a):
        name, email = str(a["name"]).strip(), str(a["email"]).strip()
        if not name or "@" not in email:
            raise ValueError("Enter a name and a valid email address.")
        return self.lib.add_member(name, email)

    # -- request handling ----------------------------------------------
    def process(self, line):
        """Turn one request line into one reply dict. Never raises."""
        try:
            request = json.loads(line)
            func = self.commands[request["cmd"]]
            args = request.get("args") or {}
        except (ValueError, KeyError, TypeError, AttributeError):
            return {"ok": False, "error": "Bad request."}
        try:
            with self.lock:                      # one database operation at a time
                return {"ok": True, "data": func(args)}
        except KeyError as e:
            return {"ok": False, "error": f"Missing field {e}."}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:                   # keep the thread alive no matter what
            return {"ok": False, "error": f"Server error: {e}"}

    def handle_client(self, conn, addr):
        name = threading.current_thread().name
        print(f"[{name}] connected    {addr[0]}:{addr[1]}")
        try:
            with conn, conn.makefile("rw", encoding="utf-8", newline="\n") as stream:
                for line in stream:              # blocks until a full line arrives
                    reply = self.process(line)
                    print(f"[{name}] {line.strip()[:70]}  ->  {'ok' if reply['ok'] else reply['error']}")
                    stream.write(json.dumps(reply) + "\n")
                    stream.flush()
        except OSError:
            pass                                  # client vanished mid-conversation
        print(f"[{name}] disconnected {addr[0]}:{addr[1]}")

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen()
            print(f"Library server listening on {self.host}:{self.port}  (Ctrl+C to stop)")
            try:
                while True:
                    conn, addr = srv.accept()
                    threading.Thread(target=self.handle_client, args=(conn, addr),
                                     daemon=True).start()
            except KeyboardInterrupt:
                print("\nShutting down.")


def seed_demo_data(lib):
    if lib.search_books(""):
        return
    for title, author, isbn, copies in DEMO_BOOKS:
        lib.add_book(title, author, isbn, copies)
    for name, email in DEMO_MEMBERS:
        lib.add_member(name, email)
    print("Added demo books and members.")


def main():
    parser = argparse.ArgumentParser(description="Library management TCP server")
    parser.add_argument("--host", default="127.0.0.1",
                        help="use 0.0.0.0 to accept connections from other computers")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--db", default="library.db")
    parser.add_argument("--demo", action="store_true", help="add sample data if the database is empty")
    args = parser.parse_args()

    server = LibraryServer(args.host, args.port, args.db)
    if args.demo:
        seed_demo_data(server.lib)
    server.serve_forever()


if __name__ == "__main__":
    main()
