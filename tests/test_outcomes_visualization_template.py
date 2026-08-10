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


class DestinationExpansionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_destination_chart_has_an_accessible_expand_control(self):
        self.assertIn('data-control="destination-expand"', self.template)
        self.assertIn('aria-expanded="false"', self.template)
        self.assertIn("const collapsedDestinationCount = 12", self.template)
        self.assertIn("const expandedDestinationCount = 30", self.template)

    def test_expansion_uses_the_current_filtered_destination_data(self):
        self.assertIn("const allData = allDestinationData()", self.template)
        self.assertIn("const data = allData.slice(0, limit)", self.template)
        self.assertIn(
            "state.destinationsExpanded = !state.destinationsExpanded", self.template
        )


class PeopleSortTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_people_table_exposes_year_and_destination_sorts(self):
        self.assertIn('data-control="sort"', self.template)
        self.assertIn('value="year-asc"', self.template)
        self.assertIn('value="year-desc"', self.template)
        self.assertIn('value="destination-asc"', self.template)
        self.assertIn('value="destination-desc"', self.template)

    def test_year_and_destination_sort_keys_are_explicit(self):
        self.assertIn("d3.ascending(a.firstYear, b.firstYear)", self.template)
        self.assertIn("d3.descending(a.lastYear, b.lastYear)", self.template)
        self.assertIn(
            "collator.compare(destinationKey(a.organization), destinationKey(b.organization))",
            self.template,
        )
        self.assertIn("`${person.firstYear}-${person.lastYear}`", self.template)


class CountryAndHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_country_filter_and_ranking_are_available(self):
        self.assertIn('data-control="country"', self.template)
        self.assertIn('value="country"', self.template)
        self.assertIn("person.countryCode !== state.country", self.template)
        self.assertIn("country: 'Current countries'", self.template)

    def test_search_includes_alma_mater_and_history(self):
        self.assertIn("person.almaMater", self.template)
        self.assertIn("...(person.historyTerms || [])", self.template)
        self.assertIn("<th>Alma mater</th>", self.template)


class SourceAndConfidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_sources_are_compact_accessible_icon_links(self):
        self.assertIn("lucide@0.468.0", self.template)
        self.assertIn("className = 'iso-source-link'", self.template)
        self.assertIn("anchor.setAttribute('aria-label', source.label)", self.template)
        self.assertIn("icon.setAttribute('data-lucide', source.icon)", self.template)

    def test_confidence_uses_an_accessible_color_dot(self):
        self.assertIn("className = 'iso-confidence-dot'", self.template)
        self.assertIn("Confidence: ${person.confidence}", self.template)
        self.assertNotIn("confidenceCell.textContent = person.confidence", self.template)


if __name__ == "__main__":
    unittest.main()
