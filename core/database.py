"""Library Data Access Layer - handles SQLite persistence and business rules."""

import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.config import DB_FILE, FINE_PER_DAY, LOAN_DAYS, MAX_LOANS


class Library:
    """Encapsulates all database interactions and relational operations for the library."""

    def __init__(self, path: str = DB_FILE, check_same_thread: bool = True):
        # The network server shares one connection between threads and
        # protects it with its own lock, so it passes check_same_thread=False.
        self.db = sqlite3.connect(path, check_same_thread=check_same_thread)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                isbn TEXT UNIQUE NOT NULL,
                copies INTEGER NOT NULL CHECK (copies >= 0),
                available INTEGER NOT NULL CHECK (available >= 0)
            );
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL REFERENCES books(id),
                member_id INTEGER NOT NULL REFERENCES members(id),
                borrowed_on TEXT NOT NULL,
                due_on TEXT NOT NULL,
                returned_on TEXT
            );
        """)

    # ---------- books ----------
    def add_book(self, title: str, author: str, isbn: str, copies: int = 1) -> int:
        """Add a new book title to the catalog. Returns new book ID."""
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO books (title, author, isbn, copies, available) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (title, author, isbn, copies, copies)
                )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"A book with ISBN {isbn} already exists.")

    def remove_book(self, book_id: int) -> None:
        """Remove a book from the catalog if it is not currently on loan."""
        if self.db.execute(
            "SELECT 1 FROM loans WHERE book_id=? AND returned_on IS NULL",
            (book_id,)
        ).fetchone():
            raise ValueError("Cannot remove a book that is currently on loan.")
        with self.db:
            cur = self.db.execute("DELETE FROM books WHERE id=?", (book_id,))
        if cur.rowcount == 0:
            raise ValueError("Book not found.")

    def search_books(self, term: str = "") -> List[sqlite3.Row]:
        """Search books by title, author, or ISBN."""
        like = f"%{term}%"
        return self.db.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? "
            "ORDER BY title",
            (like, like, like)
        ).fetchall()

    # ---------- members ----------
    def add_member(self, name: str, email: str) -> int:
        """Register a new library member. Returns new member ID."""
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO members (name, email) VALUES (?, ?)",
                    (name, email)
                )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"A member with email {email} already exists.")

    def list_members(self) -> List[sqlite3.Row]:
        """Return list of all registered library members."""
        return self.db.execute("SELECT * FROM members ORDER BY name").fetchall()

    # ---------- loans ----------
    def checkout(self, book_id: int, member_id: int) -> date:
        """Check out a book copy to a member. Returns due date."""
        book = self.db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        member = self.db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        if not book:
            raise ValueError("Book not found.")
        if not member:
            raise ValueError("Member not found.")
        if book["available"] < 1:
            raise ValueError("No copies available.")
        active = self.db.execute(
            "SELECT COUNT(*) FROM loans WHERE member_id=? AND returned_on IS NULL",
            (member_id,)
        ).fetchone()[0]
        if active >= MAX_LOANS:
            raise ValueError(f"{member['name']} already has {MAX_LOANS} books out.")
        if self.db.execute(
            "SELECT 1 FROM loans WHERE book_id=? AND member_id=? AND returned_on IS NULL",
            (book_id, member_id)
        ).fetchone():
            raise ValueError("Member already has a copy of this book.")

        today = date.today()
        due = today + timedelta(days=LOAN_DAYS)
        with self.db:
            self.db.execute(
                "INSERT INTO loans (book_id, member_id, borrowed_on, due_on) "
                "VALUES (?, ?, ?, ?)",
                (book_id, member_id, today.isoformat(), due.isoformat())
            )
            self.db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
        return due

    def return_book(self, book_id: int, member_id: int) -> float:
        """Mark a book as returned. Returns fine amount owed (if any)."""
        loan = self.db.execute(
            "SELECT * FROM loans WHERE book_id=? AND member_id=? AND returned_on IS NULL",
            (book_id, member_id)
        ).fetchone()
        if not loan:
            raise ValueError("No matching active loan found.")
        today = date.today()
        days_late = max(0, (today - date.fromisoformat(loan["due_on"])).days)
        with self.db:
            self.db.execute(
                "UPDATE loans SET returned_on=? WHERE id=?",
                (today.isoformat(), loan["id"])
            )
            self.db.execute("UPDATE books SET available = available + 1 WHERE id=?", (book_id,))
        return days_late * FINE_PER_DAY

    def active_loans(self, member_id: Optional[int] = None) -> List[sqlite3.Row]:
        """Return all active (unreturned) loans, optionally filtered by member."""
        query = """
            SELECT l.*, b.title, m.name FROM loans l
            JOIN books b ON b.id = l.book_id
            JOIN members m ON m.id = l.member_id
            WHERE l.returned_on IS NULL"""
        params = ()
        if member_id:
            query += " AND l.member_id = ?"
            params = (member_id,)
        return self.db.execute(query + " ORDER BY l.due_on", params).fetchall()

    def overdue_loans(self) -> List[sqlite3.Row]:
        """Return all active loans whose due date is prior to today."""
        today = date.today().isoformat()
        return [l for l in self.active_loans() if l["due_on"] < today]

    def close(self) -> None:
        """Close SQLite connection."""
        self.db.close()
