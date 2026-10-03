#!/usr/bin/env python3
"""Multithreaded TCP server for the library system with CAT-2 Collaborative Lending.

Every client connection gets its own thread. All database access goes through
one shared Library object protected by a lock, so threads never interleave
their reads and writes.

Protocol (one JSON object per line, UTF-8):
    request : {"cmd": "search", "args": {"term": "dune"}}
    reply   : {"ok": true,  "data": ...}
              {"ok": false, "error": "message"}

Run:  python -m server.server --demo
"""

import argparse
import json
import socket
import sys
import threading
from pathlib import Path

# Ensure project root is in sys.path when running as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import (
    CAT2_SLOTS,
    CAT2_SUBJECTS,
    DB_FILE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    SLOT_EXAM_DAYS,
)
from core.database import Library

DEMO_BOOKS = [
    # General catalogue
    ("Dune", "Frank Herbert", "9780441172719", 2),
    ("The Hobbit", "J.R.R. Tolkien", "9780547928227", 3),
    ("Neuromancer", "William Gibson", "9780441569595", 1),
    ("Pride and Prejudice", "Jane Austen", "9780141439518", 2),
    ("Python Crash Course", "Eric Matthes", "9781593279288", 2),
    # CAT-2 Open Book Specific Course Textbooks (limited copies for collaborative lending)
    ("Python Programming: An Intro to Computer Science (CSE2004)", "John Zelle", "9781590282755", 1),
    ("The C++ Programming Language (ECE2002)", "Bjarne Stroustrup", "9780321563842", 1),
    ("Discrete Mathematics and Its Applications (MAT2002)", "Kenneth Rosen", "9780073383095", 1),
    ("Introduction to the Theory of Computation (CSE3011)", "Michael Sipser", "9781133187790", 1),
    ("Principles of Management (MGT2003)", "Harold Koontz", "9780070356078", 1),
]

DEMO_MEMBERS = [
    ("Asha Verma (Slot A1)", "asha@example.com"),
    ("Ravi Patel (Slot C1)", "ravi@example.com"),
    ("Sneha Roy (Slot B1)", "sneha@example.com"),
    ("Arjun Kumar (Slot D1)", "arjun@example.com"),
]


def rows(result):
    """Turn sqlite3.Row objects into plain dicts so they can become JSON."""
    return [dict(r) for r in result]


class LibraryServer:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, db_path=DB_FILE):
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
                int(a["book_id"]), int(a["member_id"])
            ).isoformat(),
            "return": lambda a: self.lib.return_book(
                int(a["book_id"]), int(a["member_id"])
            ),
            "loans": lambda a: rows(self.lib.active_loans()),
            "overdue": lambda a: rows(self.lib.overdue_loans()),
            # CAT-2 Open Book Collaborative Lending Commands
            "cat2_metadata": lambda a: {
                "subjects": CAT2_SUBJECTS,
                "slots": CAT2_SLOTS,
                "slot_days": SLOT_EXAM_DAYS,
            },
            "collab_checkout": self.collab_checkout,
            "collab_request": self.collab_request,
            "list_collab_requests": lambda a: rows(self.lib.list_collab_requests(a.get("subject_code"))),
            "accept_collab_request": self.accept_collab_request,
            "collab_handover": lambda a: self.lib.collab_handover(int(a["collab_id"])),
            "collab_return": lambda a: self.lib.collab_return(int(a["collab_id"])),
            "active_collab_loans": lambda a: rows(self.lib.active_collab_loans()),
            "all_collab_loans": lambda a: rows(self.lib.all_collab_loans()),
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

    def collab_checkout(self, a):
        book_id = int(a["book_id"])
        subject_code = str(a["subject_code"])
        member1_id = int(a["member1_id"])
        slot1 = str(a["slot1"])
        member2_id = int(a["member2_id"])
        slot2 = str(a["slot2"])
        return self.lib.collab_checkout(book_id, subject_code, member1_id, slot1, member2_id, slot2)

    def collab_request(self, a):
        book_id = int(a["book_id"])
        subject_code = str(a["subject_code"])
        member_id = int(a["member_id"])
        slot = str(a["slot"])
        return self.lib.create_collab_request(book_id, subject_code, member_id, slot)

    def accept_collab_request(self, a):
        request_id = int(a["request_id"])
        joining_member_id = int(a["joining_member_id"])
        joining_slot = str(a["joining_slot"])
        return self.lib.accept_collab_request(request_id, joining_member_id, joining_slot)

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
    existing_books = {b["isbn"] for b in lib.search_books("")}
    for title, author, isbn, copies in DEMO_BOOKS:
        if isbn not in existing_books:
            lib.add_book(title, author, isbn, copies)
    existing_members = {m["email"] for m in lib.list_members()}
    for name, email in DEMO_MEMBERS:
        if email not in existing_members:
            lib.add_member(name, email)
    print("Checked and updated demo books and members.")


def main(args=None):
    parser = argparse.ArgumentParser(description="Library management TCP server")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="use 0.0.0.0 to accept connections from other computers")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DB_FILE)
    parser.add_argument("--demo", action="store_true", help="add sample data if the database is empty")
    parsed_args = parser.parse_args(args)

    server = LibraryServer(parsed_args.host, parsed_args.port, parsed_args.db)
    if parsed_args.demo:
        seed_demo_data(server.lib)
    server.serve_forever()


if __name__ == "__main__":
    main()
