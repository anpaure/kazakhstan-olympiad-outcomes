import unittest
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "visualization" / "olympiad-outcomes-template.html"


class OrganizationTypeFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_companies_only_control_is_an_accessible_toggle(self):
        self.assertIn('data-control="companies-only"', self.template)
        self.assertIn('aria-pressed="false"', self.template)
        self.assertIn('aria-label="Show companies only"', self.template)
        self.assertIn('Companies only', self.template)

    def test_companies_only_excludes_non_industry_organizations(self):
        self.assertIn(
            "state.companiesOnly && person.organizationCategory !== 'Industry'",
            self.template,
        )
        self.assertIn(
            "controls.companiesOnly.setAttribute('aria-pressed', String(state.companiesOnly))",
            self.template,
        )


if __name__ == "__main__":
    unittest.main()
