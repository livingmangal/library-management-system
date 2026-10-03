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
