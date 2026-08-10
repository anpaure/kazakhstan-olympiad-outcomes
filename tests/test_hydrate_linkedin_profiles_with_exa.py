import unittest

from scripts.hydrate_linkedin_profiles_with_exa import (
    EXA_SEARCH_URL,
    cached_profiles_from_search,
    csv_value,
    normalize_batch,
    profile_search_records,
    select_profiles,
)


class ExaProfileHydrationTest(unittest.TestCase):
    def test_csv_export_strips_line_end_whitespace(self):
        self.assertEqual(csv_value("first  \nsecond \n \nthird"), "first\nsecond\n\nthird")

    def test_selects_only_accepted_linkedin_profiles(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Accepted Person",
                "confidence": "confirmed",
                "linkedin_url": "https://www.linkedin.com/in/accepted",
            },
            {
                "person_id": "person-2",
                "name": "Unmatched Person",
                "confidence": "unmatched",
                "linkedin_url": "https://www.linkedin.com/in/unmatched",
            },
            {
                "person_id": "person-3",
                "name": "No Profile",
                "confidence": "confirmed",
                "linkedin_url": "",
            },
        ]

        selected = select_profiles(people)

        self.assertEqual([row["person_id"] for row in selected], ["person-1"])

    def test_normalizes_success_and_error_statuses(self):
        selected = [
            {
                "person_id": "person-1",
                "name": "Found Person",
                "linkedin_url": "https://www.linkedin.com/in/found/",
            },
            {
                "person_id": "person-2",
                "name": "Missing Person",
                "linkedin_url": "https://kz.linkedin.com/in/missing",
            },
        ]
        response = {
            "requestId": "request-1",
            "results": [
                {
                    "id": "https://linkedin.com/in/found",
                    "url": "https://linkedin.com/in/found",
                    "title": "Found Person",
                    "text": "## Education ### MIT",
                }
            ],
            "statuses": [
                {"id": selected[0]["linkedin_url"], "status": "success"},
                {
                    "id": selected[1]["linkedin_url"],
                    "status": "error",
                    "error": {"tag": "ENTITY_NOT_FOUND"},
                },
            ],
            "costDollars": {"total": 0.002},
        }

        profiles, request = normalize_batch(selected, response, "2026-08-10T00:00:00+00:00")

        self.assertEqual(profiles[0]["status"], "success")
        self.assertEqual(profiles[1]["status"], "error")
        self.assertIn("ENTITY_NOT_FOUND", profiles[1]["error"])
        self.assertEqual(request["cost_usd"], 0.002)

    def test_successful_profile_becomes_parser_input(self):
        profiles = [
            {
                "person_id": "person-1",
                "status": "success",
                "linkedin_url": "https://linkedin.com/in/example",
                "resolved_url": "",
                "title": "Example Person",
                "text": "## Education ### MIT",
            },
            {
                "person_id": "person-2",
                "status": "error",
                "linkedin_url": "https://linkedin.com/in/missing",
                "text": "",
            },
        ]

        records = profile_search_records(profiles)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["person_id"], "person-1")
        self.assertEqual(records[0]["results"][0]["highlights"], ["## Education ### MIT"])

    def test_cached_search_result_becomes_audited_profile(self):
        selected = [
            {
                "person_id": "person-1",
                "name": "Reversed Person",
                "linkedin_url": "https://www.linkedin.com/in/reversed-person/",
            }
        ]
        searches = [
            {
                "request_id": "search-1",
                "searched_at": "2026-08-10T00:00:00+00:00",
                "results": [
                    {
                        "title": "Reversed Person",
                        "url": "https://linkedin.com/in/reversed-person",
                        "highlights": ["## Education\n\n### Example University"],
                    }
                ],
            }
        ]

        profiles = cached_profiles_from_search(selected, searches)

        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["status"], "search_cache")
        self.assertEqual(profiles[0]["source_endpoint"], EXA_SEARCH_URL)
        self.assertEqual(len(profile_search_records(profiles)), 1)


if __name__ == "__main__":
    unittest.main()
