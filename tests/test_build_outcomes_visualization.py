import json
import re
import unittest
from pathlib import Path

from scripts.build_outcomes_visualization import compact_person, compact_sources


class CompactVisualizationDataTest(unittest.TestCase):
    def test_exposes_reviewed_sector_metadata(self):
        row = {
            "person_id": "person-1",
            "name": "Example Person",
            "aliases": "Example Person",
            "olympiads": "IMO",
            "first_year": 2010,
            "last_year": 2010,
            "awards": "Gold medal",
            "confidence": "confirmed",
            "organization": "Amazon Web Services",
            "role": "Engineer",
            "organization_category": "Industry",
            "role_category": "Engineering",
            "destination_status": "latest_employment",
            "profile_url": "https://example.com/profile",
            "linkedin_url": "",
            "research_scope": "career",
            "evidence_urls": "https://example.com/profile",
        }

        person = compact_person(row)

        self.assertEqual(person["organization"], "Amazon")
        self.assertEqual(person["organizationType"], "company")
        self.assertEqual(person["sector"], "Technology & Software")

    def test_exposes_source_explicit_concurrent_destination(self):
        row = {
            "person_id": "person-1",
            "name": "Example Person",
            "aliases": "Example Person",
            "olympiads": "IOI",
            "first_year": 2007,
            "last_year": 2007,
            "awards": "Gold",
            "confidence": "probable",
            "organization": "AGI Lab",
            "role": "Chief Executive Officer",
            "organization_category": "Industry",
            "role_category": "Leadership",
            "destination_status": "latest_employment",
            "profile_url": "https://example.com/profile",
            "linkedin_url": "",
            "research_scope": "career",
            "evidence_urls": "https://example.com/profile",
        }
        affiliations = [
            {
                "organization": "AGI Lab",
                "role": "Chief Executive Officer",
                "affiliation_type": "employment",
                "is_current": True,
                "evidence_kind": "destination_source_review",
                "evidence_text": (
                    "The reviewed source identifies the person as CEO of both "
                    "AGI Lab and Khan Group concurrently."
                ),
            },
            {
                "organization": "Khan Group",
                "role": "Chief Executive Officer",
                "affiliation_type": "employment",
                "is_current": True,
                "evidence_kind": "manual_web_evidence",
                "evidence_text": "The role remains current.",
            },
            {
                "organization": "Old Employer",
                "role": "Engineer",
                "affiliation_type": "employment",
                "is_current": True,
                "evidence_kind": "manual_web_evidence",
                "evidence_text": "Not named by the destination review.",
            },
        ]

        person = compact_person(row, affiliations=affiliations)

        self.assertEqual(
            [destination["organization"] for destination in person["destinations"]],
            ["AGI Lab", "Khan Group"],
        )
        self.assertTrue(
            all(
                destination["role"] == "Chief Executive Officer"
                for destination in person["destinations"]
            )
        )

    def test_ui_keeps_only_one_olympiad_source(self):
        row = {
            "linkedin_url": "https://linkedin.com/in/example",
            "profile_url": "https://example.com/outcome",
            "organization": "Example Co",
            "evidence_urls": (
                "https://www.imo-official.org/results/contestant/1/;"
                "https://ipho-unofficial.org/countries/KAZ/individual"
            ),
        }
        evidence = [
            {
                "claim_type": "olympiad_participation",
                "review_status": "accepted",
                "source_url": "https://www.imo-official.org/results/contestant/1/",
            },
            {
                "claim_type": "olympiad_participation",
                "review_status": "accepted",
                "source_url": "https://ipho-unofficial.org/countries/KAZ/individual",
            },
        ]

        sources = compact_sources(row, {}, [], evidence)

        olympiad_sources = [source for source in sources if source["kind"] == "olympiad"]
        self.assertEqual(len(olympiad_sources), 1)
        self.assertIn("contestant", olympiad_sources[0]["url"])

    def test_ui_prefers_https_for_duplicate_olympiad_profile_urls(self):
        row = {
            "linkedin_url": "https://linkedin.com/in/example",
            "profile_url": "https://linkedin.com/in/example",
            "organization": "Example Co",
            "evidence_urls": (
                "http://stats.ioinformatics.org/people/2474;"
                "https://stats.ioinformatics.org/people/2474"
            ),
        }

        sources = compact_sources(row, {}, [], [])

        olympiad_sources = [source for source in sources if source["kind"] == "olympiad"]
        self.assertEqual(len(olympiad_sources), 1)
        self.assertEqual(
            olympiad_sources[0]["url"],
            "https://stats.ioinformatics.org/people/2474",
        )

    def test_ui_does_not_publish_live_ioi_fallback_url(self):
        row = {
            "linkedin_url": "",
            "profile_url": "",
            "organization": "",
            "evidence_urls": "https://stats.ioinformatics.org/results/KAZ",
        }
        evidence = [
            {
                "claim_type": "olympiad_participation",
                "review_status": "accepted",
                "source_url": "https://stats.ioinformatics.org/results/KAZ",
            }
        ]

        sources = compact_sources(row, {}, [], evidence)

        self.assertEqual(sources, [])

    def test_destination_review_source_beats_superseded_profile_summary(self):
        row = {
            "linkedin_url": "https://linkedin.com/in/example",
            "profile_url": "https://example.test/old-employer",
            "organization": "Current Co",
            "evidence_urls": "",
        }
        evidence = [
            {
                "claim_type": "career_outcome",
                "review_status": "superseded",
                "supports_final_outcome": False,
                "source_url": "https://example.test/old-employer",
            },
            {
                "claim_type": "destination_source_review",
                "review_status": "accepted",
                "supports_final_outcome": True,
                "source_url": "https://example.test/current-employer",
            },
        ]
        location = {"evidence_url": "https://example.test/current-employer"}

        sources = compact_sources(row, location, [], evidence)
        outcome_sources = [source for source in sources if source["kind"] == "outcome"]

        self.assertEqual(
            outcome_sources,
            [
                {
                    "url": "https://example.test/current-employer",
                    "kind": "outcome",
                    "label": "Reviewed destination source",
                    "icon": "briefcase-business",
                }
            ],
        )
        self.assertFalse(
            any(source["url"] == row["profile_url"] for source in sources)
        )

    def test_alma_icons_prefer_official_sources_over_profile_rows(self):
        row = {
            "linkedin_url": "https://linkedin.com/in/example",
            "profile_url": "https://linkedin.com/in/example",
            "organization": "Example Co",
            "evidence_urls": "",
        }
        affiliations = [
            {
                "organization": "Vanderbilt University",
                "affiliation_type": "education",
                "selected_as_alma_mater": True,
                "evidence_url": "https://linkedin.com/in/example",
                "evidence_kind": "accepted_linkedin_profile",
                "confidence": "probable",
            },
            {
                "organization": "Vanderbilt University",
                "affiliation_type": "education",
                "selected_as_alma_mater": False,
                "evidence_url": "https://vanderbilt.edu/commencement.pdf",
                "evidence_kind": "official_commencement_program",
                "confidence": "confirmed",
            },
            {
                "organization": "Yale University",
                "affiliation_type": "education",
                "selected_as_alma_mater": True,
                "evidence_url": "https://linkedin.com/in/example",
                "evidence_kind": "accepted_linkedin_profile",
                "confidence": "probable",
            },
            {
                "organization": "Yale University",
                "affiliation_type": "education",
                "selected_as_alma_mater": False,
                "evidence_url": "https://yale.edu/degree-list",
                "evidence_kind": "official_degree_list",
                "confidence": "confirmed",
            },
        ]

        sources = compact_sources(row, {}, affiliations, [])
        education_urls = {
            source["url"] for source in sources if source["kind"] == "education"
        }

        self.assertEqual(
            education_urls,
            {
                "https://vanderbilt.edu/commencement.pdf",
                "https://yale.edu/degree-list",
            },
        )

    def test_published_talgat_record_uses_honeywell_uae_location(self):
        html = Path("docs/index.html").read_text(encoding="utf-8")
        match = re.search(
            r'\{"id":"kaz-7907a5491483".*?"scope":"career"\}',
            html,
        )

        self.assertIsNotNone(match)
        person = json.loads(match.group(0))
        self.assertEqual(person["organization"], "Honeywell")
        self.assertEqual(person["countryCode"], "AE")
        self.assertEqual(
            person["locationEvidenceKind"],
            "active_affiliation_profile_location",
        )
        self.assertEqual(person["country"], "United Arab Emirates")
        self.assertIn("Abu Dhabi", person["location"])

    def test_published_zhomart_record_includes_both_ceo_destinations(self):
        html = Path("docs/index.html").read_text(encoding="utf-8")
        match = re.search(
            r'\{"id":"kaz-d5a9e6425d45".*?"scope":"career"\}',
            html,
        )

        self.assertIsNotNone(match)
        person = json.loads(match.group(0))
        self.assertEqual(
            [destination["organization"] for destination in person["destinations"]],
            ["AGI Lab", "Khan Group"],
        )
        self.assertTrue(
            all(
                destination["role"] == "Chief Executive Officer"
                for destination in person["destinations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
