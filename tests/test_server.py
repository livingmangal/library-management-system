"""Tests for TCP server protocol and command processing including CAT-2 Collaborative Lending."""

import json
import unittest

from server.server import LibraryServer


class TestServerProtocol(unittest.TestCase):
    def setUp(self):
        # Create server instance with an isolated in-memory DB
        self.server = LibraryServer(host="127.0.0.1", port=0, db_path=":memory:")

    def tearDown(self):
        self.server.lib.close()

    def send_cmd(self, cmd, **args):
        line = json.dumps({"cmd": cmd, "args": args})
        return self.server.process(line)

    def test_ping(self):
        reply = self.send_cmd("ping")
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["data"], "pong")

    def test_add_and_search_book(self):
        reply = self.send_cmd(
            "add_book",
            title="Protocol Design",
            author="Network Expert",
            isbn="9781112223334",
            copies=2
        )
        self.assertTrue(reply["ok"])
        book_id = reply["data"]

        reply = self.send_cmd("search", term="Protocol")
        self.assertTrue(reply["ok"])
        self.assertEqual(len(reply["data"]), 1)
        self.assertEqual(reply["data"][0]["id"], book_id)

    def test_invalid_command(self):
        reply = self.server.process('{"cmd": "non_existent_command"}')
        self.assertFalse(reply["ok"])
        self.assertIn("error", reply)

    def test_malformed_json(self):
        reply = self.server.process("NOT_VALID_JSON{")
        self.assertFalse(reply["ok"])
        self.assertEqual(reply["error"], "Bad request.")

    def test_missing_required_args(self):
        reply = self.send_cmd("add_book", title="No Author or ISBN")
        self.assertFalse(reply["ok"])

    def test_cat2_metadata(self):
        reply = self.send_cmd("cat2_metadata")
        self.assertTrue(reply["ok"])
        self.assertIn("CSE2004", reply["data"]["subjects"])
        self.assertIn("A1", reply["data"]["slots"])

    def test_collab_checkout_protocol(self):
        # Seed members and book
        b_res = self.send_cmd("add_book", title="Python Exam Book", author="Author", isbn="9780001", copies=1)
        m1_res = self.send_cmd("add_member", name="Student A", email="sa@ex.com")
        m2_res = self.send_cmd("add_member", name="Student B", email="sb@ex.com")

        b_id, m1, m2 = b_res["data"], m1_res["data"], m2_res["data"]

        # Same slot should return ok: false
        same_slot_reply = self.send_cmd(
            "collab_checkout",
            book_id=b_id,
            subject_code="CSE2004",
            member1_id=m1,
            slot1="A1",
            member2_id=m2,
            slot2="A1"
        )
        self.assertFalse(same_slot_reply["ok"])
        self.assertIn("Slot A1", same_slot_reply["error"])

        # Different slots should succeed
        diff_slot_reply = self.send_cmd(
            "collab_checkout",
            book_id=b_id,
            subject_code="CSE2004",
            member1_id=m1,
            slot1="A1",
            member2_id=m2,
            slot2="C1"
        )
        self.assertTrue(diff_slot_reply["ok"])
        collab_id = diff_slot_reply["data"]["collab_id"]

        # Check active loans
        loans_reply = self.send_cmd("active_collab_loans")
        self.assertTrue(loans_reply["ok"])
        self.assertEqual(len(loans_reply["data"]), 1)

        # Handover
        handover_reply = self.send_cmd("collab_handover", collab_id=collab_id)
        self.assertTrue(handover_reply["ok"])
        self.assertEqual(handover_reply["data"]["status"], "ACTIVE_PHASE_2")

        # Return
        return_reply = self.send_cmd("collab_return", collab_id=collab_id)
        self.assertTrue(return_reply["ok"])


if __name__ == "__main__":
    unittest.main()
