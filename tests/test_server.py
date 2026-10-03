"""Tests for TCP server protocol and command processing."""

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


if __name__ == "__main__":
    unittest.main()
