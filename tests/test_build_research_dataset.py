import unittest

from scripts.build_research_dataset import (
    build_rows,
    normalize_destination,
    organization_category,
    role_category,
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

    def test_destination_review_supersedes_stale_manual_summary(self):
        people = [
            {
                "person_id": "kaz-test",
                "canonical_name": "Test Person",
                "aliases": "Test Person",
                "olympiads": "IMO",
                "years": "2010",
                "first_year": "2010",
                "last_year": "2010",
                "awards": "Silver",
                "research_scope": "career",
            }
        ]
        verified = [
            {
                "person_id": "kaz-test",
                "name": "Test Person",
                "organization": "Old Co",
                "role": "Founder",
                "affiliation_type": "employment",
                "start_year": "",
                "end_year": "",
                "olympiad_evidence_url": "https://example.test/olympiad",
                "career_evidence_url": "https://example.test/profile",
                "linkedin_url": "https://linkedin.com/in/test",
                "confidence": "confirmed",
                "verification_basis": "Previously reviewed summary.",
            }
        ]
        reviews = [
            {
                "person_id": "kaz-test",
                "name": "Test Person",
                "organization": "Current Co",
                "role": "Software Engineer",
                "affiliation_type": "employment",
                "start_year": "2025",
                "end_year": "",
                "evidence_url": "https://linkedin.com/in/test",
                "reviewed_at": "2026-08-10",
                "review_reason": "The cited profile gives the current title.",
            }
        ]

        [row] = build_rows(people, [], [], verified, [], reviews)

        self.assertEqual(row.organization, "Current Co")
        self.assertEqual(row.role, "Software Engineer")
        self.assertEqual(row.start_year, "2025")
        self.assertIn("Destination review", row.verification_basis)
        self.assertIn("https://linkedin.com/in/test", row.evidence_urls)


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
            "Dove Science Academy",
        ]

        for organization in organizations:
            with self.subTest(organization=organization):
                self.assertEqual(
                    organization_category(organization, "employment"), "Academia"
                )

    def test_principal_is_classified_as_leadership(self):
        self.assertEqual(
            role_category(
                "Principal, Chemistry Teacher and Olympiad Coach",
                "Bilim-Innovation Lyceum No. 1, Karaganda",
                "employment",
            ),
            "Leadership",
        )

    def test_quantitative_research_is_classified_as_finance(self):
        self.assertEqual(
            role_category(
                "Quantitative Research Analyst",
                "Qube Research & Technologies",
                "employment",
            ),
            "Economics & Finance",
        )


class DestinationNormalizationTest(unittest.TestCase):
    def test_destination_uses_canonical_organization_name(self):
        normalized = normalize_destination(
            "Amazon Web Services (AWS)", "Software Engineer", "employment", "2024", ""
        )

        self.assertEqual(normalized[0], "Amazon")
        self.assertEqual(normalized[3], "latest_employment")

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

    def test_parent_organization_keeps_aliases_searchable(self):
        row = {
            "person_id": "kaz-test",
            "name": "Test Person",
            "aliases": "Test Person",
            "olympiads": "IMO",
            "first_year": "2018",
            "last_year": "2018",
            "awards": "Silver",
            "confidence": "confirmed",
            "organization": "Amazon",
            "role": "Software Engineer",
            "organization_category": "Industry",
            "role_category": "Software & AI",
            "profile_url": "https://example.test/profile",
            "linkedin_url": "",
            "research_scope": "career",
        }

        compact = compact_person(row)

        self.assertEqual(compact["organization"], "Amazon")
        self.assertIn("Amazon Web Services (AWS)", compact["historyTerms"])

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
                "start_year": "2017",
                "evidence_url": "https://linkedin.com/in/test",
            },
            {
                "organization": "Graduate University",
                "role": "MSc",
                "selected_as_alma_mater": True,
                "start_year": "2021",
                "evidence_url": "https://example.test/graduate",
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

        self.assertEqual(
            compact["almaMater"],
            "Example University; Graduate University",
        )
        self.assertEqual(
            [item["organization"] for item in compact["almaMaters"]],
            ["Example University", "Graduate University"],
        )
        self.assertIn("Past Co", compact["historyTerms"])
        self.assertEqual(compact["country"], "Switzerland")
        self.assertTrue(compact["sources"])

    def test_compact_person_shows_only_one_olympiad_source(self):
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
            "profile_url": "https://www.imo-official.org/country_individual_r.aspx?code=KAZ",
            "linkedin_url": "",
            "evidence_urls": ";".join(
                [
                    "https://www.imo-official.org/results/contestant/12345/",
                    "https://www.imo-official.org/country_individual_r.aspx?code=KAZ",
                ]
            ),
            "research_scope": "career",
        }
        evidence = [
            {
                "claim_type": "olympiad_participation",
                "review_status": "accepted",
                "source_url": "https://www.imo-official.org/results/contestant/12345/",
            },
            {
                "claim_type": "identity_review",
                "review_status": "supporting",
                "source_url": "https://www.imo-official.org/country_individual_r.aspx?code=KAZ",
            },
        ]

        compact = compact_person(row, audit_evidence=evidence)
        olympiad_sources = [
            source for source in compact["sources"] if source["kind"] == "olympiad"
        ]

        self.assertEqual(len(olympiad_sources), 1)
        self.assertEqual(
            olympiad_sources[0]["url"],
            "https://www.imo-official.org/results/contestant/12345/",
        )
        self.assertFalse(
            any(source["kind"] == "evidence" for source in compact["sources"])
        )


if __name__ == "__main__":
    unittest.main()
