import unittest

from scripts.validate_research import manual_history_preserved, structured_alma_timeline_conflicts


class ManualHistoryPreservationTest(unittest.TestCase):
    def test_role_capitalization_does_not_hide_preserved_evidence(self):
        verified = {"organization": "MIT", "role": "PhD Candidate",
                    "career_evidence_url": "https://example.test/profile/"}
        history = {"organization": "Massachusetts Institute of Technology (MIT)",
                   "role": "PhD candidate", "evidence_url": "https://example.test/profile"}
        self.assertTrue(manual_history_preserved(verified, [history]))

    def test_different_claim_or_source_is_not_preserved_history(self):
        verified = {"organization": "MIT", "role": "PhD Candidate",
                    "career_evidence_url": "https://example.test/profile"}
        history = {"organization": "MIT", "role": "PhD candidate",
                   "evidence_url": "https://example.test/profile"}
        for field, value in [("organization", "Harvard University"),
                             ("role", "Research Scientist"),
                             ("evidence_url", "https://example.test/other")]:
            with self.subTest(field=field):
                self.assertFalse(manual_history_preserved(verified, [{**history, field: value}]))


def alma(
    organization,
    start_year,
    end_year,
    evidence_kind,
    evidence_url="https://example.test/profile",
    selected="true",
):
    return {
        "person_id": "kaz-test",
        "organization": organization,
        "role": "Degree",
        "affiliation_type": "education",
        "start_year": start_year,
        "end_year": end_year,
        "selected_as_alma_mater": selected,
        "evidence_kind": evidence_kind,
        "evidence_url": evidence_url,
    }


class StructuredAlmaTimelineConflictTest(unittest.TestCase):
    def test_rejects_overlapping_different_institutions(self):
        rows = [
            alma(
                "Northwest A&F University",
                "2024",
                "2026",
                "accepted_orcid",
                "https://orcid.org/0000-0000-0000-0001",
            ),
            alma("EPFL", "2024", "2029", "accepted_linkedin_profile"),
        ]

        self.assertEqual(
            structured_alma_timeline_conflicts(rows),
            [
                (
                    "kaz-test",
                    "https://orcid.org/0000-0000-0000-0001",
                    "Northwest A&F University",
                    "EPFL",
                )
            ],
        )

    def test_allows_canonical_alias_of_same_institution(self):
        rows = [
            alma(
                "Massachusetts Institute of Technology",
                "2018",
                "2022",
                "accepted_orcid",
            ),
            alma(
                "Massachusetts Institute of Technology (MIT)",
                "2018",
                "2022",
                "accepted_linkedin_profile",
            ),
        ]

        self.assertEqual(structured_alma_timeline_conflicts(rows), [])

    def test_allows_trusted_corroboration_of_structured_institution(self):
        rows = [
            alma("University A", "2024", "2026", "accepted_orcid"),
            alma("University A", "2024", "2026", "manual_review"),
            alma("University B", "2024", "2026", "accepted_linkedin_profile"),
        ]

        self.assertEqual(structured_alma_timeline_conflicts(rows), [])


if __name__ == "__main__":
    unittest.main()
