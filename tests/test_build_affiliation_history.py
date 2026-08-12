import unittest

from scripts.build_affiliation_history import (
    build_rows,
    education_score,
    extract_affiliations,
    is_postsecondary_education,
    merge_undated_duplicates,
    normalized_type,
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

    def test_extracts_beng_linked_education_heading(self):
        rows = extract_affiliations(
            "## Education "
            "### BEng in Computer Science + AI at "
            "[The Hong Kong University of Science and Technology]"
            "(https://www.linkedin.com/school/hkust) "
            "2023 - 2027 (4 years) in Kowloon, Hong Kong"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Hong Kong University of Science and Technology (HKUST)",
        )
        self.assertEqual(rows[0]["role"], "BEng in Computer Science + AI")
        self.assertEqual(rows[0]["affiliation_type"], "education")

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

    def test_distance_education_department_specialist_is_employment(self):
        rows = extract_affiliations(
            "## Experience "
            "### Senior specialist of Distance Education Department - "
            "[Kaspi Bank](https://linkedin.com/company/kaspi-kz) "
            "Jan 2008 - Jan 2009"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Kaspi.kz")
        self.assertEqual(rows[0]["affiliation_type"], "employment")

    def test_specialist_jobs_and_degrees_are_distinguished(self):
        self.assertEqual(
            normalized_type("education", "Finance Specialist"),
            "employment",
        )
        self.assertEqual(
            normalized_type("education", "Postdoctoral Associate II"),
            "employment",
        )
        self.assertEqual(
            normalized_type("education", "Specialist Mathematics & Computer Science"),
            "education",
        )
        self.assertEqual(
            normalized_type("education", "Investment Associate"),
            "employment",
        )
        self.assertEqual(
            normalized_type("education", "Associate's degree, Computer Science"),
            "education",
        )
        self.assertEqual(
            normalized_type("education", "специалист"),
            "employment",
        )
        self.assertEqual(
            normalized_type("education", "Специалист по маркетингу"),
            "employment",
        )
        self.assertEqual(
            normalized_type("education", "Специалист, Международные отношения"),
            "education",
        )

    def test_student_roles_are_education_even_when_source_type_is_employment(self):
        self.assertEqual(normalized_type("employment", "PhD candidate"), "education")
        self.assertEqual(
            normalized_type("employment", "Magistrant student"), "education"
        )
        self.assertEqual(
            normalized_type("employment", "PhD Student & Research Assistant"),
            "education",
        )
        self.assertEqual(
            normalized_type("employment", "Student Recruiting Manager"),
            "employment",
        )

    def test_teaching_assistant_is_employment_but_phd_student_role_is_education(self):
        rows = extract_affiliations(
            "## Experience "
            "### Graduate Teaching Assistant - Example University "
            "Sep 2024 - Dec 2024 "
            "### PhD Student & Research Assistant - Graduate University "
            "Jan 2025 - Present "
            "### Undergraduate Student Researcher - Research University "
            "Jun 2024 - Aug 2024"
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["affiliation_type"], "employment")
        self.assertEqual(rows[1]["affiliation_type"], "education")
        self.assertEqual(rows[2]["affiliation_type"], "employment")

    def test_russian_specialist_job_is_not_education(self):
        rows = extract_affiliations(
            "## Experience "
            "### Специалист по маркетингу - ТОО «ТемирЗем» (Current) "
            "Jul 2016 - Present "
            "### специалист - КГУ \"Центр занятости\" "
            "Sep 2011 - Jul 2014 "
            "## Education "
            "### Специалист, Международные отношения at КазНУ им. аль-Фараби "
            "1998 - 2003"
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["affiliation_type"], "employment")
        self.assertEqual(rows[1]["affiliation_type"], "employment")
        self.assertEqual(rows[2]["affiliation_type"], "education")

    def test_research_affiliation_is_not_postsecondary_education(self):
        self.assertFalse(
            is_postsecondary_education(
                {
                    "organization": "Example University",
                    "role": "Research author",
                    "evidence_text": "Research author at Example University",
                }
            )
        )

    def test_degree_is_not_rejected_by_assistant_detail(self):
        self.assertTrue(
            is_postsecondary_education(
                {
                    "organization": "Iowa State University",
                    "role": "M.S. Computer Science Economics",
                    "evidence_text": "Research and teaching assistant duties.",
                }
            )
        )

    def test_foreign_exchange_finance_degree_is_an_alma_mater(self):
        self.assertTrue(
            is_postsecondary_education(
                {
                    "organization": "Narxoz University",
                    "role": "Bachelor's degree, International Finance and Foreign Exchange",
                    "evidence_text": "Bachelor's degree at the Kazakh State Academy of Management.",
                }
            )
        )

    def test_physics_and_technology_institute_is_postsecondary(self):
        self.assertTrue(
            is_postsecondary_education(
                {
                    "organization": "Moscow Institute of Physics and Technology (MIPT)",
                    "role": "",
                    "evidence_text": "",
                }
            )
        )

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

    def test_leadership_title_with_school_name_is_employment(self):
        rows = extract_affiliations(
            "### [Nazarbayev University](https://linkedin.com/company/nu) "
            "#### Executive Director, School of Medicine "
            "Jan 2015 - Dec 2017 in Astana, Kazakhstan"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Nazarbayev University")
        self.assertEqual(rows[0]["affiliation_type"], "employment")

    def test_recovers_undergraduate_degree_without_education_section(self):
        rows = extract_affiliations(
            "### Undergraduate, Chemistry at "
            "[Orta Doğu Teknik Üniversitesi](https://linkedin.com/school/metu) "
            "2014 - 2019 (5 years) in Ankara, Türkiye"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Middle East Technical University")
        self.assertEqual(rows[0]["affiliation_type"], "education")

    def test_recovers_specialist_degree_inside_education_section(self):
        rows = extract_affiliations(
            "## Education\n"
            "### Specialist Mathematics & Computer Science at "
            "Saint-Petersburg State University\n"
            "2007 - 2012 (5 years)"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Saint Petersburg State University")
        self.assertEqual(rows[0]["role"], "Specialist Mathematics & Computer Science")

    def test_recovers_linked_school_with_leading_at(self):
        rows = extract_affiliations(
            "## Education\n"
            "### at [Nazarbayev University](https://linkedin.com/school/nu)\n"
            "2015 - 2019"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Nazarbayev University")
        self.assertEqual(rows[0]["role"], "")

    def test_linked_school_ignores_descriptive_body_as_role(self):
        rows = extract_affiliations(
            "## Education\n"
            "### [Kazakh-Turkish lyceum for gifted students]"
            "(https://linkedin.com/school/bilim)\n"
            "Kazakhstan\n\nStudent of the year\n\n"
            "Kazakh-Turkish lyceum for gifted students is an educational institution."
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Bilim-Innovation Lyceums (BIL)")
        self.assertEqual(rows[0]["role"], "")

    def test_recovers_bare_known_university_acronym(self):
        rows = extract_affiliations(
            "## Education\n### KBTU\n2010 - 2014"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Kazakh-British Technical University (KBTU)",
        )

    def test_recovers_russian_bachelor_degree(self):
        rows = extract_affiliations(
            "## Education\n"
            "### бакалавр, Прикладная математика at "
            "Казахский национальный университет имени аль-Фараби\n"
            "2001 - 2006"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["organization"],
            "Al-Farabi Kazakh National University",
        )

    def test_recovers_abbreviated_us_degrees(self):
        rows = extract_affiliations(
            "## Education\n"
            "### M.S. Computer Science Economics at Iowa State University\n"
            "2014 - 2016\n"
            "### B.S. Computer Science Math at University of Nebraska-Lincoln\n"
            "2010 - 2014"
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["role"], "M.S. Computer Science Economics")
        self.assertEqual(rows[1]["role"], "B.S. Computer Science Math")


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

    def test_combined_degree_record_beats_single_degree_at_same_school(self):
        combined = {
            "organization": "KBTU",
            "role": "Bachelor's degree; Master's degree",
            "start_year": "",
            "end_year": "",
        }
        masters_only = {
            "organization": "KBTU",
            "role": "Master's degree",
            "start_year": "",
            "end_year": "",
        }

        self.assertGreater(
            education_score(combined, "Current Co", False, 2026),
            education_score(masters_only, "Current Co", False, 2026),
        )

    def test_selects_undergraduate_and_postgraduate_institutions(self):
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
                "organization": "Example High School",
                "role": "",
                "affiliation_type": "education",
                "start_year": "2014",
                "end_year": "2018",
                "is_current": "false",
                "evidence_url": "https://example.com/profile",
                "confidence": "confirmed",
            },
            {
                "person_id": "person-1",
                "organization": "Example University",
                "role": "Bachelor of Science",
                "affiliation_type": "education",
                "start_year": "2018",
                "end_year": "2022",
                "is_current": "false",
                "evidence_url": "https://example.com/profile",
                "confidence": "confirmed",
            },
            {
                "person_id": "person-1",
                "organization": "Graduate University",
                "role": "Master of Science",
                "affiliation_type": "education",
                "start_year": "2022",
                "end_year": "2024",
                "is_current": "false",
                "evidence_url": "https://example.com/profile",
                "confidence": "confirmed",
            },
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)
        selected = {
            row["organization"]
            for row in rows
            if row["selected_as_alma_mater"]
        }

        self.assertEqual(
            selected,
            {"Example University", "Graduate University"},
        )

    def test_keeps_only_one_secondary_school_when_no_university_is_known(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://example.com/profile",
                "organization": "",
                "affiliation_type": "",
            }
        ]
        manual = [
            {
                "person_id": "person-1",
                "organization": "First High School",
                "role": "",
                "affiliation_type": "education",
                "start_year": "2018",
                "end_year": "2020",
                "evidence_url": "https://example.com/profile",
            },
            {
                "person_id": "person-1",
                "organization": "Second High School",
                "role": "",
                "affiliation_type": "education",
                "start_year": "2020",
                "end_year": "2022",
                "evidence_url": "https://example.com/profile",
            },
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)

        self.assertEqual(
            sum(bool(row["selected_as_alma_mater"]) for row in rows),
            1,
        )

    def test_student_instructor_role_is_not_selected_as_alma_mater(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://example.com/profile",
                "organization": "Current Co",
                "affiliation_type": "employment",
            }
        ]
        manual = [
            {
                "person_id": "person-1",
                "organization": "Example University",
                "role": "Bachelor of Science",
                "affiliation_type": "education",
                "start_year": "2018",
                "end_year": "2022",
                "evidence_url": "https://example.com/profile",
            },
            {
                "person_id": "person-1",
                "organization": "Example University Engineering Department",
                "role": "Undergraduate Student Instructor",
                "affiliation_type": "education",
                "start_year": "2021",
                "end_year": "2022",
                "evidence_url": "https://example.com/profile",
            },
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)
        selected = {
            row["organization"]
            for row in rows
            if row["selected_as_alma_mater"]
        }

        self.assertEqual(selected, {"Example University"})

    def test_short_program_and_employment_title_are_not_alma_maters(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://example.com/profile",
                "organization": "Current Co",
                "affiliation_type": "employment",
            }
        ]
        manual = [
            {
                "person_id": "person-1",
                "organization": "Degree University",
                "role": "Master of Science",
                "affiliation_type": "education",
                "start_year": "2022",
                "end_year": "2024",
                "evidence_url": "https://example.com/profile",
            },
            {
                "person_id": "person-1",
                "organization": "Summer University",
                "role": "Summer Research School",
                "affiliation_type": "education",
                "start_year": "2023",
                "end_year": "2023",
                "evidence_url": "https://example.com/profile",
            },
            {
                "person_id": "person-1",
                "organization": "Employer University",
                "role": "Acting Dean of Research School",
                "affiliation_type": "education",
                "start_year": "2024",
                "end_year": "2025",
                "evidence_url": "https://example.com/profile",
            },
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)
        selected = {
            row["organization"]
            for row in rows
            if row["selected_as_alma_mater"]
        }

        self.assertEqual(selected, {"Degree University"})

    def test_summer_semester_in_evidence_is_not_an_alma_mater(self):
        row = {
            "organization": "University at Buffalo",
            "role": "Chemical Engineering",
            "evidence_text": "May 2018 - Jul 2018 Summer Semester",
        }

        self.assertFalse(is_postsecondary_education(row))

    def test_graduate_studies_are_postsecondary_education(self):
        self.assertTrue(
            is_postsecondary_education(
                {
                    "organization": "École Nationale Supérieure de Géologie (ENSG)",
                    "role": "Graduate studies",
                    "evidence_text": "",
                }
            )
        )


class ManualAffiliationTest(unittest.TestCase):
    def test_search_snippet_is_not_joined_to_a_different_person(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://linkedin.com/in/example",
                "linkedin_url": "https://linkedin.com/in/example",
                "organization": "",
                "affiliation_type": "",
            }
        ]
        searches = [
            {
                "person_id": "different-person",
                "results": [
                    {
                        "url": "https://linkedin.com/in/example",
                        "highlights": [
                            "## Education ### Bachelor of Science at "
                            "Example University 2010 - 2020"
                        ],
                    }
                ],
            }
        ]

        rows = build_rows(people, searches, [], [], [], [], [], 2026)

        self.assertEqual(rows, [])

    def test_owner_search_snippet_can_supply_affiliation_history(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "profile_url": "https://linkedin.com/in/example",
                "linkedin_url": "https://linkedin.com/in/example",
                "organization": "",
                "affiliation_type": "",
            }
        ]
        searches = [
            {
                "person_id": "person-1",
                "results": [
                    {
                        "url": "https://linkedin.com/in/example",
                        "highlights": [
                            "## Education ### Bachelor of Science at "
                            "Example University 2018 - 2022"
                        ],
                    }
                ],
            }
        ]

        rows = build_rows(people, searches, [], [], [], [], [], 2026)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "Example University")
        self.assertEqual(rows[0]["start_year"], "2018")

    def test_undated_duplicate_is_folded_into_latest_dated_source_record(self):
        common = {
            "person_id": "person-1",
            "name": "Example Person",
            "organization": "Example Co",
            "role": "Engineer",
            "affiliation_type": "employment",
            "evidence_url": "https://example.com/profile",
            "confidence": "probable",
            "selected_as_alma_mater": False,
        }
        rows = [
            {
                **common,
                "start_year": "2020",
                "end_year": "2022",
                "is_current": False,
                "evidence_kind": "accepted_linkedin_profile",
                "evidence_text": "Past period.",
            },
            {
                **common,
                "start_year": "2024",
                "end_year": "",
                "is_current": True,
                "evidence_kind": "accepted_linkedin_profile",
                "evidence_text": "Current period.",
            },
            {
                **common,
                "start_year": "",
                "end_year": "",
                "is_current": True,
                "evidence_kind": "destination_source_review",
                "evidence_text": "Reviewed current destination.",
                "confidence": "confirmed",
            },
        ]

        merged = merge_undated_duplicates(rows)

        self.assertEqual(len(merged), 2)
        current = next(row for row in merged if row["start_year"] == "2024")
        self.assertEqual(current["evidence_kind"], "destination_source_review")
        self.assertEqual(current["confidence"], "confirmed")
        self.assertEqual(current["evidence_text"], "Reviewed current destination.")

    def test_undated_manual_summary_does_not_replace_profile_provenance(self):
        common = {
            "person_id": "person-1",
            "name": "Example Person",
            "organization": "Example Co",
            "role": "Engineer",
            "affiliation_type": "employment",
            "evidence_url": "https://example.com/profile",
            "confidence": "confirmed",
            "selected_as_alma_mater": False,
        }
        rows = [
            {
                **common,
                "start_year": "2024",
                "end_year": "",
                "is_current": True,
                "evidence_kind": "accepted_linkedin_profile",
                "evidence_text": "Dated profile record.",
            },
            {
                **common,
                "start_year": "",
                "end_year": "",
                "is_current": True,
                "evidence_kind": "manual_review",
                "evidence_text": "Longer manually reviewed outcome summary.",
            },
        ]

        merged = merge_undated_duplicates(rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["evidence_kind"], "accepted_linkedin_profile")
        self.assertEqual(merged[0]["evidence_text"], "Dated profile record.")

    def test_attached_degree_dates_beat_overlapping_achievement_dates(self):
        common = {
            "person_id": "person-1",
            "name": "Example Person",
            "organization": "Example University",
            "role": "Bachelor of Applied Science",
            "affiliation_type": "education",
            "evidence_url": "https://linkedin.com/in/example",
            "evidence_kind": "accepted_linkedin_profile",
            "confidence": "probable",
            "selected_as_alma_mater": False,
            "is_current": False,
        }
        rows = [
            {
                **common,
                "start_year": "2018",
                "end_year": "2021",
                "evidence_text": (
                    "Bachelor of Applied Science at Example University "
                    "2018 - 2021 (3 years)"
                ),
            },
            {
                **common,
                "start_year": "2010",
                "end_year": "2020",
                "evidence_text": (
                    "Bachelor of Applied Science at Example University ... "
                    + "profile summary " * 30
                    + "competition achievements 2010-2020"
                ),
            },
        ]

        merged = merge_undated_duplicates(rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["start_year"], "2018")
        self.assertEqual(merged[0]["end_year"], "2021")

    def test_reviewed_open_history_beats_bounded_destination_summary(self):
        common = {
            "person_id": "person-1",
            "name": "Example Person",
            "organization": "Example University",
            "role": "Undergraduate Student",
            "affiliation_type": "education",
            "start_year": "2000",
            "is_current": False,
            "selected_as_alma_mater": False,
            "evidence_url": "https://example.com/source",
            "confidence": "probable",
            "evidence_text": "Historical enrollment record.",
        }
        rows = [
            {
                **common,
                "end_year": "",
                "evidence_kind": "reviewed_olympiad_destination_table",
            },
            {**common, "end_year": "2000", "evidence_kind": "manual_review"},
        ]

        merged = merge_undated_duplicates(rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["end_year"], "")
        self.assertEqual(
            merged[0]["evidence_kind"], "reviewed_olympiad_destination_table"
        )

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

    def test_verified_education_with_future_graduation_is_current(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "organization": "MIT",
                "affiliation_type": "education",
            }
        ]
        verified = [
            {
                "person_id": "person-1",
                "organization": "MIT",
                "role": "Undergraduate Student",
                "affiliation_type": "education",
                "start_year": "2023",
                "end_year": "2029",
                "career_evidence_url": "https://example.com/profile",
                "confidence": "confirmed",
            }
        ]

        rows = build_rows(people, [], [], [], verified, [], [], 2026)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_current"])

    def test_explicit_manual_past_flag_overrides_graduation_year(self):
        people = [
            {
                "person_id": "person-1",
                "name": "Example Person",
                "confidence": "confirmed",
                "organization": "ENS",
                "affiliation_type": "education",
            }
        ]
        manual = [
            {
                "person_id": "person-1",
                "organization": "HKUST",
                "role": "Undergraduate Student",
                "affiliation_type": "education",
                "start_year": "2025",
                "end_year": "2026",
                "is_current": "false",
                "evidence_url": "https://example.com/profile",
                "confidence": "confirmed",
            }
        ]

        rows = build_rows(people, [], [], [], [], manual, [], 2026)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_current"])


if __name__ == "__main__":
    unittest.main()
