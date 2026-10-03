"""Library Data Access Layer - handles SQLite persistence and collaborative lending business rules."""

import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.config import (
    CAT2_SLOTS,
    CAT2_SUBJECTS,
    DB_FILE,
    FINE_PER_DAY,
    LOAN_DAYS,
    MAX_LOANS,
    SLOT_EXAM_DAYS,
)


class Library:
    """Encapsulates all database interactions, relational operations, and collaborative lending."""

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

            -- CAT-2 Open Book Collaborative Lending Tables
            CREATE TABLE IF NOT EXISTS collaborative_loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL REFERENCES books(id),
                subject_code TEXT NOT NULL,
                member1_id INTEGER NOT NULL REFERENCES members(id),
                slot1 TEXT NOT NULL,
                exam1_date TEXT NOT NULL,
                member2_id INTEGER NOT NULL REFERENCES members(id),
                slot2 TEXT NOT NULL,
                exam2_date TEXT NOT NULL,
                borrowed_on TEXT NOT NULL,
                handover_date TEXT NOT NULL,
                due_on TEXT NOT NULL,
                current_holder_id INTEGER NOT NULL REFERENCES members(id),
                handover_confirmed INTEGER NOT NULL DEFAULT 0,
                returned_on TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE_PHASE_1'
            );

            CREATE TABLE IF NOT EXISTS collaborative_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL REFERENCES books(id),
                subject_code TEXT NOT NULL,
                member_id INTEGER NOT NULL REFERENCES members(id),
                slot TEXT NOT NULL,
                exam_date TEXT NOT NULL,
                created_on TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN'
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
        ).fetchone() or self.db.execute(
            "SELECT 1 FROM collaborative_loans WHERE book_id=? AND returned_on IS NULL",
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

    # ---------- standard loans ----------
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

    # ---------- CAT-2 Open Book Collaborative Lending ----------
    @staticmethod
    def get_exam_date(slot: str, base_date: Optional[date] = None) -> date:
        """Calculate the scheduled CAT-2 exam date for a given university slot."""
        norm_slot = slot.strip().upper()
        if norm_slot not in SLOT_EXAM_DAYS:
            raise ValueError(f"Unknown slot '{slot}'. Valid slots: {', '.join(CAT2_SLOTS)}")
        if base_date is None:
            base_date = date.today()
        offset_days = SLOT_EXAM_DAYS[norm_slot]
        return base_date + timedelta(days=offset_days)

    def collab_checkout(
        self,
        book_id: int,
        subject_code: str,
        member1_id: int,
        slot1: str,
        member2_id: int,
        slot2: str,
        base_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Check out a book collaboratively to two students with different slots of the same subject."""
        norm_s1 = slot1.strip().upper()
        norm_s2 = slot2.strip().upper()
        norm_sub = subject_code.strip().upper()

        if member1_id == member2_id:
            raise ValueError("Collaborative lending requires two different students.")

        if norm_s1 == norm_s2:
            raise ValueError(
                f"Both students are in Slot {norm_s1}. Their CAT-2 open-book exams are scheduled "
                f"at the exact same time! Collaborative lending requires students from different slots "
                f"(e.g., Slot {norm_s1} and a different slot)."
            )

        book = self.db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not book:
            raise ValueError(f"Book with ID #{book_id} not found.")
        if book["available"] < 1:
            raise ValueError(f"No copies of '{book['title']}' currently available for co-lending.")

        m1 = self.db.execute("SELECT * FROM members WHERE id=?", (member1_id,)).fetchone()
        m2 = self.db.execute("SELECT * FROM members WHERE id=?", (member2_id,)).fetchone()
        if not m1:
            raise ValueError(f"Member with ID #{member1_id} not found.")
        if not m2:
            raise ValueError(f"Member with ID #{member2_id} not found.")

        # Calculate exam dates
        exam1 = self.get_exam_date(norm_s1, base_date)
        exam2 = self.get_exam_date(norm_s2, base_date)

        # Automatic chronological ordering: Phase 1 goes to whichever student has the earlier exam
        if exam1 < exam2:
            p1_id, p1_slot, p1_exam = member1_id, norm_s1, exam1
            p2_id, p2_slot, p2_exam = member2_id, norm_s2, exam2
            p1_name, p2_name = m1["name"], m2["name"]
        else:
            p1_id, p1_slot, p1_exam = member2_id, norm_s2, exam2
            p2_id, p2_slot, p2_exam = member1_id, norm_s1, exam1
            p1_name, p2_name = m2["name"], m1["name"]

        today = date.today()
        # Handover date is the day after Exam 1
        handover_date = p1_exam + timedelta(days=1)
        # Final due date is the day after Exam 2
        due_on = p2_exam + timedelta(days=1)

        with self.db:
            cur = self.db.execute(
                """INSERT INTO collaborative_loans (
                    book_id, subject_code, member1_id, slot1, exam1_date,
                    member2_id, slot2, exam2_date, borrowed_on, handover_date,
                    due_on, current_holder_id, handover_confirmed, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'ACTIVE_PHASE_1')""",
                (
                    book_id, norm_sub, p1_id, p1_slot, p1_exam.isoformat(),
                    p2_id, p2_slot, p2_exam.isoformat(), today.isoformat(),
                    handover_date.isoformat(), due_on.isoformat(), p1_id
                )
            )
            collab_id = cur.lastrowid
            self.db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))

        return {
            "collab_id": collab_id,
            "book_id": book_id,
            "book_title": book["title"],
            "subject_code": norm_sub,
            "phase1_member": {"id": p1_id, "name": p1_name, "slot": p1_slot, "exam_date": p1_exam.isoformat()},
            "phase2_member": {"id": p2_id, "name": p2_name, "slot": p2_slot, "exam_date": p2_exam.isoformat()},
            "handover_date": handover_date.isoformat(),
            "due_on": due_on.isoformat(),
            "status": "ACTIVE_PHASE_1"
        }

    def create_collab_request(
        self,
        book_id: int,
        subject_code: str,
        member_id: int,
        slot: str,
        base_date: Optional[date] = None
    ) -> int:
        """Post a request looking for a co-lending partner from a different slot for CAT-2."""
        norm_slot = slot.strip().upper()
        norm_sub = subject_code.strip().upper()

        book = self.db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not book:
            raise ValueError(f"Book #{book_id} not found.")
        member = self.db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            raise ValueError(f"Member #{member_id} not found.")

        exam_date = self.get_exam_date(norm_slot, base_date)
        today = date.today().isoformat()

        # Check if identical open request already exists
        existing = self.db.execute(
            """SELECT 1 FROM collaborative_requests
               WHERE book_id=? AND member_id=? AND subject_code=? AND status='OPEN'""",
            (book_id, member_id, norm_sub)
        ).fetchone()
        if existing:
            raise ValueError("You already have an open co-lending request for this book and subject.")

        with self.db:
            cur = self.db.execute(
                """INSERT INTO collaborative_requests (
                    book_id, subject_code, member_id, slot, exam_date, created_on, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'OPEN')""",
                (book_id, norm_sub, member_id, norm_slot, exam_date.isoformat(), today)
            )
            return cur.lastrowid

    def list_collab_requests(self, subject_code: Optional[str] = None) -> List[sqlite3.Row]:
        """List open co-lending requests waiting for a partner from a different slot."""
        query = """
            SELECT cr.*, b.title as book_title, b.isbn as book_isbn, b.available,
                   m.name as member_name, m.email as member_email
            FROM collaborative_requests cr
            JOIN books b ON b.id = cr.book_id
            JOIN members m ON m.id = cr.member_id
            WHERE cr.status = 'OPEN'
        """
        params = ()
        if subject_code:
            query += " AND cr.subject_code = ?"
            params = (subject_code.strip().upper(),)
        query += " ORDER BY cr.created_on DESC"
        return self.db.execute(query, params).fetchall()

    def accept_collab_request(
        self,
        request_id: int,
        joining_member_id: int,
        joining_slot: str,
        base_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Pair with an existing open request to establish a collaborative loan."""
        req = self.db.execute(
            "SELECT * FROM collaborative_requests WHERE id=?", (request_id,)
        ).fetchone()
        if not req:
            raise ValueError(f"Request #{request_id} not found.")
        if req["status"] != "OPEN":
            raise ValueError(f"Request #{request_id} is no longer open.")

        collab_result = self.collab_checkout(
            book_id=req["book_id"],
            subject_code=req["subject_code"],
            member1_id=req["member_id"],
            slot1=req["slot"],
            member2_id=joining_member_id,
            slot2=joining_slot,
            base_date=base_date
        )

        with self.db:
            self.db.execute(
                "UPDATE collaborative_requests SET status='PAIRED' WHERE id=?",
                (request_id,)
            )

        return collab_result

    def collab_handover(self, collab_id: int) -> Dict[str, Any]:
        """Confirm that Student 1 has handed the book over to Student 2 after Exam 1."""
        loan = self.db.execute(
            "SELECT * FROM collaborative_loans WHERE id=?", (collab_id,)
        ).fetchone()
        if not loan:
            raise ValueError(f"Collaborative loan #{collab_id} not found.")
        if loan["status"] != "ACTIVE_PHASE_1":
            raise ValueError(f"Loan #{collab_id} is in status '{loan['status']}', handover already completed.")

        with self.db:
            self.db.execute(
                """UPDATE collaborative_loans
                   SET current_holder_id = member2_id,
                       handover_confirmed = 1,
                       status = 'ACTIVE_PHASE_2'
                   WHERE id = ?""",
                (collab_id,)
            )
        return {"collab_id": collab_id, "status": "ACTIVE_PHASE_2", "current_holder_id": loan["member2_id"]}

    def collab_return(self, collab_id: int) -> float:
        """Mark collaborative book as returned to the library after Exam 2."""
        loan = self.db.execute(
            "SELECT * FROM collaborative_loans WHERE id=?", (collab_id,)
        ).fetchone()
        if not loan:
            raise ValueError(f"Collaborative loan #{collab_id} not found.")
        if loan["returned_on"] is not None:
            raise ValueError(f"Collaborative loan #{collab_id} was already returned.")

        today = date.today()
        days_late = max(0, (today - date.fromisoformat(loan["due_on"])).days)
        with self.db:
            self.db.execute(
                "UPDATE collaborative_loans SET returned_on=?, status='RETURNED' WHERE id=?",
                (today.isoformat(), collab_id)
            )
            self.db.execute("UPDATE books SET available = available + 1 WHERE id=?", (loan["book_id"],))

        return days_late * FINE_PER_DAY

    def active_collab_loans(self) -> List[sqlite3.Row]:
        """Return all active (unreturned) collaborative loans with detailed student metadata."""
        query = """
            SELECT cl.*,
                   b.title as book_title, b.isbn as book_isbn,
                   m1.name as member1_name, m1.email as member1_email,
                   m2.name as member2_name, m2.email as member2_email,
                   ch.name as current_holder_name
            FROM collaborative_loans cl
            JOIN books b ON b.id = cl.book_id
            JOIN members m1 ON m1.id = cl.member1_id
            JOIN members m2 ON m2.id = cl.member2_id
            JOIN members ch ON ch.id = cl.current_holder_id
            WHERE cl.returned_on IS NULL
            ORDER BY cl.due_on ASC
        """
        return self.db.execute(query).fetchall()

    def all_collab_loans(self) -> List[sqlite3.Row]:
        """Return all collaborative loans (active and returned)."""
        query = """
            SELECT cl.*,
                   b.title as book_title, b.isbn as book_isbn,
                   m1.name as member1_name, m1.email as member1_email,
                   m2.name as member2_name, m2.email as member2_email,
                   ch.name as current_holder_name
            FROM collaborative_loans cl
            JOIN books b ON b.id = cl.book_id
            JOIN members m1 ON m1.id = cl.member1_id
            JOIN members m2 ON m2.id = cl.member2_id
            JOIN members ch ON ch.id = cl.current_holder_id
            ORDER BY cl.id DESC
        """
        return self.db.execute(query).fetchall()

    def close(self) -> None:
        """Close SQLite connection."""
        self.db.close()
