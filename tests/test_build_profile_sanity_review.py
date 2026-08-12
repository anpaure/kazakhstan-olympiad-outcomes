import unittest

from scripts.build_profile_sanity_review import (
    build_sample_rows,
    build_reconciliation,
    review_fingerprint,
    select_sample,
)


class ProfileSanityReviewTests(unittest.TestCase):
    def test_sample_is_stratified_and_deterministic(self):
        people = []
        for confidence in ("probable", "confirmed"):
            for era, year in (("older", "2000"), ("newer", "2010")):
                for index in range(3):
                    people.append(
                        {
                            "person_id": f"{confidence}-{era}-{index}",
                            "name": f"{confidence} {era} {index}",
                            "confidence": confidence,
                            "first_year": year,
                        }
                    )

        first = select_sample(people, seed="fixed", cutoff_year=2005, per_stratum=2)
        second = select_sample(people, seed="fixed", cutoff_year=2005, per_stratum=2)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        self.assertEqual(
            {row["stratum"] for row in first},
            {
                "probable_older",
                "probable_newer",
                "confirmed_older",
                "confirmed_newer",
            },
        )

    def test_reconciliation_requires_explicit_review_for_mismatch(self):
        people = [
            {
                "person_id": "kaz-test",
                "name": "Test Person",
                "organization": "New Employer",
                "role": "Engineer",
            }
        ]
        profiles = [
            {
                "person_id": "kaz-test",
                "name": "Test Person",
                "linkedin_url": "https://linkedin.com/in/test",
                "status": "success",
                "text": (
                    "### Engineer - [Old Employer](https://linkedin.com/company/old) "
                    "(Current) 2024 - Present"
                ),
            }
        ]

        unresolved = build_reconciliation(people, profiles, [], [])
        self.assertEqual(
            unresolved[0]["alignment_status"], "unreconciled_organization"
        )

        reviewed = build_reconciliation(
            people,
            profiles,
            [],
            [
                {
                    "person_id": "kaz-test",
                    "candidate_url": "https://linkedin.com/in/test",
                    "decision": "retain_newer_source",
                    "reason": "A newer official source supersedes the profile.",
                    "review_evidence_url": "https://example.com/current",
                }
            ],
        )
        self.assertEqual(
            reviewed[0]["alignment_status"], "reconciled_source_precedence"
        )

    def test_degree_through_current_year_matches_student_destination(self):
        people = [
            {
                "person_id": "kaz-student",
                "name": "Current Student",
                "organization": "Example University",
                "role": "Undergraduate Student",
                "affiliation_type": "education",
            }
        ]
        profiles = [
            {
                "person_id": "kaz-student",
                "name": "Current Student",
                "linkedin_url": "https://linkedin.com/in/current-student",
                "status": "success",
                "text": (
                    "## Education\n\n### Bachelor's degree, Mathematics at "
                    "[Example University](https://linkedin.com/school/example)\n\n"
                    "2022 - 2026 (4 years)"
                ),
            }
        ]

        rows = build_reconciliation(people, profiles, [], [])

        self.assertEqual(rows[0]["organization_alignment"], "matched")
        self.assertEqual(rows[0]["role_alignment"], "matched")
        self.assertEqual(rows[0]["alignment_status"], "matched_current_profile")

    def test_retrieval_error_uses_separate_outcome_evidence(self):
        people = [
            {
                "person_id": "kaz-error",
                "name": "Unavailable Profile",
                "organization": "Verified Employer",
                "role": "Engineer",
            }
        ]
        profiles = [
            {
                "person_id": "kaz-error",
                "name": "Unavailable Profile",
                "linkedin_url": "https://linkedin.com/in/unavailable",
                "status": "error",
                "text": "",
            }
        ]
        evidence = [
            {
                "person_id": "kaz-error",
                "claim_type": "career_outcome",
                "review_status": "accepted",
                "supports_final_outcome": "True",
                "source_url": "https://example.com/verified-role",
            }
        ]

        rows = build_reconciliation(people, profiles, [], [], evidence)

        self.assertEqual(rows[0]["alignment_status"], "profile_retrieval_unavailable")
        self.assertEqual(rows[0]["review_decision"], "verified_fallback_source")
        self.assertEqual(
            rows[0]["review_reference_url"], "https://example.com/verified-role"
        )

    def test_bounded_profile_destination_requires_a_review(self):
        people = [
            {
                "person_id": "kaz-stale",
                "name": "Stale Role",
                "organization": "Former Employer",
                "role": "Director",
                "affiliation_type": "employment",
            }
        ]
        profiles = [
            {
                "person_id": "kaz-stale",
                "name": "Stale Role",
                "linkedin_url": "https://linkedin.com/in/stale",
                "status": "success",
                "text": (
                    "## Experience\n\n### Director - Former Employer\n\n"
                    "2023 - 2025"
                ),
            }
        ]

        unresolved = build_reconciliation(people, profiles, [], [])
        self.assertEqual(
            unresolved[0]["alignment_status"],
            "unreconciled_bounded_profile_destination",
        )

        people[0]["start_year"] = "2023"
        people[0]["end_year"] = "2025"
        matched = build_reconciliation(people, profiles, [], [])
        self.assertEqual(
            matched[0]["alignment_status"], "matched_historical_profile"
        )

        people[0]["start_year"] = ""
        people[0]["end_year"] = ""

        reviewed = build_reconciliation(
            people,
            profiles,
            [
                {
                    "person_id": "kaz-stale",
                    "evidence_url": "https://example.com/new-role",
                    "review_reason": "A newer source establishes the replacement role.",
                }
            ],
            [],
        )
        self.assertEqual(
            reviewed[0]["alignment_status"], "reconciled_destination_review"
        )

    def test_sample_review_requires_matching_fingerprint(self):
        selection = [
            {
                "person": {"person_id": "kaz-review"},
                "stratum": "confirmed_newer",
                "sample_rank": 1,
                "sample_hash": "abc123",
            }
        ]
        audit_person = {
            "person_id": "kaz-review",
            "name": "Review Person",
            "olympiads": "IMO",
            "years": "2020",
            "outcome_status": "career",
            "organization": "Example Co",
            "role": "Engineer",
            "destination_status": "latest_employment",
            "outcome_country_name": "United States",
            "outcome_location_label": "United States",
            "alma_mater": "Example University",
            "primary_profile_url": "https://example.com/profile",
            "linkedin_url": "",
            "outcome_country_source_url": "https://example.com/location",
        }
        evidence = [
            {
                "person_id": "kaz-review",
                "claim_type": "olympiad_participation",
                "source_url": "https://example.com/imo",
                "review_status": "accepted",
                "supports_final_outcome": "False",
            },
            {
                "person_id": "kaz-review",
                "claim_type": "career_outcome",
                "source_url": "https://example.com/job",
                "review_status": "accepted",
                "supports_final_outcome": "True",
            },
        ]
        affiliations = [
            {
                "person_id": "kaz-review",
                "selected_as_alma_mater": "true",
                "evidence_url": "https://example.com/degree",
            }
        ]

        pending = build_sample_rows(
            selection, [audit_person], evidence, affiliations, [], [], "seed"
        )
        self.assertEqual(pending[0]["manual_review_status"], "pending")
        self.assertEqual(
            pending[0]["review_fingerprint"], review_fingerprint(pending[0])
        )

        decision = {
            ("seed", "kaz-review"): {
                "review_fingerprint": pending[0]["review_fingerprint"],
                "review_status": "pass",
                "review_depth": "deep",
                "reviewed_at": "2026-08-12",
                "review_note": "Source chain reviewed.",
            }
        }
        reviewed = build_sample_rows(
            selection,
            [audit_person],
            evidence,
            affiliations,
            [],
            [],
            "seed",
            decision,
        )
        self.assertEqual(reviewed[0]["manual_review_status"], "pass")
        self.assertEqual(reviewed[0]["review_depth"], "deep")

        audit_person["role"] = "Senior Engineer"
        changed = build_sample_rows(
            selection,
            [audit_person],
            evidence,
            affiliations,
            [],
            [],
            "seed",
            decision,
        )
        self.assertEqual(changed[0]["manual_review_status"], "pending")
        self.assertIn("stale", changed[0]["review_note"])


if __name__ == "__main__":
    unittest.main()
