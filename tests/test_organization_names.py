import unittest

from scripts.organization_names import (
    canonicalize_organization,
    display_organization,
    load_organization_aliases,
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

    def test_aliases_remain_available_for_search(self):
        aliases = organization_aliases_for("Khan Group")
        self.assertIn("@khangroupkz", aliases)
        self.assertIn("Khan Group LLP", aliases)

    def test_alias_registry_has_no_conflicts(self):
        aliases, displays, reverse = load_organization_aliases()
        self.assertTrue(aliases)
        self.assertTrue(displays)
        self.assertTrue(reverse)


if __name__ == "__main__":
    unittest.main()
