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


if __name__ == "__main__":
    unittest.main()
