import unittest

from scripts.build_affiliation_history import (
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
        self.assertEqual(rows[0]["organization"], "Nazarbayev Intellectual Schools")
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
            "Korea Advanced Institute of Science and Technology",
        )
        self.assertEqual(rows[1]["affiliation_type"], "education")

    def test_grouped_school_degree_is_education(self):
        rows = extract_affiliations(
            "### [MIT](https://linkedin.com/school/mit) "
            "#### Bachelor of Science, Mathematics 2018 - 2022"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "MIT")
        self.assertEqual(rows[0]["affiliation_type"], "education")

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
        self.assertEqual(rows[0]["organization"], "Nanyang Technological University")
        self.assertEqual(rows[0]["affiliation_type"], "education")

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


if __name__ == "__main__":
    unittest.main()
