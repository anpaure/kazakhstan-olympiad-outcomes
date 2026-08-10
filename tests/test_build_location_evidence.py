import unittest

from scripts.build_location_evidence import country_from_location, extract_location


class LocationExtractionTest(unittest.TestCase):
    def test_public_profile_country_code_is_preferred(self):
        result = extract_location(
            "# Person CTO at Example Singapore (SG) 57 connections "
            "## Experience ### CTO - Example (Current) in Kazakhstan"
        )

        self.assertEqual(result["country_code"], "SG")
        self.assertEqual(result["evidence_kind"], "public_profile_location")
        self.assertEqual(result["confidence"], "confirmed")

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

    def test_city_only_current_role_location_uses_reviewed_city_map(self):
        self.assertEqual(country_from_location("Hillsboro, Oregon"), "US")
        self.assertEqual(country_from_location("Hwaseong"), "KR")

    def test_hungary_profile_location_is_supported(self):
        result = extract_location(
            "# Example Person\n\nStudent at Debreceni Egyetem\n\n"
            "Debrecen, Hajdú-Bihar, Hungary (HU)\n\n3 connections"
        )

        self.assertEqual(result["country_code"], "HU")
        self.assertEqual(result["country_name"], "Hungary")


if __name__ == "__main__":
    unittest.main()
