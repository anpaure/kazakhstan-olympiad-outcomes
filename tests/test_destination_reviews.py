import csv
import tempfile
import unittest
from pathlib import Path

from scripts.destination_reviews import (
    DESTINATION_REVIEW_FIELDS,
    load_destination_reviews,
)


class DestinationReviewRegistryTest(unittest.TestCase):
    def write_rows(self, rows):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "destination_reviews.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DESTINATION_REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return temporary, path

    def test_loads_and_canonicalizes_reviewed_destination(self):
        temporary, path = self.write_rows(
            [
                {
                    "person_id": "kaz-test",
                    "name": "Test Person",
                    "organization": "Amazon Web Services (AWS)",
                    "role": "Software Engineer",
                    "affiliation_type": "employment",
                    "start_year": "2025",
                    "end_year": "",
                    "evidence_url": "https://example.test/profile",
                    "reviewed_at": "2026-08-10",
                    "review_reason": "Exact current title in the cited profile.",
                }
            ]
        )
        self.addCleanup(temporary.cleanup)

        [review] = load_destination_reviews(path)

        self.assertEqual(review["organization"], "Amazon")

    def test_rejects_duplicate_people(self):
        row = {
            "person_id": "kaz-test",
            "name": "Test Person",
            "organization": "Current Co",
            "role": "Engineer",
            "affiliation_type": "employment",
            "start_year": "2025",
            "end_year": "",
            "evidence_url": "https://example.test/profile",
            "reviewed_at": "2026-08-10",
            "review_reason": "Exact current title in the cited profile.",
        }
        temporary, path = self.write_rows([row, row])
        self.addCleanup(temporary.cleanup)

        with self.assertRaisesRegex(ValueError, "duplicate person ID"):
            load_destination_reviews(path)


if __name__ == "__main__":
    unittest.main()
