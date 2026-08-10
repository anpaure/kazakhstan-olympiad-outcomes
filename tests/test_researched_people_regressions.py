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


if __name__ == "__main__":
    unittest.main()
