import json
import tempfile
import unittest
from pathlib import Path

from scripts.search_linkedin_with_exa import (
    build_query,
    exact_name_in_title,
    flat_rows,
    linkedin_result_kind,
    select_people,
    should_search,
    write_outputs,
)


class ExaLinkedInAuditTest(unittest.TestCase):
    def test_build_query_keeps_identity_context(self):
        query = build_query(
            {
                "name": "Nurtas Shyntas",
                "olympiads": "IMO",
                "years": "2019;2020",
            }
        )
        self.assertIn('"Nurtas Shyntas"', query)
        self.assertIn("Kazakhstan IMO Olympiad 2019;2020", query)

    def test_linkedin_profile_classification_accepts_country_subdomains(self):
        self.assertEqual(
            linkedin_result_kind("https://kz.linkedin.com/in/example-person"),
            "profile",
        )
        self.assertEqual(
            linkedin_result_kind("https://www.linkedin.com/posts/example"),
            "post",
        )
        self.assertEqual(linkedin_result_kind("https://example.com/in/person"), "non_linkedin")

    def test_explicit_person_selection_ignores_default_confidence_filter(self):
        people = [
            {
                "person_id": "kaz-confirmed",
                "name": "Exact Person",
                "confidence": "confirmed",
                "research_scope": "career",
                "first_year": "2010",
            },
            {
                "person_id": "kaz-unmatched",
                "name": "Other Person",
                "confidence": "unmatched",
                "research_scope": "career",
                "first_year": "2011",
            },
        ]
        selected = select_people(people, person_ids={"kaz-confirmed"})
        self.assertEqual([row["person_id"] for row in selected], ["kaz-confirmed"])

    def test_all_people_selection_ignores_default_filters(self):
        people = [
            {
                "person_id": "kaz-confirmed",
                "name": "Confirmed Person",
                "confidence": "confirmed",
                "research_scope": "historical",
                "first_year": "2000",
            },
            {
                "person_id": "kaz-unmatched",
                "name": "Unmatched Person",
                "confidence": "unmatched",
                "research_scope": "career",
                "first_year": "2001",
            },
        ]
        selected = select_people(people, include_all=True)
        self.assertEqual(
            [row["person_id"] for row in selected],
            ["kaz-confirmed", "kaz-unmatched"],
        )

    def test_resume_skips_completed_searches_and_can_retry_errors(self):
        self.assertFalse(should_search({"status": "ok"}))
        self.assertFalse(should_search({"status": "error"}))
        self.assertTrue(should_search({"status": "error"}, retry_errors=True))
        self.assertTrue(should_search({"status": "ok"}, refresh=True))
        self.assertTrue(should_search(None))

    def test_json_output_records_coverage(self):
        searches = [
            {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "status": "ok",
                "cost_usd": 0.007,
                "results": [],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "audit.json"
            csv_path = Path(directory) / "audit.csv"
            write_outputs(searches, json_path, csv_path, Path("input.csv"), 2)
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["input_people_count"], 2)
        self.assertEqual(payload["searched_people_count"], 1)
        self.assertEqual(payload["successful_search_count"], 1)
        self.assertEqual(payload["error_search_count"], 0)
        self.assertEqual(payload["coverage_percent"], 50.0)

    def test_flat_rows_preserve_request_and_source_evidence(self):
        rows = flat_rows(
            [
                {
                    "person_id": "kaz-1",
                    "name": "Exact Person",
                    "olympiads": "IMO",
                    "years": "2019",
                    "prior_confidence": "unmatched",
                    "query": "query",
                    "status": "ok",
                    "error": "",
                    "request_id": "req-1",
                    "cost_usd": 0.007,
                    "results": [
                        {
                            "rank": 1,
                            "title": "Exact Person - Company",
                            "url": "https://linkedin.com/in/exact-person",
                            "result_kind": "profile",
                            "exact_name_in_title": True,
                            "published_date": "",
                            "author": "",
                            "highlights": ["IMO medal", "Company"],
                        }
                    ],
                }
            ]
        )
        self.assertEqual(rows[0]["request_id"], "req-1")
        self.assertEqual(rows[0]["url"], "https://linkedin.com/in/exact-person")
        self.assertEqual(rows[0]["highlights"], "IMO medal | Company")
        self.assertTrue(exact_name_in_title("Exact Person", rows[0]["title"]))


if __name__ == "__main__":
    unittest.main()
