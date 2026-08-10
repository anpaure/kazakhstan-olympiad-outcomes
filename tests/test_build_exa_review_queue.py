import unittest

from scripts.build_exa_review_queue import (
    build_queue,
    canonical_url,
    classify_candidate,
    classify_outcome_alignment,
)


class ExaReviewQueueTest(unittest.TestCase):
    def test_expected_olympiad_year_and_current_role_form_explicit_bridge(self):
        row = classify_candidate(
            {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IMO",
                "years": "2022",
                "confidence": "unmatched",
            },
            {"request_id": "req-1", "query": "query", "cost_usd": 0.007},
            {
                "rank": 1,
                "title": "Exact Person",
                "url": "https://linkedin.com/in/exact-person",
                "result_kind": "profile",
                "exact_name_in_title": True,
                "highlights": [
                    "Software Engineer - Example (Current). IMO 2022 bronze medal."
                ],
            },
        )
        self.assertEqual(row["review_tier"], "explicit_bridge")
        self.assertTrue(row["expected_olympiad_bridge"])
        self.assertTrue(row["year_overlap"])
        self.assertTrue(row["award_language"])
        self.assertTrue(row["current_affiliation_language"])

    def test_explicit_bridge_extracts_changed_current_outcome(self):
        row = classify_candidate(
            {
                "person_id": "kaz-1",
                "name": "Altair Ashurov",
                "olympiads": "IOI",
                "years": "2021",
                "confidence": "confirmed",
                "organization": "Nazarbayev University",
                "role": "Student",
            },
            {"request_id": "req-1", "query": "query", "cost_usd": 0.007},
            {
                "rank": 1,
                "title": "Altair Ashurov",
                "url": "https://linkedin.com/in/fracta1l",
                "result_kind": "profile",
                "exact_name_in_title": True,
                "highlights": [
                    "### Quantitative Research Intern - "
                    "[Squarepoint](https://linkedin.com/company/squarepoint-capital) "
                    "(Current) ... International Olympiad in Informatics 2021 Bronze Medal"
                ],
            },
        )
        self.assertEqual(row["candidate_current_organization"], "Squarepoint")
        self.assertEqual(row["candidate_current_role"], "Quantitative Research Intern")
        self.assertEqual(row["outcome_alignment"], "organization_change")

    def test_other_olympiad_does_not_count_as_expected_bridge(self):
        row = classify_candidate(
            {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IBO",
                "years": "2022",
                "confidence": "unmatched",
            },
            {"request_id": "req-1", "query": "query", "cost_usd": 0.007},
            {
                "rank": 1,
                "title": "Exact Person",
                "url": "https://linkedin.com/in/exact-person",
                "result_kind": "profile",
                "exact_name_in_title": True,
                "highlights": ["IMO 2022 bronze medal"],
            },
        )
        self.assertEqual(row["review_tier"], "exact_name_only")
        self.assertFalse(row["expected_olympiad_bridge"])

    def test_link_target_does_not_create_ibo_bridge(self):
        row = classify_candidate(
            {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IBO",
                "years": "2012",
                "confidence": "unmatched",
            },
            {"request_id": "req-1", "query": "query", "cost_usd": 0.007},
            {
                "rank": 1,
                "title": "Exact Person",
                "url": "https://linkedin.com/in/exact-person",
                "result_kind": "profile",
                "exact_name_in_title": True,
                "highlights": [
                    "Economics at [International Baccalaureate](https://linkedin.com/school/ibo)"
                ],
            },
        )
        self.assertEqual(row["review_tier"], "exact_name_only")
        self.assertFalse(row["expected_olympiad_bridge"])

    def test_queue_excludes_non_exact_results_and_prioritizes_unmatched(self):
        people = {
            "kaz-confirmed": {
                "person_id": "kaz-confirmed",
                "name": "Confirmed Person",
                "olympiads": "IMO",
                "years": "2020",
                "confidence": "confirmed",
            },
            "kaz-unmatched": {
                "person_id": "kaz-unmatched",
                "name": "Unmatched Person",
                "olympiads": "IMO",
                "years": "2020",
                "confidence": "unmatched",
            },
        }
        searches = []
        for person_id, name in [
            ("kaz-confirmed", "Confirmed Person"),
            ("kaz-unmatched", "Unmatched Person"),
        ]:
            searches.append(
                {
                    "person_id": person_id,
                    "request_id": f"req-{person_id}",
                    "results": [
                        {
                            "rank": 1,
                            "title": name,
                            "url": f"https://linkedin.com/in/{person_id}",
                            "result_kind": "profile",
                            "exact_name_in_title": True,
                            "highlights": ["IMO 2020 bronze medal (Current)"],
                        },
                        {
                            "rank": 2,
                            "title": "Different Person",
                            "url": "https://linkedin.com/in/different",
                            "result_kind": "profile",
                            "exact_name_in_title": False,
                            "highlights": ["IMO 2020 bronze medal"],
                        },
                    ],
                }
            )

        queue = build_queue(people, searches)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["person_id"], "kaz-unmatched")

    def test_queue_labels_selected_and_rejected_linkedin_variants(self):
        people = {
            "kaz-1": {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IMO",
                "years": "2020",
                "confidence": "confirmed",
                "linkedin_url": "https://kz.linkedin.com/in/accepted-person/",
            }
        }
        searches = [
            {
                "person_id": "kaz-1",
                "results": [
                    {
                        "rank": 1,
                        "title": "Exact Person",
                        "url": "https://linkedin.com/in/accepted-person",
                        "result_kind": "profile",
                        "exact_name_in_title": True,
                        "highlights": [],
                    },
                    {
                        "rank": 2,
                        "title": "Exact Person",
                        "url": "https://www.linkedin.com/in/rejected-person/",
                        "result_kind": "profile",
                        "exact_name_in_title": True,
                        "highlights": [],
                    },
                ],
            }
        ]
        rejections = {("kaz-1", canonical_url("https://linkedin.com/in/rejected-person"))}
        queue = build_queue(people, searches, rejections)
        statuses = {row["candidate_url"]: row["review_status"] for row in queue}
        self.assertEqual(statuses["https://linkedin.com/in/accepted-person"], "selected")
        self.assertEqual(statuses["https://www.linkedin.com/in/rejected-person/"], "rejected")

    def test_canonical_url_strips_linkedin_locale_suffix(self):
        expected = "linkedin.com/in/accepted-person"
        self.assertEqual(
            canonical_url("https://pl.linkedin.com/in/accepted-person/en"), expected
        )
        self.assertEqual(
            canonical_url("https://www.linkedin.com/in/accepted-person/ru/"), expected
        )

    def test_parent_and_department_organizations_align(self):
        self.assertEqual(
            classify_outcome_alignment(
                "AWS Center for Quantum Computing at Amazon",
                "Amazon Web Services (AWS)",
            ),
            "organization_match",
        )
        self.assertEqual(
            classify_outcome_alignment(
                "Karlsruhe Institute of Technology",
                "wbk - Institute of Production Science",
            ),
            "organization_match",
        )

    def test_manual_outcome_decision_resolves_a_selected_conflict(self):
        people = {
            "kaz-1": {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IMO",
                "years": "2020",
                "confidence": "confirmed",
                "organization": "Newer Company",
                "linkedin_url": "https://linkedin.com/in/exact-person",
            }
        }
        searches = [
            {
                "person_id": "kaz-1",
                "results": [
                    {
                        "rank": 1,
                        "title": "Exact Person",
                        "url": "https://linkedin.com/in/exact-person",
                        "result_kind": "profile",
                        "exact_name_in_title": True,
                        "highlights": [
                            "### Student - [Old University](https://example.test) "
                            "(Current) IMO 2020 bronze medal"
                        ],
                    }
                ],
            }
        ]
        decisions = {
            ("kaz-1", "linkedin.com/in/exact-person"): {
                "decision": "retain_published_newer_evidence",
                "reason": "A newer dated source establishes the move.",
                "review_evidence_url": "https://example.test/newer",
            }
        }

        [row] = build_queue(people, searches, outcome_decisions=decisions)

        self.assertEqual(row["review_status"], "selected")
        self.assertEqual(
            row["outcome_review_status"], "retain_published_newer_evidence"
        )

    def test_identity_decision_marks_secondary_profile_supporting(self):
        people = {
            "kaz-1": {
                "person_id": "kaz-1",
                "name": "Exact Person",
                "olympiads": "IMO",
                "years": "2020",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/primary",
            }
        }
        searches = [
            {
                "person_id": "kaz-1",
                "results": [
                    {
                        "rank": 1,
                        "title": "Exact Person",
                        "url": "https://linkedin.com/in/secondary",
                        "result_kind": "profile",
                        "exact_name_in_title": True,
                        "highlights": ["Same university timeline"],
                    }
                ],
            }
        ]
        decisions = {
            ("kaz-1", "linkedin.com/in/secondary"): {
                "decision": "supporting",
                "reason": "Duplicate old profile with the same education.",
                "review_evidence_url": "https://linkedin.com/in/primary",
            }
        }

        [row] = build_queue(people, searches, identity_decisions=decisions)

        self.assertEqual(row["review_status"], "supporting")
        self.assertEqual(row["outcome_review_status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
