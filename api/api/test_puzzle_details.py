import unittest
import logging

from api.helper_tests import PuzzleTestCase

# import api.puzzle_details


class TestInternalPuzzleDetailsView(PuzzleTestCase):
    ""

    def setUp(self):
        super().setUp()
        with self.app.app_context():
            cur = self.db.cursor()
            self.puzzle_data = self.fabricate_fake_puzzle()
            self.puzzle = self.puzzle_data.get("id")
            self.puzzle_id = self.puzzle_data.get("puzzle_id")

    def tearDown(self):
        super().tearDown()

    def test_puzzle_exists(self):
        "Should respond with 400 HTTP error if puzzle does not exist"
        with self.app.app_context():
            with self.app.test_client() as c:
                rv = c.patch(
                    "/internal/puzzle/{puzzle_id}/details/".format(puzzle_id="abc")
                )
                self.assertEqual(400, rv.status_code)
                self.assertEqual({"msg": "No puzzle found"}, rv.json)

    def test_missing_payload(self):
        "Should respond with 400 HTTP error if no payload was sent with PATCH"
        with self.app.app_context():
            with self.app.test_client() as c:
                rv = c.patch(
                    "/internal/puzzle/{puzzle_id}/details/".format(
                        puzzle_id=self.puzzle_id
                    )
                )
                self.assertEqual(400, rv.status_code)
                self.assertEqual({"msg": "No JSON data sent"}, rv.json)

    def test_acceptable_fields_in_payload(self):
        "Should respond with 400 HTTP error if missing fields in payload was sent with PATCH"
        with self.app.app_context():
            with self.app.test_client() as c:
                rv = c.patch(
                    "/internal/puzzle/{puzzle_id}/details/".format(
                        puzzle_id=self.puzzle_id
                    ),
                    json={"bogus": "value", "pieces": 1234},
                )
                self.assertEqual(400, rv.status_code)
                self.assertEqual({"msg": "Missing fields in JSON data sent"}, rv.json)

    def test_updates_puzzle_details_with_values(self):
        "Should update the puzzle details with the values that were sent"
        with self.app.app_context():
            with self.app.test_client() as c:
                rv = c.patch(
                    "/internal/puzzle/{puzzle_id}/details/".format(
                        puzzle_id=self.puzzle_id
                    ),
                    json={"status": 1, "queue": 1, "pieces": 1234},
                )
                self.assertEqual(200, rv.status_code)
                self.assertEqual({"rowcount": 1}, rv.json)


if __name__ == "__main__":
    unittest.main()
