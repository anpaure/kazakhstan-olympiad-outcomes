import unittest

from scripts.organization_sectors import (
    load_organization_sectors,
    organization_metadata,
)


class OrganizationSectorTest(unittest.TestCase):
    def test_alias_uses_canonical_company_sector(self):
        metadata = organization_metadata("Amazon Web Services", "Industry")

        self.assertEqual(metadata["canonical_name"], "Amazon")
        self.assertEqual(metadata["organization_type"], "company")
        self.assertEqual(metadata["sector"], "Technology & Software")

    def test_education_category_does_not_require_registry_row(self):
        metadata = organization_metadata("University of Example", "Academia")

        self.assertEqual(metadata["organization_type"], "education")
        self.assertEqual(metadata["sector"], "Education & Research")

    def test_registry_is_nonempty_and_complete(self):
        metadata = load_organization_sectors()

        self.assertGreater(len(metadata), 100)
        self.assertTrue(all(row["rationale"] for row in metadata.values()))


if __name__ == "__main__":
    unittest.main()
