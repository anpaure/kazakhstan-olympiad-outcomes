import unittest

from scripts.organization_names import (
    canonicalize_organization,
    display_organization,
    load_organization_aliases,
    organization_audit_key,
    organization_aliases_for,
)


class OrganizationNormalizationTest(unittest.TestCase):
    def test_corporate_subunits_merge_to_one_parent(self):
        self.assertEqual(canonicalize_organization("Amazon Web Services"), "Amazon")
        self.assertEqual(
            canonicalize_organization("AWS Center for Quantum Computing at Amazon"),
            "Amazon",
        )
        self.assertEqual(canonicalize_organization("Huawei Switzerland"), "Huawei")

    def test_acronym_language_and_typo_variants_merge(self):
        canonical = "Ulsan National Institute of Science and Technology (UNIST)"
        for value in [
            "UNIST",
            "울산과학기술원",
            "Ulsan National Insitute of Science and Technology",
        ]:
            with self.subTest(value=value):
                self.assertEqual(canonicalize_organization(value), canonical)
        self.assertEqual(display_organization(canonical), "UNIST")

    def test_distinct_similar_universities_do_not_merge(self):
        self.assertEqual(
            canonicalize_organization("Korea Institute of Science and Technology"),
            "Korea Institute of Science and Technology",
        )
        self.assertEqual(
            canonicalize_organization("University of California, Berkeley"),
            "University of California, Berkeley",
        )
        self.assertEqual(
            canonicalize_organization("University of Pennsylvania"),
            "University of Pennsylvania",
        )
        self.assertEqual(
            canonicalize_organization("Pennsylvania State University"),
            "Pennsylvania State University",
        )

    def test_aliases_remain_available_for_search(self):
        aliases = organization_aliases_for("Khan Group")
        self.assertIn("@khangroupkz", aliases)
        self.assertIn("Khan Group LLP", aliases)

    def test_common_university_aliases_merge(self):
        self.assertEqual(
            canonicalize_organization("UC Berkeley"),
            "University of California, Berkeley",
        )
        self.assertEqual(
            canonicalize_organization("University of Minnesota-Twin Cities"),
            "University of Minnesota",
        )

    def test_reviewed_organization_pass_merges_company_variants(self):
        expected = {
            "Google DeepMind": "Google",
            "Instagram": "Meta",
            "Microsoft Research": "Microsoft",
            "Schlumberger": "SLB",
            "Kcell АО": "Kcell",
            "AO Home Credit Bank Kazakhstan": "Home Credit Bank",
            "Bloomberg LP": "Bloomberg",
            "Kumtor Operating Company": "Kumtor Gold Company",
            "Kaspi Bank JSC": "Kaspi.kz",
            "Wand": "Wand AI",
            "Alem": "Alem Research",
            "Centerra Gold Inc": "Centerra Gold",
            "Platonus, LLP": "Platonus",
        }
        for value, canonical in expected.items():
            with self.subTest(value=value):
                self.assertEqual(canonicalize_organization(value), canonical)

    def test_reviewed_organization_pass_merges_institution_variants(self):
        expected = {
            "KBTU Kazakh British Technical University": (
                "Kazakh-British Technical University (KBTU)"
            ),
            "Università di Bologna": "Alma Mater Studiorum – Università di Bologna",
            "Rheinische Friedrich-Wilhelms-Universität Bonn": "University of Bonn",
            "North American University (NAU)": "North American University",
            "NWAFU": "Northwest A&F University",
            "元智大學": "Yuan Ze University",
            "Jacobs University Bremen": "Constructor University",
            "Barcelona Graduate School of Economics": (
                "Barcelona School of Economics (BSE)"
            ),
            "Harris School of Public Policy at the University of Chicago": (
                "University of Chicago"
            ),
            "Mechanobiology Institute": "National University of Singapore",
            "OIYaI": "Joint Institute for Nuclear Research",
            "Computing Center of RAS": "Dorodnitsyn Computing Centre",
            "SoftSec Lab": "Korea Advanced Institute of Science and Technology (KAIST)",
            "Statistical AI Lab": (
                "Ulsan National Institute of Science and Technology (UNIST)"
            ),
            "Hausdorff Center for Mathematics": "University of Bonn",
            "Tokyo Institute of Technology": "Institute of Science Tokyo",
            "University of Lille 1 Sciences and Technology": "University of Lille",
            "University of London International Programmes": "University of London",
            "Thompson Lab": "Princeton University",
            "Kazakh-Turkish High-School": "Kazakh-Turkish High School",
            "NURORDA High School": "Nurorda High School",
        }
        for value, canonical in expected.items():
            with self.subTest(value=value):
                self.assertEqual(canonicalize_organization(value), canonical)

    def test_alias_registry_has_no_conflicts(self):
        aliases, displays, reverse = load_organization_aliases()
        self.assertTrue(aliases)
        self.assertTrue(displays)
        self.assertTrue(reverse)

    def test_reviewed_display_names_are_compact(self):
        self.assertEqual(
            display_organization("Institute of Theoretical and Applied Mechanics"),
            "ITAM SB RAS",
        )
        self.assertEqual(
            display_organization(
                "National Research Nuclear University MEPhI "
                "(Moscow Engineering Physics Institute)"
            ),
            "MEPhI",
        )
        self.assertEqual(display_organization("The University of British Columbia"), "UBC")

    def test_audit_key_collapses_only_low_risk_surface_variants(self):
        self.assertEqual(
            organization_audit_key("Linkoping University, Inc."),
            organization_audit_key("Linköping University"),
        )
        self.assertNotEqual(
            organization_audit_key("University of California, Berkeley"),
            organization_audit_key("University of California, Davis"),
        )


if __name__ == "__main__":
    unittest.main()
