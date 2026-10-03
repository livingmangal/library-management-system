"""Unit tests for the Library data access layer and CAT-2 Collaborative Lending."""

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

    # ---------- CAT-2 Collaborative Lending Unit Tests ----------
    def test_collab_checkout_success(self):
        b_id = self.lib.add_book("Python Programming", "John Zelle", "9781590282755", copies=1)
        s1 = self.lib.add_member("Student One (Slot A1)", "s1@example.com")
        s2 = self.lib.add_member("Student Two (Slot C1)", "s2@example.com")

        res = self.lib.collab_checkout(
            book_id=b_id,
            subject_code="CSE2004",
            member1_id=s1,
            slot1="A1",
            member2_id=s2,
            slot2="C1"
        )
        self.assertEqual(res["subject_code"], "CSE2004")
        self.assertEqual(res["phase1_member"]["id"], s1)
        self.assertEqual(res["phase2_member"]["id"], s2)
        self.assertEqual(res["status"], "ACTIVE_PHASE_1")

        # Book availability should now be 0
        book = self.lib.search_books("9781590282755")[0]
        self.assertEqual(book["available"], 0)

        # Active collaborative loans check
        active = self.lib.active_collab_loans()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["current_holder_name"], "Student One (Slot A1)")

    def test_collab_checkout_same_slot_rejected(self):
        b_id = self.lib.add_book("Discrete Math", "Rosen", "9780073383095", copies=1)
        s1 = self.lib.add_member("Alice", "alice_s@example.com")
        s2 = self.lib.add_member("Bob", "bob_s@example.com")

        # Both enrolled in Slot A1 -> exam is on same day, must reject!
        with self.assertRaises(ValueError) as ctx:
            self.lib.collab_checkout(b_id, "MAT2002", s1, "A1", s2, "A1")
        self.assertIn("Both students are in Slot A1", str(ctx.exception))

    def test_collab_checkout_auto_chronological_ordering(self):
        b_id = self.lib.add_book("Theory of Computation", "Sipser", "9781133187790", copies=1)
        s_late = self.lib.add_member("Late Student (Slot D1)", "late@example.com")
        s_early = self.lib.add_member("Early Student (Slot A1)", "early@example.com")

        # Pass late student first, early student second
        res = self.lib.collab_checkout(b_id, "CSE3011", s_late, "D1", s_early, "A1")

        # System should automatically assign Phase 1 to early student (Slot A1)
        self.assertEqual(res["phase1_member"]["id"], s_early)
        self.assertEqual(res["phase1_member"]["slot"], "A1")
        self.assertEqual(res["phase2_member"]["id"], s_late)
        self.assertEqual(res["phase2_member"]["slot"], "D1")

    def test_collab_handover_and_return_lifecycle(self):
        b_id = self.lib.add_book("C++ Primer", "Lippman", "9780321714114", copies=1)
        s1 = self.lib.add_member("C++ Student 1", "cpp1@example.com")
        s2 = self.lib.add_member("C++ Student 2", "cpp2@example.com")

        res = self.lib.collab_checkout(b_id, "ECE2002", s1, "B1", s2, "D1")
        collab_id = res["collab_id"]

        # Confirm handover
        h_res = self.lib.collab_handover(collab_id)
        self.assertEqual(h_res["status"], "ACTIVE_PHASE_2")
        self.assertEqual(h_res["current_holder_id"], s2)

        # Return to library
        fine = self.lib.collab_return(collab_id)
        self.assertEqual(fine, 0.0)

        # Book availability restored to 1
        book = self.lib.search_books("9780321714114")[0]
        self.assertEqual(book["available"], 1)

        # No active collaborative loans remaining
        self.assertEqual(len(self.lib.active_collab_loans()), 0)

    def test_collab_request_and_matching(self):
        b_id = self.lib.add_book("Management", "Koontz", "9780070356078", copies=1)
        s1 = self.lib.add_member("Requester", "req@example.com")
        s2 = self.lib.add_member("Joiner", "join@example.com")

        # S1 posts open request
        req_id = self.lib.create_collab_request(b_id, "MGT2003", s1, "E1")
        self.assertIsInstance(req_id, int)

        # List requests
        reqs = self.lib.list_collab_requests("MGT2003")
        self.assertEqual(len(reqs), 1)

        # S2 accepts request with different slot
        loan = self.lib.accept_collab_request(req_id, s2, "A1")
        self.assertEqual(loan["subject_code"], "MGT2003")

        # Open request should no longer appear in open list
        self.assertEqual(len(self.lib.list_collab_requests("MGT2003")), 0)


if __name__ == "__main__":
    unittest.main()
