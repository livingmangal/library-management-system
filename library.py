#!/usr/bin/env python3
"""Library Management System - standard library only (sqlite3 for storage)."""

import sqlite3
from datetime import date, timedelta

DB_FILE = "library.db"
LOAN_DAYS = 14
MAX_LOANS = 3
FINE_PER_DAY = 0.50


class Library:
    def __init__(self, path=DB_FILE, check_same_thread=True):
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
    def add_book(self, title, author, isbn, copies=1):
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO books (title, author, isbn, copies, available) "
                    "VALUES (?, ?, ?, ?, ?)", (title, author, isbn, copies, copies))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"A book with ISBN {isbn} already exists.")

    def remove_book(self, book_id):
        if self.db.execute("SELECT 1 FROM loans WHERE book_id=? AND returned_on IS NULL",
                           (book_id,)).fetchone():
            raise ValueError("Cannot remove a book that is currently on loan.")
        with self.db:
            cur = self.db.execute("DELETE FROM books WHERE id=?", (book_id,))
        if cur.rowcount == 0:
            raise ValueError("Book not found.")

    def search_books(self, term=""):
        like = f"%{term}%"
        return self.db.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? "
            "ORDER BY title", (like, like, like)).fetchall()

    # ---------- members ----------
    def add_member(self, name, email):
        try:
            with self.db:
                cur = self.db.execute(
                    "INSERT INTO members (name, email) VALUES (?, ?)", (name, email))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"A member with email {email} already exists.")

    def list_members(self):
        return self.db.execute("SELECT * FROM members ORDER BY name").fetchall()

    # ---------- loans ----------
    def checkout(self, book_id, member_id):
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
            (member_id,)).fetchone()[0]
        if active >= MAX_LOANS:
            raise ValueError(f"{member['name']} already has {MAX_LOANS} books out.")
        if self.db.execute(
                "SELECT 1 FROM loans WHERE book_id=? AND member_id=? AND returned_on IS NULL",
                (book_id, member_id)).fetchone():
            raise ValueError("Member already has a copy of this book.")

        today = date.today()
        due = today + timedelta(days=LOAN_DAYS)
        with self.db:
            self.db.execute(
                "INSERT INTO loans (book_id, member_id, borrowed_on, due_on) "
                "VALUES (?, ?, ?, ?)", (book_id, member_id, today.isoformat(), due.isoformat()))
            self.db.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
        return due

    def return_book(self, book_id, member_id):
        loan = self.db.execute(
            "SELECT * FROM loans WHERE book_id=? AND member_id=? AND returned_on IS NULL",
            (book_id, member_id)).fetchone()
        if not loan:
            raise ValueError("No matching active loan found.")
        today = date.today()
        days_late = max(0, (today - date.fromisoformat(loan["due_on"])).days)
        with self.db:
            self.db.execute("UPDATE loans SET returned_on=? WHERE id=?",
                            (today.isoformat(), loan["id"]))
            self.db.execute("UPDATE books SET available = available + 1 WHERE id=?", (book_id,))
        return days_late * FINE_PER_DAY

    def active_loans(self, member_id=None):
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

    def overdue_loans(self):
        today = date.today().isoformat()
        return [l for l in self.active_loans() if l["due_on"] < today]


# ---------- CLI ----------
def ask(prompt):
    return input(prompt).strip()


def ask_int(prompt):
    try:
        return int(ask(prompt))
    except ValueError:
        raise ValueError("Please enter a number.")


def print_books(books):
    if not books:
        print("  No books found.")
        return
    print(f"  {'ID':<4} {'Title':<30} {'Author':<20} {'ISBN':<15} Avail")
    for b in books:
        print(f"  {b['id']:<4} {b['title'][:29]:<30} {b['author'][:19]:<20} "
              f"{b['isbn']:<15} {b['available']}/{b['copies']}")


def print_loans(loans):
    if not loans:
        print("  None.")
        return
    today = date.today()
    for l in loans:
        late = (today - date.fromisoformat(l["due_on"])).days
        flag = f"  OVERDUE by {late} day(s), fine ${late * FINE_PER_DAY:.2f}" if late > 0 else ""
        print(f"  Book {l['book_id']} '{l['title']}' -> {l['name']} (member {l['member_id']}), "
              f"due {l['due_on']}{flag}")


MENU = """
===== Library Management =====
 1. Add book            6. Add member
 2. Remove book         7. List members
 3. Search / list books 8. Show active loans
 4. Check out a book    9. Show overdue loans
 5. Return a book       0. Quit
"""


def main():
    lib = Library()
    while True:
        print(MENU)
        choice = ask("Choose: ")
        try:
            if choice == "1":
                title, author, isbn = ask("Title: "), ask("Author: "), ask("ISBN: ")
                copies = ask_int("Copies: ")
                if not (title and author and isbn) or copies < 1:
                    raise ValueError("All fields are required and copies must be >= 1.")
                print(f"Added book with ID {lib.add_book(title, author, isbn, copies)}.")
            elif choice == "2":
                lib.remove_book(ask_int("Book ID: "))
                print("Book removed.")
            elif choice == "3":
                print_books(lib.search_books(ask("Search (blank for all): ")))
            elif choice == "4":
                due = lib.checkout(ask_int("Book ID: "), ask_int("Member ID: "))
                print(f"Checked out. Due on {due}.")
            elif choice == "5":
                fine = lib.return_book(ask_int("Book ID: "), ask_int("Member ID: "))
                print("Returned." + (f" Late fine: ${fine:.2f}" if fine else ""))
            elif choice == "6":
                name, email = ask("Name: "), ask("Email: ")
                if not name or "@" not in email:
                    raise ValueError("Enter a name and a valid email.")
                print(f"Added member with ID {lib.add_member(name, email)}.")
            elif choice == "7":
                for m in lib.list_members():
                    print(f"  {m['id']:<4} {m['name']:<25} {m['email']}")
            elif choice == "8":
                print_loans(lib.active_loans())
            elif choice == "9":
                print_loans(lib.overdue_loans())
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Invalid choice.")
        except ValueError as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
