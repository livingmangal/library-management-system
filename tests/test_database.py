"""Unit tests for the Library data access layer (core/database.py)."""

import sqlite3
import unittest
from datetime import date, timedelta

from core.database import Library


class TestLibraryDatabase(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite database for isolated, fast tests
        self.lib = Library(path=":memory:")

    def tearDown(self):
        self.lib.close()

    def test_add_and_search_book(self):
        book_id = self.lib.add_book("Test Title", "Author Person", "1234567890", copies=3)
        self.assertIsInstance(book_id, int)

        results = self.lib.search_books("Test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Title")
        self.assertEqual(results[0]["copies"], 3)
        self.assertEqual(results[0]["available"], 3)

    def test_duplicate_isbn_fails(self):
        self.lib.add_book("Book One", "Author", "ISBN-111", 1)
        with self.assertRaises(ValueError) as ctx:
            self.lib.add_book("Book Two", "Other", "ISBN-111", 1)
        self.assertIn("already exists", str(ctx.exception))

    def test_add_and_list_members(self):
        m_id = self.lib.add_member("Alice Smith", "alice@example.com")
        self.assertIsInstance(m_id, int)

        members = self.lib.list_members()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["name"], "Alice Smith")

        # Duplicate email should fail
        with self.assertRaises(ValueError):
            self.lib.add_member("Alice Clone", "alice@example.com")

    def test_checkout_and_return_cycle(self):
        b_id = self.lib.add_book("Book", "Author", "ISBN-10", copies=1)
        m_id = self.lib.add_member("Bob", "bob@example.com")

        # Checkout
        due_date = self.lib.checkout(b_id, m_id)
        self.assertIsInstance(due_date, date)

        # Book availability should now be 0
        book = self.lib.search_books("ISBN-10")[0]
        self.assertEqual(book["available"], 0)

        # Second checkout should fail (no copies)
        m2_id = self.lib.add_member("Charlie", "charlie@example.com")
        with self.assertRaises(ValueError) as ctx:
            self.lib.checkout(b_id, m2_id)
        self.assertIn("No copies available", str(ctx.exception))

        # Return book
        fine = self.lib.return_book(b_id, m_id)
        self.assertEqual(fine, 0.0)

        # Availability restored to 1
        book = self.lib.search_books("ISBN-10")[0]
        self.assertEqual(book["available"], 1)

    def test_cannot_remove_borrowed_book(self):
        b_id = self.lib.add_book("Borrowed Book", "Author", "ISBN-BORROW", copies=1)
        m_id = self.lib.add_member("Dan", "dan@example.com")
        self.lib.checkout(b_id, m_id)

        with self.assertRaises(ValueError) as ctx:
            self.lib.remove_book(b_id)
        self.assertIn("currently on loan", str(ctx.exception))

    def test_overdue_fine_calculation(self):
        b_id = self.lib.add_book("Late Book", "Author", "ISBN-LATE", copies=1)
        m_id = self.lib.add_member("Eve", "eve@example.com")
        self.lib.checkout(b_id, m_id)

        # Manually backdate the loan in the test database
        past_due = (date.today() - timedelta(days=5)).isoformat()
        with self.lib.db:
            self.lib.db.execute("UPDATE loans SET due_on=? WHERE book_id=?", (past_due, b_id))

        # Check overdue loans
        overdue = self.lib.overdue_loans()
        self.assertEqual(len(overdue), 1)

        # Return and check fine (5 days * $0.50 = $2.50)
        fine = self.lib.return_book(b_id, m_id)
        self.assertEqual(fine, 2.50)


if __name__ == "__main__":
    unittest.main()
