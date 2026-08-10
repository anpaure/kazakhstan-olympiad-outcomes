import unittest

from scripts.apply_exa_outcome_integrations import merge_rows


class ExaOutcomeIntegrationTest(unittest.TestCase):
    def test_updates_existing_rows_and_appends_new_people(self):
        base = [
            {"person_id": "kaz-1", "organization": "Old University"},
            {"person_id": "kaz-2", "organization": "Existing Company"},
        ]
        updates = [
            {"person_id": "kaz-1", "organization": "New Company"},
            {"person_id": "kaz-3", "organization": "Added Company"},
        ]

        merged, updated, appended = merge_rows(base, updates)

        self.assertEqual(updated, 1)
        self.assertEqual(appended, 1)
        self.assertEqual(
            [(row["person_id"], row["organization"]) for row in merged],
            [
                ("kaz-1", "New Company"),
                ("kaz-2", "Existing Company"),
                ("kaz-3", "Added Company"),
            ],
        )

    def test_rejects_duplicate_update_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            merge_rows(
                [],
                [
                    {"person_id": "kaz-1", "organization": "One"},
                    {"person_id": "kaz-1", "organization": "Two"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
