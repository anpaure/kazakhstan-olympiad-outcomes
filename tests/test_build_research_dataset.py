import unittest

from scripts.build_research_dataset import (
    build_rows,
    normalize_destination,
    organization_category,
)
from scripts.build_outcomes_visualization import compact_person


class ManualEvidenceConfidenceTest(unittest.TestCase):
    def test_manual_probable_confidence_is_preserved(self):
        people = [
            {
                "person_id": "kaz-test",
                "canonical_name": "Test Person",
                "aliases": "Test Person",
                "olympiads": "IBO",
                "years": "2003",
                "first_year": "2003",
                "last_year": "2003",
                "awards": "Bronze",
                "research_scope": "career",
            }
        ]
        verified = [
            {
                "person_id": "kaz-test",
                "name": "Person Test",
                "organization": "Example Research Lab",
                "role": "Principal Scientist",
                "affiliation_type": "employment",
                "start_year": "2022",
                "end_year": "",
                "olympiad_evidence_url": "https://example.test/olympiad",
                "career_evidence_url": "https://example.test/career",
                "linkedin_url": "",
                "confidence": "probable",
                "verification_basis": "Exact-name timeline match without a primary current-role source",
            }
        ]

        [row] = build_rows(people, [], [], verified)

        self.assertEqual(row.confidence, "probable")
        self.assertEqual(row.identity_source, "verified")
        self.assertEqual(row.name, "Person Test")


class RejectedCandidateTest(unittest.TestCase):
    def test_rejected_profile_and_its_affiliation_do_not_leak(self):
        people = [
            {
                "person_id": "kaz-test",
                "canonical_name": "Test Person",
                "aliases": "Test Person",
                "olympiads": "IBO",
                "years": "2003",
                "first_year": "2003",
                "last_year": "2003",
                "awards": "Bronze",
                "research_scope": "career",
            }
        ]
        identities = [
            {
                "person_id": "kaz-test",
                "source": "orcid",
                "profile_url": "https://orcid.org/0000-0000-0000-0000",
                "evidence_url": "https://orcid.org/0000-0000-0000-0000",
                "confidence": "candidate",
                "score": "0.57",
                "organization": "Wrong University",
                "role": "Researcher",
                "outbound_urls": "",
                "evidence_text": "Exact name only",
            }
        ]
        affiliations = [
            {
                "person_id": "kaz-test",
                "source": "orcid",
                "evidence_url": "https://orcid.org/0000-0000-0000-0000",
                "confidence": "candidate",
                "organization": "Wrong University",
                "role": "Researcher",
                "affiliation_type": "employment",
                "start_year": "2020",
                "end_year": "",
                "country_code": "",
                "evidence_text": "Exact name only",
            }
        ]
        rejections = [
            {
                "person_id": "kaz-test",
                "evidence_url": "https://orcid.org/0000-0000-0000-0000/",
                "reason": "No country or Olympiad bridge",
                "review_evidence_url": "",
            }
        ]

        [row] = build_rows(people, identities, affiliations, [], rejections)

        self.assertEqual(row.confidence, "unmatched")
        self.assertEqual(row.organization, "")
        self.assertEqual(row.evidence_urls, "")


class OrganizationCategoryTest(unittest.TestCase):
    def test_school_employers_are_not_classified_as_industry(self):
        organizations = [
            "Bilim-Innovation Specialized Boarding Lyceum, North Kazakhstan",
            "Almaty KTL",
            "NIS Medeu (NIS PhM Almaty)",
            "Astana/Almaty Physics Battles Tournament",
        ]

        for organization in organizations:
            with self.subTest(organization=organization):
                self.assertEqual(
                    organization_category(organization, "employment"), "Academia"
                )


class DestinationNormalizationTest(unittest.TestCase):
    def test_completed_degree_is_history_not_destination(self):
        normalized = normalize_destination(
            "Example University", "BSc Graduate", "education", "2018", "2022"
        )

        self.assertEqual(normalized[0], "")
        self.assertEqual(normalized[3], "history_only")

    def test_active_phd_student_remains_a_destination(self):
        normalized = normalize_destination(
            "Example University", "PhD Student", "education", "2024", ""
        )

        self.assertEqual(normalized[0], "Example University")
        self.assertEqual(normalized[3], "current_education")

    def test_university_researcher_is_employment(self):
        normalized = normalize_destination(
            "Example University", "Senior Researcher", "education", "2024", ""
        )

        self.assertEqual(normalized[2], "employment")
        self.assertEqual(normalized[3], "latest_employment")

    def test_publication_authorship_is_not_a_job(self):
        normalized = normalize_destination(
            "Example University", "Research author", "education", "2025", "2025"
        )

        self.assertEqual(normalized[0], "")
        self.assertEqual(normalized[3], "history_only")

    def test_unscoped_academic_organization_is_not_a_destination(self):
        normalized = normalize_destination("MIT", "", "organization", "", "")

        self.assertEqual(normalized[0], "")
        self.assertEqual(normalized[3], "history_only")

    def test_university_abbreviations_are_not_classified_as_industry(self):
        for organization in ["MIT", "HKUST", "KAIST", "UNIST"]:
            with self.subTest(organization=organization):
                self.assertEqual(
                    organization_category(organization, "organization"), "Academia"
                )


class VisualizationOrganizationAliasTest(unittest.TestCase):
    def test_unist_long_name_uses_one_display_label(self):
        row = {
            "person_id": "kaz-test",
            "name": "Test Person",
            "aliases": "Test Person;Person Test",
            "olympiads": "IBO",
            "first_year": "2018",
            "last_year": "2019",
            "awards": "Bronze;Silver",
            "confidence": "confirmed",
            "organization": "Ulsan National Institute of Science and Technology",
            "role": "PhD Student",
            "organization_category": "Education",
            "role_category": "Student",
            "profile_url": "https://example.test/profile",
            "linkedin_url": "",
            "research_scope": "career",
        }

        compact = compact_person(row)

        self.assertEqual(compact["organization"], "UNIST")
        self.assertEqual(compact["aliases"], ["Test Person", "Person Test"])
        self.assertEqual(compact["lastYear"], 2019)
        self.assertEqual(compact["awards"], ["Bronze", "Silver"])

    def test_compact_person_exposes_alma_mater_history_and_country(self):
        row = {
            "person_id": "kaz-test",
            "name": "Test Person",
            "aliases": "Test Person",
            "olympiads": "IMO",
            "first_year": "2018",
            "last_year": "2018",
            "awards": "Silver",
            "confidence": "confirmed",
            "organization": "Current Co",
            "role": "Engineer",
            "organization_category": "Industry",
            "role_category": "Engineering",
            "destination_status": "latest_employment",
            "profile_url": "https://example.test/career",
            "linkedin_url": "https://linkedin.com/in/test",
            "evidence_urls": "https://imo-official.org/test",
            "research_scope": "career",
        }
        affiliations = [
            {
                "organization": "Example University",
                "role": "BSc",
                "selected_as_alma_mater": True,
                "evidence_url": "https://linkedin.com/in/test",
            },
            {
                "organization": "Past Co",
                "role": "Analyst",
                "selected_as_alma_mater": False,
                "evidence_url": "https://linkedin.com/in/test",
            },
        ]
        location = {
            "country_code": "CH",
            "country_name": "Switzerland",
            "location_label": "Zurich, Switzerland",
            "confidence": "probable",
            "evidence_url": "https://linkedin.com/in/test",
        }

        compact = compact_person(row, location, affiliations)

        self.assertEqual(compact["almaMater"], "Example University")
        self.assertIn("Past Co", compact["historyTerms"])
        self.assertEqual(compact["country"], "Switzerland")
        self.assertTrue(compact["sources"])


if __name__ == "__main__":
    unittest.main()
