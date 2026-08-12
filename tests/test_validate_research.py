import unittest

from scripts.validate_research import structured_alma_timeline_conflicts


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
