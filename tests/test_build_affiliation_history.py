import unittest

from scripts.build_affiliation_history import (
    build_rows,
    education_score,
    extract_affiliations,
)


class LinkedInAffiliationExtractionTest(unittest.TestCase):
    def test_extracts_current_and_past_jobs_and_education(self):
        rows = extract_affiliations(
            "## Experience "
            "### Engineer - [Current Co](https://linkedin.com/company/current) (Current) "
            "Jan 2024 - Present in Zurich, Switzerland "
            "### Analyst - [Past Co](https://linkedin.com/company/past) "
            "2021 - 2023 in Almaty, Kazakhstan "
            "## Education "
            "### Bachelor's degree, Mathematics at "
            "[Nazarbayev University](https://linkedin.com/school/nu) 2017 - 2021"
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["organization"], "Current Co")
        self.assertTrue(rows[0]["is_current"])
        self.assertEqual(rows[1]["organization"], "Past Co")
        self.assertEqual(rows[1]["end_year"], "2023")
        self.assertEqual(rows[2]["organization"], "Nazarbayev University")
        self.assertEqual(rows[2]["affiliation_type"], "education")

    def test_extracts_grouped_employer_roles(self):
        rows = extract_affiliations(
            "## Experience "
            "### [Nazarbayev Intellectual Schools](https://linkedin.com/school/nis) "
            "#### Chemistry Olympiad Coach Feb 2020 - Feb 2020 in Astana, Kazakhstan"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"], "Nazarbayev Intellectual Schools (NIS)"
        )
        self.assertEqual(rows[0]["role"], "Chemistry Olympiad Coach")

    def test_infers_grouped_employer_without_section_heading(self):
        rows = extract_affiliations(
            "### [Citadel Securities](https://linkedin.com/company/citadel) "
            "#### Quantitative Researcher (Current) Sep 2024 - Present "
            "### Bachelor's degree Computer Science at Korea Advanced Institute "
            "of Science and Technology 2014 - 2018"
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["organization"], "Citadel Securities")
        self.assertEqual(rows[0]["affiliation_type"], "employment")
        self.assertEqual(
            rows[1]["organization"],
            "Korea Advanced Institute of Science and Technology (KAIST)",
        )
        self.assertEqual(rows[1]["affiliation_type"], "education")

    def test_grouped_school_degree_is_education(self):
        rows = extract_affiliations(
            "### [MIT](https://linkedin.com/school/mit) "
            "#### Bachelor of Science, Mathematics 2018 - 2022"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Massachusetts Institute of Technology (MIT)",
        )
        self.assertEqual(rows[0]["affiliation_type"], "education")

    def test_extracts_grouped_degrees_inside_education_section(self):
        rows = extract_affiliations(
            "## Education\n"
            "### [MIT](https://linkedin.com/school/mit)\n"
            "#### Bachelor's degree, Mathematics\n"
            "Cambridge, Massachusetts, United States\n"
            "#### Bachelor's Degree, Computer Science\n"
            "Cambridge, Massachusetts, United States"
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["organization"], "Massachusetts Institute of Technology (MIT)")
        self.assertEqual(rows[0]["role"], "Bachelor's degree, Mathematics")
        self.assertEqual(rows[1]["role"], "Bachelor's Degree, Computer Science")

    def test_ignores_projects_and_organizations_sections(self):
        rows = extract_affiliations(
            "## Experience\n"
            "### Engineer - [Current Co](https://linkedin.com/company/current) "
            "(Current) Jan 2024 - Present\n"
            "## Projects\n"
            "### Founder - Fake Project Jan 2020 - Present\n"
            "## Organizations\n"
            "### user at MathOverflow Jan 2017 - Present"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Current Co")

    def test_stale_present_flag_does_not_make_one_off_program_current(self):
        rows = extract_affiliations(
            "## Experience "
            "### RSI 2018 Participant - [Center for Excellence in Education]"
            "(https://linkedin.com/company/cee) (Current) Jun 2018 - Present"
        )

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_current"])
        self.assertEqual(rows[0]["end_year"], "2018")

    def test_does_not_treat_awards_as_jobs(self):
        self.assertEqual(
            extract_affiliations(
                "### International Chemistry Olympiad - Bronze Medal "
                "Issued by IChO Aug 2019"
            ),
            [],
        )

    def test_rejects_truncated_markdown_organizations(self):
        self.assertEqual(
            extract_affiliations(
                "### Bachelor's degree, Physics at [N ... 2018 - 2022"
            ),
            [],
        )

    def test_recovers_plain_degree_heading_from_date_range(self):
        rows = extract_affiliations(
            "### B.Sc. in Mathematical Sciences at Nanyang Technological University "
            "2005 - 2009 (4 years)"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Nanyang Technological University (NTU)",
        )
        self.assertEqual(rows[0]["affiliation_type"], "education")

    def test_strips_date_prefix_from_recovered_school(self):
        rows = extract_affiliations(
            "### Bachelor, Computer Science at 2005-2006, "
            "Suleyman Demirel University 2005 - 2009"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Suleyman Demirel University (SDU)")

    def test_rejects_duration_fragments_as_organizations(self):
        self.assertEqual(
            extract_affiliations(
                "### Teacher of - Aug 2022 (4 years and 4 months) in "
                "Apr 2018 - Aug 2022"
            ),
            [],
        )

    def test_rejects_incomplete_institution_names(self):
        self.assertEqual(
            extract_affiliations(
                "## Education ### [University of](https://linkedin.com/school/example)"
            ),
            [],
        )

    def test_job_about_text_is_not_parsed_as_education(self):
        rows = extract_affiliations(
            "### Software Engineer - [Google](https://linkedin.com/company/google) "
            "(Current) ... Dec 2024 - Present ... Software engineer at Vertex AI "
            "Search, Gemini Enterprise."
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Google")
        self.assertEqual(rows[0]["affiliation_type"], "employment")


class AlmaMaterSelectionTest(unittest.TestCase):
    def test_completed_prior_school_beats_current_destination_school(self):
        prior = {
            "organization": "Nazarbayev University",
            "role": "Bachelor's degree",
            "start_year": "2017",
            "end_year": "2021",
        }
        current = {
            "organization": "MIT",
            "role": "PhD Student",
            "start_year": "2022",
            "end_year": "",
        }

        self.assertGreater(
            education_score(prior, "MIT", True, 2026),
            education_score(current, "MIT", True, 2026),
        )


class ManualAffiliationTest(unittest.TestCase):
    def test_includes_sourced_manual_history_and_selects_alma_mater(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://example.com/profile",
                "linkedin_url": "",
                "organization": "Current Co",
                "affiliation_type": "employment",
            }
        ]
        manual = [
            {
                "person_id": "person-1",
                "organization": "MIT",
                "role": "Bachelor of Science, Mathematics",
                "affiliation_type": "education",
                "start_year": "",
                "end_year": "",
                "is_current": "false",
                "evidence_url": "https://example.com/profile",
                "evidence_kind": "manual_profile_transcription",
                "confidence": "confirmed",
                "evidence_text": "Reviewed profile education entry.",
            }
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Massachusetts Institute of Technology (MIT)",
        )
        self.assertTrue(rows[0]["selected_as_alma_mater"])
        self.assertEqual(rows[0]["evidence_kind"], "manual_profile_transcription")

    def test_destination_review_is_published_as_sourced_history(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://example.com/profile",
                "linkedin_url": "",
                "organization": "Current Co",
                "affiliation_type": "employment",
            }
        ]
        reviews = [
            {
                "person_id": "person-1",
                "organization": "Current Co",
                "role": "Principal Engineer",
                "affiliation_type": "employment",
                "start_year": "2025",
                "end_year": "",
                "evidence_url": "https://example.com/profile",
                "review_reason": "The source states the exact current title.",
            }
        ]

        rows = build_rows(people, [], [], [], [], [], [], 2026, reviews)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "Principal Engineer")
        self.assertEqual(rows[0]["evidence_kind"], "destination_source_review")
        self.assertTrue(rows[0]["is_current"])


if __name__ == "__main__":
    unittest.main()
