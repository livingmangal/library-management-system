# Library Management System

A multi-tier Library Management System built entirely with the Python standard library. It features a SQLite database engine, a multithreaded TCP backend server, and multiple client interfaces (Desktop GUI, Web portal, and CLI).

---

## 🏛 Architecture & Project Structure

The project is structured into modular layers with clear separation of concerns:

```
library-management-system/
│
├── core/                        # Data access layer & business logic
│   ├── __init__.py
│   ├── config.py                # Centralized configuration & constants
│   └── database.py              # Library SQLite model & constraints
│
├── server/                      # Multithreaded TCP backend server
│   ├── __init__.py
│   └── server.py                # Protocol handlers & thread synchronization
│
├── clients/                     # Client presentation interfaces
│   ├── cli.py                   # Interactive terminal interface
│   ├── gui/                     # Desktop graphical user interface (Tkinter)
│   │   ├── __init__.py
│   │   ├── app.py               # Async event-driven GUI window
│   │   └── client_api.py        # Resilient socket connection wrapper
│   └── web/                     # Web client
│       ├── __init__.py
│       ├── web_server.py        # HTTP CGI server
│       ├── index.html           # Web portal UI
│       └── cgi-bin/             # CGI request handlers (search & register)
│
├── tests/                       # Automated test suite
│   ├── __init__.py
│   ├── test_database.py         # Unit tests for DAL and business rules
│   └── test_server.py           # Protocol and command tests
│
├── run.py                       # Unified project runner CLI
├── library.py                   # Backward-compatible entrypoint
├── server.py                    # Backward-compatible server entrypoint
├── client_gui.py                # Backward-compatible GUI entrypoint
├── web_server.py                # Backward-compatible web entrypoint
├── client_api.py                # Backward-compatible client library
└── .gitignore                   # Ignore caches, logs, and database files
```

---

## 🚀 Quick Start

### Requirements
* **Python 3.10+** (Tested on Python 3.13)
* **Zero external dependencies**: Uses only Python standard library (`sqlite3`, `tkinter`, `socket`, `http.server`, etc.).

---

### Running with the Unified Runner (`run.py`)

The project includes a convenient unified launcher [run.py](file:///c:/Users/hiima/Desktop/library-management-system/run.py):

#### 1. Start the TCP Backend Server
```powershell
python run.py server --demo
```
*(The `--demo` flag seeds sample books and members if the database is newly initialized.)*

#### 2. Launch Client Frontends

* **Desktop GUI Application (Tkinter)**:
  ```powershell
  python run.py gui
  ```

* **Web Application**:
  ```powershell
  python run.py web
  ```
  Then open your browser at: **[http://localhost:8000](http://localhost:8000)**

* **Terminal Interactive CLI (Standalone)**:
  ```powershell
  python run.py cli
  ```

---

### Running with Direct Scripts (Backward-Compatible)

You can also run components directly using their root entrypoints:

```powershell
# 1. Start Server
python server.py --demo

# 2. Start Desktop GUI (in a new terminal)
python client_gui.py

# 3. Start Web Server (in a new terminal)
python web_server.py

# 4. Standalone CLI
python library.py
```

---

## 🧪 Running Automated Tests

Run the full automated test suite using `run.py`:

```powershell
python run.py test
```

Or using Python's built-in test discovery:
```powershell
python -m unittest discover tests
```

---

## ⚙️ Configuration & Environment Variables

Default settings can be configured via [core/config.py](file:///c:/Users/hiima/Desktop/library-management-system/core/config.py) or overridden with environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LIBRARY_HOST` | `127.0.0.1` | TCP server listening/connect IP |
| `LIBRARY_PORT` | `5050` | TCP server listening/connect port |
| `LIBRARY_WEB_PORT` | `8000` | HTTP web server port |
| `LIBRARY_DB` | `library.db` | SQLite database file location |
| `LIBRARY_LOAN_DAYS` | `14` | Default duration (days) for book loans |
| `LIBRARY_MAX_LOANS` | `3` | Maximum active loans per member |
| `LIBRARY_FINE_PER_DAY` | `0.50` | Overdue fee per day in dollars |

---

## 🔌 TCP Protocol Specification

The TCP server communicates using newline-delimited UTF-8 JSON messages.

### Request Format
```json
{"cmd": "<command_name>", "args": { ... }}
```

### Reply Format
```json
{"ok": true, "data": ...}
{"ok": false, "error": "<error message>"}
```

### Available Commands
* `ping` - Check server liveness (replies `"pong"`).
* `search` - Search books by title, author, or ISBN (`{"term": "..."}`).
* `add_book` - Add a book (`{"title": "...", "author": "...", "isbn": "...", "copies": 1}`).
* `remove_book` - Remove a book by ID (`{"book_id": 1}`).
* `list_members` - Retrieve all registered members.
* `add_member` - Register a member (`{"name": "...", "email": "..."}`).
* `checkout` - Check out a book (`{"book_id": 1, "member_id": 1}`).
* `return` - Return a book copy (`{"book_id": 1, "member_id": 1}`).
* `loans` - List all active loans.
* `overdue` - List overdue loans.
* `cat2_metadata` - Retrieve timetable subjects, slots, and relative exam days.
* `collab_checkout` - Check out a textbook collaboratively (`{"book_id": 1, "subject_code": "CSE2004", "member1_id": 1, "slot1": "A1", "member2_id": 2, "slot2": "C1"}`).
* `collab_request` - Post an open co-lending partner request (`{"book_id": 1, "subject_code": "CSE2004", "member_id": 1, "slot": "A1"}`).
* `list_collab_requests` - List open co-lending requests looking for slot partners.
* `accept_collab_request` - Pair with an open request (`{"request_id": 1, "joining_member_id": 2, "joining_slot": "C1"}`).
* `collab_handover` - Confirm physical handover from Phase 1 student to Phase 2 student (`{"collab_id": 1}`).
* `collab_return` - Return co-borrowed book to library (`{"collab_id": 1}`).
* `active_collab_loans` - List currently active collaborative loans.
* `all_collab_loans` - List all collaborative loans.

---

## 🤝 CAT-2 Open Book Collaborative Lending

### The Problem
During college CAT-2 Open Book Exams, demand for prescribed textbooks (such as Python Programming, C++, Discrete Mathematics, and Theory of Computation) spikes dramatically. Because library copies are limited, if one student checks out a copy for 14 days, other students have no access during their open-book exams.

### The Solution: Slot-Based Co-Lending
Universities schedule open-book exams by timetable slots (e.g. Slot A1, B1, C1, D1, E1, F1, A2, etc.) on **different exam dates**:
* **Student 1** in **Slot A1** has their CAT-2 exam on **Day 1**.
* **Student 2** in **Slot C1** has their CAT-2 exam on **Day 3**.

Because their exams do not clash:
1. **Phase 1 (Preparation & Exam 1)**: Student 1 holds the book until their exam is finished.
2. **Handover Date**: Student 1 hands over the book to Student 2 on the scheduled handover date (Day 2).
3. **Phase 2 (Preparation & Exam 2)**: Student 2 uses the book for their exam on Day 3.
4. **Final Return**: Student 2 returns the book to the library after their exam.

The system automatically validates that slots do not clash, calculates the non-conflicting handover schedule, tracks custody, and offers a **Matchmaker Board** for students looking for partners in alternate slots.
