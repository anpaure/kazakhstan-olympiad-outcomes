import json
import unittest
from pathlib import Path


class ResearchedPeopleRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.people = {
            row["person_id"]: row
            for row in json.loads(
                Path("data/researched_people.json").read_text(encoding="utf-8")
            )
        }
        cls.affiliations = json.loads(
            Path("data/person_affiliations.json").read_text(encoding="utf-8")
        )
        cls.locations = {
            row["person_id"]: row
            for row in json.loads(
                Path("data/person_locations.json").read_text(encoding="utf-8")
            )
        }

    def alma_maters(self, person_id):
        return {
            row["organization"]
            for row in self.affiliations
            if row["person_id"] == person_id and row["selected_as_alma_mater"]
        }

    def affiliations_for(self, person_id):
        return [
            row for row in self.affiliations if row["person_id"] == person_id
        ]

    def test_anton_draganchuk_outcome_and_mipt_alma_mater(self):
        person = self.people["kaz-b76707715f6b"]

        self.assertEqual(person["organization"], "STEM Olympiads")
        self.assertEqual(person["role"], "Physics Tutor")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertIn(
            "Moscow Institute of Physics and Technology (MIPT)",
            self.alma_maters(person["person_id"]),
        )

    def test_yuriy_ten_current_iowa_state_outcome(self):
        person = self.people["kaz-8d648f29d1e0"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Iowa State University")
        self.assertEqual(person["role"], "Undergraduate Mechanical Engineering Student")
        self.assertEqual(person["confidence"], "probable")
        self.assertIn("Iowa State University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "US")
        self.assertEqual(location["location_label"], "Ames, Iowa, United States")

    def test_altynay_narmanova_mount_sinai_and_kaist(self):
        person = self.people["kaz-bd1a5011816e"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Mount Sinai Health System")
        self.assertEqual(
            person["role"],
            "Program Coordinator II, World Trade Center Health Program",
        )
        self.assertIn(
            "Korea Advanced Institute of Science and Technology (KAIST)",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "US")

    def test_merlan_nagidulin_simcc_and_ntu(self):
        person = self.people["kaz-1bea50762a08"]

        self.assertEqual(
            person["organization"],
            "Singapore International Math Contests Centre (SIMCC)",
        )
        self.assertEqual(person["role"], "Head of Scientific Committee")
        self.assertIn(
            "Nanyang Technological University (NTU)",
            self.alma_maters(person["person_id"]),
        )

    def test_yerken_tussupbekov_trade_desk_and_ntu(self):
        person = self.people["kaz-5eaeaf0aebf3"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Yerken Tussupbekov")
        self.assertEqual(person["organization"], "The Trade Desk")
        self.assertEqual(person["role"], "Lead Staff Software Engineer")
        self.assertIn(
            "Nanyang Technological University (NTU)",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "GB")

    def test_yerbolat_ablemetov_daryn_and_kbtu(self):
        person = self.people["kaz-8ad6d5a1915d"]
        location = self.locations[person["person_id"]]

        self.assertEqual(
            person["organization"],
            "Republican Scientific and Practical Center Daryn",
        )
        self.assertEqual(
            person["role"], "Head of Intellectual Events and International Cooperation"
        )
        self.assertIn(
            "Kazakh-British Technical University (KBTU)",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "KZ")

    def test_dauren_karabayev_chevron_and_two_degrees(self):
        person = self.people["kaz-76ccb7b42a10"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Dauren Karabayev")
        self.assertEqual(person["organization"], "Chevron")
        self.assertEqual(person["role"], "Executive Assignee (title not disclosed)")
        self.assertEqual(person["confidence"], "probable")
        self.assertIn("Narxoz University", self.alma_maters(person["person_id"]))
        self.assertIn("Texas A&M University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "US")
        self.assertEqual(
            location["location_label"], "San Ramon, California, United States"
        )

    def test_zhaidarzhan_zatayev_shbfinance_and_narxoz(self):
        person = self.people["kaz-b22287fe1ff1"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Zhaidarzhan Zatayev")
        self.assertEqual(person["organization"], "SHBFinance")
        self.assertEqual(person["role"], "Chief Risk Officer")
        self.assertEqual(person["confidence"], "probable")
        self.assertIn("Narxoz University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "VN")
        self.assertEqual(location["location_label"], "Vietnam")

    def test_erke_nurkenov_united_group_alatau_and_kaznu(self):
        person = self.people["kaz-7720cc1cbeae"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "United Group Alatau")
        self.assertEqual(person["role"], "Deputy Chairman of the Management Board")
        self.assertEqual(person["confidence"], "probable")
        self.assertIn(
            "Al-Farabi Kazakh National University",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Almaty, Kazakhstan")

    def test_daulet_turetayev_cptdc_and_kazakhstan(self):
        person = self.people["kaz-1d6bad0a9a90"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Daulet Turetayev")
        self.assertEqual(
            person["organization"],
            "China Petroleum Technology & Development Corporation (CPTDC)",
        )
        self.assertEqual(person["role"], "Business Development Manager (BDM)")
        self.assertEqual(person["confidence"], "probable")
        self.assertIn(
            "Almaty Management University (AlmaU)",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "KZ")

    def test_arnur_tokhtabayev_tlab_and_astana(self):
        person = self.people["kaz-5f05301e71f7"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Arnur Tokhtabayev")
        self.assertEqual(person["organization"], "tLab Technologies")
        self.assertEqual(person["role"], "Founder & CEO")
        self.assertEqual(person["confidence"], "probable")
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Astana, Kazakhstan")

    def test_nurzhan_kadzhiakbarov_security_council_and_two_degrees(self):
        person = self.people["kaz-55cdb586d884"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Nurzhan Kadzhiakbarov")
        self.assertEqual(
            person["organization"],
            "Security Council of the Republic of Kazakhstan",
        )
        self.assertEqual(person["role"], "Deputy Secretary")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertEqual(person["organization_category"], "Government")
        self.assertEqual(person["role_category"], "Leadership")
        self.assertIn("Narxoz University", self.alma_maters(person["person_id"]))
        self.assertIn(
            "Diplomatic Academy of the Ministry of Foreign Affairs of Russia",
            self.alma_maters(person["person_id"]),
        )
        self.assertEqual(location["country_code"], "KZ")

    def test_zeinul_kazhkenov_latest_career_is_in_kazakhstan(self):
        person = self.people["kaz-36fb8d2c335b"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Polymer Production")
        self.assertEqual(person["role"], "Financial Director")
        self.assertIn("Cornell University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Kazakhstan")
        self.assertNotEqual(location["country_code"], "US")

    def test_alexandr_shakiyev_remote_armeta_role_is_in_kazakhstan(self):
        person = self.people["kaz-0260225556fe"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Armeta")
        self.assertEqual(person["role"], "R&D and ML Engineer")
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Astana, Kazakhstan")
        self.assertEqual(
            location["evidence_kind"], "current_role_location"
        )

    def test_madi_baltagulov_profile_destination_and_two_degrees(self):
        person = self.people["kaz-c792c9bfcef4"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "NutraLens")
        self.assertEqual(person["role"], "Co-founder")
        self.assertEqual(
            person["linkedin_url"],
            "https://www.linkedin.com/in/madi-baltagulov-509bbb18b",
        )
        self.assertIn("Vanderbilt University", self.alma_maters(person["person_id"]))
        self.assertIn("Yale University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "US")
        self.assertEqual(
            location["location_label"],
            "New Haven, Connecticut, United States",
        )

    def test_nurislam_tursynbek_current_unc_role_and_actual_degrees(self):
        person = self.people["kaz-2732f0e135fa"]
        location = self.locations[person["person_id"]]
        alma_maters = self.alma_maters(person["person_id"])

        self.assertEqual(
            person["organization"], "University of North Carolina at Chapel Hill"
        )
        self.assertEqual(person["role"], "Graduate Student in Computer Science")
        self.assertIn("University of North Carolina at Chapel Hill", alma_maters)
        self.assertIn("Skoltech", alma_maters)
        self.assertIn("Nazarbayev University", alma_maters)
        self.assertEqual(location["country_code"], "US")
        self.assertEqual(
            location["location_label"],
            "Chapel Hill, North Carolina, United States",
        )

    def test_iliyas_kazymbek_current_spectrum_school_outcome(self):
        person = self.people["kaz-33b90013745b"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Spectrum International School")
        self.assertEqual(person["role"], "High School Student")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertEqual(
            person["linkedin_url"],
            "https://kz.linkedin.com/in/iliyas-kazymbek-77237a286",
        )
        self.assertIn("Ilyas Kazymbek", person["aliases"])
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Astana, Kazakhstan")

    def test_aizere_zhengiskhanova_current_nis_outcome(self):
        person = self.people["kaz-d0f8031edfa1"]
        location = self.locations[person["person_id"]]

        self.assertEqual(
            person["organization"], "Nazarbayev Intellectual Schools (NIS)"
        )
        self.assertEqual(person["role"], "High School Student")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertIn("Aizere Zheniskhanova", person["aliases"])
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(
            location["location_label"], "Ust-Kamenogorsk, Kazakhstan"
        )

    def test_damir_kurman_current_nis_outcome_and_profile(self):
        person = self.people["kaz-e9cd35b41255"]
        location = self.locations[person["person_id"]]

        self.assertEqual(
            person["organization"], "Nazarbayev Intellectual Schools (NIS)"
        )
        self.assertEqual(person["role"], "High School Student")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertEqual(
            person["linkedin_url"],
            "https://kz.linkedin.com/in/damir-kurman-7570372ab",
        )
        self.assertIn("Damir Kurmanov", person["aliases"])
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Astana, Kazakhstan")

    def test_2026_silver_medalists_have_sourced_school_destinations(self):
        expected = {
            "kaz-0a21069b5b5d": ("Nazarbayev Intellectual Schools (NIS)", "Astana, Kazakhstan"),
            "kaz-796f13ed0022": ("Nurorda School-Lyceum", "Almaty, Kazakhstan"),
            "kaz-a916225fee26": ("Bilim-Innovation Lyceums (BIL)", "Almaty, Kazakhstan"),
            "kaz-7dd0181a5ee2": ("Spectrum International School", "Astana, Kazakhstan"),
            "kaz-81ce5fa84827": ("Republican Physics and Mathematics School (RFMS)", "Kazakhstan"),
            "kaz-8e557ae5dc19": ("Lyceum No. 134", "Almaty, Kazakhstan"),
            "kaz-330d52d38c3b": ("Nazarbayev Intellectual Schools (NIS)", "Almaty, Kazakhstan"),
            "kaz-532ae28f1d07": ("Bilim-Innovation Lyceums (BIL)", "Pavlodar Region, Kazakhstan"),
        }

        for person_id, (organization, location_label) in expected.items():
            with self.subTest(person_id=person_id):
                person = self.people[person_id]
                location = self.locations[person_id]
                self.assertEqual(person["organization"], organization)
                self.assertEqual(person["role"], "High School Student")
                self.assertEqual(person["confidence"], "confirmed")
                self.assertEqual(location["country_code"], "KZ")
                self.assertEqual(location["location_label"], location_label)

        self.assertIn(
            "Yersultan Kaiyrken", self.people["kaz-532ae28f1d07"]["aliases"]
        )

    def test_older_gold_medalists_are_not_forced_to_namesakes(self):
        for person_id in ("kaz-dbcaf30d53de", "kaz-1e390288b2cc"):
            with self.subTest(person_id=person_id):
                person = self.people[person_id]
                self.assertEqual(person["confidence"], "unmatched")
                self.assertEqual(person["organization"], "")
                self.assertEqual(person["role"], "")

    def test_askar_amangeldy_singapore_coaching_and_both_degrees(self):
        person = self.people["kaz-7f627c03e4ca"]
        location = self.locations[person["person_id"]]

        self.assertEqual(
            person["organization"],
            "Singapore National Physics and Mathematics Olympiad Teams",
        )
        self.assertEqual(person["role"], "Physics and Mathematics Olympiad Coach")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertEqual(
            self.alma_maters(person["person_id"]),
            {
                "Nanyang Technological University (NTU)",
                "National University of Singapore",
            },
        )
        self.assertEqual(location["country_code"], "SG")
        self.assertEqual(location["location_label"], "Singapore")

    def test_adilet_turtemir_pittsburgh_phd_and_unist_bachelors(self):
        person = self.people["kaz-1f5957f35c2c"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["name"], "Adilet Turtemir")
        self.assertIn("Adlet Turtemir", person["aliases"])
        self.assertEqual(
            person["organization"], "University of Pittsburgh School of Medicine"
        )
        self.assertEqual(person["role"], "PhD Student in Molecular Pharmacology")
        self.assertEqual(
            person["linkedin_url"],
            "https://www.linkedin.com/in/adilet-turtemir-891b911b0/",
        )
        self.assertEqual(
            self.alma_maters(person["person_id"]),
            {
                "University of Pittsburgh School of Medicine",
                "Ulsan National Institute of Science and Technology (UNIST)",
            },
        )
        self.assertEqual(location["country_code"], "US")
        self.assertEqual(
            location["location_label"],
            "Pittsburgh, Pennsylvania, United States",
        )

    def test_nurdaulet_kemel_current_hong_kong_location(self):
        person = self.people["kaz-7bc4b3d48a29"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Undisclosed prop trading firm")
        self.assertEqual(person["role"], "Quantitative Researcher")
        self.assertEqual(
            person["linkedin_url"],
            "https://hk.linkedin.com/in/nurdauletkemel",
        )
        self.assertEqual(location["country_code"], "HK")
        self.assertEqual(location["country_name"], "Hong Kong")
        self.assertEqual(location["location_label"], "Hong Kong, Hong Kong SAR")

    def test_zhassulan_shaikhygali_indrive_and_unist(self):
        person = self.people["kaz-0e1075c1b53e"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "inDrive")
        self.assertEqual(person["role"], "Data Engineer")
        self.assertEqual(person["confidence"], "probable")
        self.assertEqual(person["profile_url"], "https://github.com/shaikhzhas")
        self.assertEqual(
            self.alma_maters(person["person_id"]),
            {"Ulsan National Institute of Science and Technology (UNIST)"},
        )
        self.assertEqual(location["country_code"], "KZ")

    def test_bekassyl_yelubay_current_nazarbayev_university_student(self):
        person = self.people["kaz-d2813a8e7e70"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Nazarbayev University")
        self.assertEqual(
            person["role"],
            "Undergraduate Student, School of Sciences and Humanities",
        )
        self.assertEqual(person["confidence"], "confirmed")
        self.assertIn("Nazarbayev University", self.alma_maters(person["person_id"]))
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Astana, Kazakhstan")

    def test_mansur_mamadakhunov_current_bil_student(self):
        person = self.people["kaz-ec0591e8ac95"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "Bilim-Innovation Lyceums (BIL)")
        self.assertEqual(person["role"], "High School Student")
        self.assertEqual(person["confidence"], "confirmed")
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Kyzylorda Region, Kazakhstan")

    def test_stale_school_records_remain_history_only(self):
        expected_alma_maters = {
            "kaz-618279226751": "Republican Physics and Mathematics School (RFMS)",
            "kaz-822bb4ee42e0": "Nazarbayev Intellectual Schools (NIS)",
            "kaz-eebfbe6a6de9": "Nazarbayev Intellectual Schools (NIS)",
            "kaz-6d8ff9e71d31": "Suleyman Demirel University (SDU)",
        }

        for person_id, alma_mater in expected_alma_maters.items():
            with self.subTest(person_id=person_id):
                person = self.people[person_id]
                self.assertEqual(person["confidence"], "unmatched")
                self.assertEqual(person["organization"], "")
                self.assertEqual(person["role"], "")
                self.assertIn(alma_mater, self.alma_maters(person_id))
                self.assertTrue(self.affiliations_for(person_id))

    def test_baurzhan_urgunshbayev_probable_metaphora_outcome(self):
        person = self.people["kaz-694369c06874"]
        location = self.locations[person["person_id"]]

        self.assertEqual(person["organization"], "METAPHORA")
        self.assertEqual(person["role"], "Technical Lead")
        self.assertEqual(person["confidence"], "probable")
        self.assertEqual(
            person["linkedin_url"],
            "https://kz.linkedin.com/in/baurzhan-urgunshbayev-143a68104",
        )
        self.assertIn("Urgunshbayev Baurzhan", person["aliases"])
        self.assertEqual(location["country_code"], "KZ")
        self.assertEqual(location["location_label"], "Almaty, Kazakhstan")


if __name__ == "__main__":
    unittest.main()
