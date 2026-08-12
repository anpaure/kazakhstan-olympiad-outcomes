import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_location_evidence import (
    build_rows,
    country_from_location,
    extract_current_roles,
    extract_location,
    load_organization_locations,
)
from scripts.organization_names import canonicalize_organization, organization_key


class LocationExtractionTest(unittest.TestCase):
    def test_current_role_location_is_preferred_over_profile_header(self):
        result = extract_location(
            "# Person CTO at Example Singapore (SG) 57 connections "
            "## Experience ### CTO - Example (Current) "
            "Jan 2025 - Present in Kazakhstan"
        )

        self.assertEqual(result["country_code"], "KZ")
        self.assertEqual(result["evidence_kind"], "current_role_location")

    def test_current_role_location_is_used_without_profile_location(self):
        result = extract_location(
            "### Engineer - Example (Current) ... Jan 2025 - Present "
            "in Zurich, Switzerland ... Department: Engineering"
        )

        self.assertEqual(result["country_code"], "CH")
        self.assertEqual(result["location_label"], "Zurich, Switzerland")
        self.assertEqual(result["evidence_kind"], "current_role_location")

    def test_degree_abbreviation_is_not_a_country_code(self):
        self.assertIsNone(
            extract_location(
                "Bachelor of Science (BS) ... University degree with no current location"
            )
        )

    def test_employer_headquarters_is_not_a_person_location(self):
        self.assertIsNone(
            extract_location(
                "### Researcher - Example (Current) ... Example has 40 employees, "
                "founded in 2020. Headquartered in South Korea."
            )
        )

    def test_employer_description_is_not_a_person_location(self):
        self.assertIsNone(
            extract_location(
                "### Researcher - University (Current) ... University is a leader "
                "in Central Asia and Kazakhstan. University has 1,000 employees."
            )
        )

    def test_project_country_is_not_mistaken_for_current_role_location(self):
        roles = extract_current_roles(
            "### Cyber Security Consultant - Honeywell (Current) ... "
            "Jan 2020 - Present in EMEA ... Acting as a member of a project "
            "team in Kazakhstan."
        )

        self.assertEqual(roles[0]["location_label"], "")
        self.assertEqual(roles[0]["country_code"], "")

    def test_city_only_current_role_location_uses_reviewed_city_map(self):
        self.assertEqual(country_from_location("Hillsboro, Oregon"), "US")
        self.assertEqual(country_from_location("Hwaseong"), "KR")
        self.assertEqual(country_from_location("Hanoi, Vietnam"), "VN")

    def test_hungary_profile_location_is_supported(self):
        result = extract_location(
            "# Example Person\n\nStudent at Debreceni Egyetem\n\n"
            "Debrecen, Hajdú-Bihar, Hungary (HU)\n\n3 connections"
        )

        self.assertEqual(result["country_code"], "HU")
        self.assertEqual(result["country_name"], "Hungary")

    def test_current_education_uses_institution_country_not_profile_header(self):
        people = [
            {
                "person_id": "kaz-test",
                "name": "Example Student",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/example-student",
                "organization": "Massachusetts Institute of Technology (MIT)",
                "affiliation_type": "education",
                "destination_status": "current_education",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/example-student",
                        "highlights": [
                            "# Example Student Astana, Kazakhstan (KZ) 20 connections"
                        ],
                    }
                ]
            }
        ]
        organization_locations = {
            "massachusetts institute of technology mit": {
                "organization": "Massachusetts Institute of Technology (MIT)",
                "country_code": "US",
                "country_name": "United States",
                "location_label": "Cambridge, Massachusetts, United States",
                "evidence_url": "https://www.mit.edu/visitmit/",
                "rationale": "MIT's official visitor page identifies its campus.",
            }
        }

        rows = build_rows(people, searches, {}, organization_locations)

        self.assertEqual(rows[0]["country_code"], "US")
        self.assertEqual(rows[0]["evidence_kind"], "current_education_location")
        self.assertEqual(rows[0]["evidence_url"], "https://www.mit.edu/visitmit/")

    def test_reviewed_active_affiliation_location_beats_network_location(self):
        people = [
            {
                "person_id": "kaz-student",
                "name": "Example Student",
                "confidence": "confirmed",
                "organization": "National School Network",
                "affiliation_type": "education",
                "destination_status": "current_education",
            }
        ]
        overrides = {
            "kaz-student": {
                "person_id": "kaz-student",
                "name": "Example Student",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Ust-Kamenogorsk, Kazakhstan",
                "evidence_url": "https://example.edu/student",
                "evidence_kind": "active_affiliation_profile_location",
                "confidence": "confirmed",
                "review_reason": "The current student source identifies the campus.",
            }
        }
        organization_locations = {
            "national school network": {
                "organization": "National School Network",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Kazakhstan",
                "evidence_url": "https://example.edu/",
                "rationale": "The network operates nationally.",
            }
        }

        rows = build_rows(people, [], overrides, organization_locations)

        self.assertEqual(rows[0]["location_label"], "Ust-Kamenogorsk, Kazakhstan")
        self.assertEqual(
            rows[0]["evidence_kind"], "active_affiliation_profile_location"
        )

    def test_current_employment_matches_destination_role_before_other_current_role(self):
        people = [
            {
                "person_id": "kaz-worker",
                "name": "Example Worker",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/example-worker",
                "organization": "Deep Infra",
                "role": "Computational Scientist",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/example-worker",
                        "highlights": [
                            "# Example Worker\n\nAstana, Kazakhstan (KZ)\n\n"
                            "500 connections\n\n## Experience\n\n"
                            "### Computational Scientist - [Deep Infra Inc.]"
                            "(https://linkedin.com/company/deep-infra) (Current)\n\n"
                            "Jul 2024 - Present (2 years) in Palo Alto, "
                            "California, United States\n\nDepartment: Research\n\n"
                            "### Member - Kazakhstan Programming Federation (Current)\n\n"
                            "Jul 2022 - Present (4 years) in Astana, Kazakhstan"
                        ],
                    }
                ]
            }
        ]

        rows = build_rows(people, searches, {})

        self.assertEqual(rows[0]["country_code"], "US")
        self.assertEqual(rows[0]["location_label"], "Palo Alto, California, United States")
        self.assertIn("is not used", rows[0]["review_reason"])

    def test_header_only_location_is_not_used_for_current_employment(self):
        people = [
            {
                "person_id": "kaz-worker",
                "name": "Example Worker",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/example-worker",
                "organization": "Global Company",
                "role": "Engineer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/example-worker",
                        "highlights": [
                            "# Example Worker Astana, Kazakhstan (KZ) 20 connections"
                        ],
                    }
                ]
            }
        ]

        self.assertEqual(build_rows(people, searches, {}), [])

    def test_profile_location_is_used_when_same_profile_has_matched_current_role(self):
        people = [
            {
                "person_id": "kaz-worker",
                "name": "Example Worker",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/example-worker",
                "organization": "Global Company",
                "role": "Engineer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/example-worker",
                        "highlights": [
                            "# Example Worker Astana, Kazakhstan (KZ) 20 connections "
                            "## Experience ### Engineer - Global Company (Current) "
                            "Jan 2025 - Present"
                        ],
                    }
                ]
            }
        ]

        rows = build_rows(people, searches, {})

        self.assertEqual(rows[0]["country_code"], "KZ")
        self.assertEqual(
            rows[0]["evidence_kind"], "active_affiliation_profile_location"
        )
        self.assertIn("matched current role", rows[0]["review_reason"])

    def test_profile_location_is_not_used_for_nonmatching_current_role(self):
        people = [
            {
                "person_id": "kaz-worker",
                "name": "Example Worker",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/example-worker",
                "organization": "Expected Company",
                "role": "Engineer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/example-worker",
                        "highlights": [
                            "# Example Worker Astana, Kazakhstan (KZ) 20 connections "
                            "## Experience ### Researcher - Different Company (Current) "
                            "Jan 2025 - Present"
                        ],
                    }
                ]
            }
        ]

        self.assertEqual(build_rows(people, searches, {}), [])

    def test_reviewed_override_supersedes_automatic_role_location(self):
        people = [
            {
                "person_id": "kaz-remote-worker",
                "name": "Remote Worker",
                "confidence": "confirmed",
                "linkedin_url": "https://linkedin.com/in/remote-worker",
                "organization": "Distributed Company",
                "role": "Engineer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/remote-worker",
                        "highlights": [
                            "# Remote Worker Astana, Kazakhstan (KZ) 20 connections "
                            "### Engineer - Distributed Company (Current) "
                            "Jan 2025 - Present in San Francisco, United States"
                        ],
                    }
                ]
            }
        ]
        overrides = {
            "kaz-remote-worker": {
                "person_id": "kaz-remote-worker",
                "name": "Remote Worker",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Astana, Kazakhstan",
                "evidence_url": "https://linkedin.com/in/remote-worker",
                "evidence_kind": "current_role_location",
                "confidence": "confirmed",
                "review_reason": "Reviewed remote-work location.",
            }
        }

        rows = build_rows(people, searches, overrides)

        self.assertEqual(rows[0]["country_code"], "KZ")
        self.assertEqual(rows[0]["location_label"], "Astana, Kazakhstan")
        self.assertEqual(
            rows[0]["evidence_kind"], "current_role_location"
        )

    def test_legal_entity_location_is_a_trusted_fallback(self):
        people = [
            {
                "person_id": "kaz-company-officer",
                "name": "Company Officer",
                "confidence": "probable",
                "organization": "Example Company",
                "role": "Chief Financial Officer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        overrides = {
            "kaz-company-officer": {
                "person_id": "kaz-company-officer",
                "name": "Company Officer",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Almaty, Kazakhstan",
                "evidence_url": "https://example.kz/company",
                "evidence_kind": "active_affiliation_legal_entity_location",
                "confidence": "probable",
                "review_reason": "The active legal entity is registered in Almaty.",
            }
        }

        rows = build_rows(people, [], overrides)

        self.assertEqual(rows[0]["country_code"], "KZ")
        self.assertEqual(
            rows[0]["evidence_kind"],
            "active_affiliation_legal_entity_location",
        )

    def test_current_research_affiliation_location_is_a_priority_override(self):
        people = [
            {
                "person_id": "kaz-researcher",
                "name": "Researcher",
                "confidence": "probable",
                "organization": "Example University",
                "role": "Physics Researcher",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        overrides = {
            "kaz-researcher": {
                "person_id": "kaz-researcher",
                "name": "Researcher",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Astana, Kazakhstan",
                "evidence_url": "https://example.edu/conference.pdf",
                "evidence_kind": "current_research_affiliation_location",
                "confidence": "probable",
                "review_reason": "A current institutional abstract places the researcher in Astana.",
            }
        }

        rows = build_rows(people, [], overrides)

        self.assertEqual(rows[0]["country_code"], "KZ")
        self.assertEqual(rows[0]["location_label"], "Astana, Kazakhstan")
        self.assertEqual(
            rows[0]["evidence_kind"], "current_research_affiliation_location"
        )

    def test_participant_history_is_not_an_outcome_country(self):
        people = [
            {
                "person_id": "kaz-confirmed",
                "name": "Confirmed Alumnus",
                "confidence": "confirmed",
                "destination_status": "none",
            }
        ]
        overrides = {
            "kaz-confirmed": {
                "person_id": "kaz-confirmed",
                "name": "Confirmed Alumnus",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Kazakhstan (last verified in 1998)",
                "evidence_url": "https://example.org/olympiad-result",
                "evidence_kind": "participant_history_location",
                "confidence": "confirmed",
                "review_reason": "The source records Olympiad participation only.",
            }
        }

        self.assertEqual(build_rows(people, [], overrides), [])

    def test_historical_adult_outcome_can_supply_country(self):
        people = [
            {
                "person_id": "kaz-alumnus",
                "name": "Reviewed Alumnus",
                "confidence": "probable",
                "destination_status": "history_only",
            }
        ]
        overrides = {
            "kaz-alumnus": {
                "person_id": "kaz-alumnus",
                "name": "Reviewed Alumnus",
                "country_code": "GB",
                "country_name": "United Kingdom",
                "location_label": "London, United Kingdom (last verified in 2015)",
                "evidence_url": "https://example.org/university-alumni-profile",
                "evidence_kind": "historical_outcome_location",
                "confidence": "probable",
                "review_reason": "A reviewed post-secondary outcome places the alumnus in London.",
            }
        }

        rows = build_rows(people, [], overrides)

        self.assertEqual(rows[0]["country_code"], "GB")
        self.assertEqual(
            rows[0]["evidence_kind"], "historical_outcome_location"
        )

    def test_unmatched_identity_stays_excluded_even_with_override(self):
        people = [
            {
                "person_id": "kaz-unmatched",
                "name": "Unmatched Alumnus",
                "confidence": "unmatched",
            }
        ]
        overrides = {
            "kaz-unmatched": {
                "person_id": "kaz-unmatched",
                "name": "Unmatched Alumnus",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Almaty, Kazakhstan",
                "evidence_url": "https://example.org/profile",
                "evidence_kind": "current_role_location",
                "confidence": "probable",
                "review_reason": "The profile is not accepted as the Olympiad alumnus.",
            }
        }

        self.assertEqual(build_rows(people, [], overrides), [])

    def test_current_role_location_beats_legal_entity_fallback(self):
        people = [
            {
                "person_id": "kaz-company-officer",
                "name": "Company Officer",
                "confidence": "probable",
                "linkedin_url": "https://linkedin.com/in/company-officer",
                "organization": "Example Company",
                "role": "Chief Financial Officer",
                "affiliation_type": "employment",
                "destination_status": "latest_employment",
            }
        ]
        searches = [
            {
                "results": [
                    {
                        "url": "https://linkedin.com/in/company-officer",
                        "highlights": [
                            "# Company Officer Almaty, Kazakhstan (KZ) "
                            "### Chief Financial Officer - Example Company (Current) "
                            "Jan 2025 - Present in London, United Kingdom"
                        ],
                    }
                ]
            }
        ]
        overrides = {
            "kaz-company-officer": {
                "person_id": "kaz-company-officer",
                "name": "Company Officer",
                "country_code": "KZ",
                "country_name": "Kazakhstan",
                "location_label": "Almaty, Kazakhstan",
                "evidence_url": "https://example.kz/company",
                "evidence_kind": "active_affiliation_legal_entity_location",
                "confidence": "probable",
                "review_reason": "The active legal entity is registered in Almaty.",
            }
        }

        rows = build_rows(people, searches, overrides)

        self.assertEqual(rows[0]["country_code"], "GB")
        self.assertEqual(rows[0]["evidence_kind"], "current_role_location")

    def test_organization_location_loader_rejects_duplicate_canonical_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.csv"
            path.write_text(
                "canonical_name,country_code,location_label,evidence_url,rationale\n"
                "MIT,US,Cambridge,https://www.mit.edu/,First\n"
                "MIT,US,Cambridge,https://www.mit.edu/,Second\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate organization location"):
                load_organization_locations(path)

    def test_all_current_education_destinations_have_location_mapping(self):
        people = json.loads(
            Path("data/researched_people.json").read_text(encoding="utf-8")
        )
        locations = load_organization_locations(Path("data/organization_locations.csv"))
        missing = sorted(
            {
                canonicalize_organization(person.get("organization"))
                for person in people
                if person.get("confidence") in {"probable", "confirmed"}
                and person.get("destination_status") == "current_education"
                and organization_key(
                    canonicalize_organization(person.get("organization"))
                )
                not in locations
            }
        )

        self.assertEqual(missing, [])

    def test_shared_university_locations_use_current_official_pages(self):
        locations = load_organization_locations(Path("data/organization_locations.csv"))

        expected = {
            "Hong Kong University of Science and Technology (HKUST)":
                "https://hkust.edu.hk/contact-us",
            "Nanyang Technological University (NTU)":
                "https://www.ntu.edu.sg/about-us/contact-us",
            "University of Cambridge":
                "https://www.cam.ac.uk/about-the-university/contact-the-university",
        }
        for organization, url in expected.items():
            self.assertEqual(
                locations[organization_key(organization)]["evidence_url"],
                url,
            )

    def test_talgat_uses_primary_honeywell_location_not_project_country(self):
        locations = {
            row["person_id"]: row
            for row in json.loads(
                Path("data/person_locations.json").read_text(encoding="utf-8")
            )
        }
        talgat = locations["kaz-7907a5491483"]

        self.assertEqual(talgat["country_code"], "AE")
        self.assertEqual(
            talgat["location_label"],
            "Abu Dhabi, Abu Dhabi Emirate, United Arab Emirates",
        )
        self.assertEqual(
            talgat["evidence_kind"], "active_affiliation_profile_location"
        )

    def test_country_from_location_supports_malaysia(self):
        self.assertEqual(
            country_from_location("Sepang, Selangor, Malaysia"), "MY"
        )

    def test_only_participant_history_rows_have_unknown_country(self):
        people = json.loads(
            Path("data/researched_people.json").read_text(encoding="utf-8")
        )
        locations = {
            row["person_id"]
            for row in json.loads(
                Path("data/person_locations.json").read_text(encoding="utf-8")
            )
            if row.get("country_code")
        }

        missing = {
            person["person_id"]
            for person in people
            if person["person_id"] not in locations
        }
        with Path("data/location_overrides.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            participant_history = {
                row["person_id"]
                for row in csv.DictReader(handle)
                if row["evidence_kind"] == "participant_history_location"
            }

        self.assertEqual(missing, participant_history)


if __name__ == "__main__":
    unittest.main()
