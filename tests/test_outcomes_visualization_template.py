import unittest
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "visualization" / "olympiad-outcomes-template.html"


class OrganizationSplitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_company_and_education_rankings_are_separate_and_scrollable(self):
        self.assertIn('data-chart="companies"', self.template)
        self.assertIn('data-chart="education"', self.template)
        self.assertIn('class="iso-ranked-scroll"', self.template)
        self.assertIn('overflow: auto', self.template)

    def test_company_ranking_uses_destination_and_education_uses_alma_maters(self):
        self.assertIn(
            "person.organizationType !== 'education' ? [person.organization] : []",
            self.template,
        )
        self.assertIn("...(person.almaMaters || []).map(alma => alma.organization)", self.template)
        self.assertIn("personHasOrganization(person, state.selectedOrganization)", self.template)
        self.assertNotIn('data-control="companies-only"', self.template)


class DistributionChartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_sector_and_country_pies_are_available(self):
        self.assertIn('data-control="sector"', self.template)
        self.assertIn('data-chart="sectors"', self.template)
        self.assertIn('data-chart="countries"', self.template)
        self.assertIn("drawDistribution('sectors', 'sector')", self.template)
        self.assertIn("drawDistribution('countries', 'country')", self.template)

    def test_rankings_and_pies_use_current_filtered_people(self):
        self.assertIn("filteredPeople({ ignoreSelection: true })", self.template)
        self.assertIn("state.sector !== 'all' && person.sector !== state.sector", self.template)
        self.assertIn("state.selectedOrganization", self.template)


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
        self.assertIn('data-sort-header="year"', self.template)
        self.assertIn('data-sort-header="destination"', self.template)

    def test_year_and_destination_sort_keys_are_explicit(self):
        self.assertIn("d3.ascending(a.firstYear, b.firstYear)", self.template)
        self.assertIn("d3.descending(a.lastYear, b.lastYear)", self.template)
        self.assertIn(
            "collator.compare(destinationKey(a.organization), destinationKey(b.organization))",
            self.template,
        )
        self.assertIn("`${person.firstYear}-${person.lastYear}`", self.template)

    def test_sortable_olympiad_header_stays_on_one_line(self):
        self.assertIn("#iso-outcomes-viz .iso-th-label", self.template)
        self.assertIn("white-space: nowrap", self.template)
        self.assertIn(
            "#iso-outcomes-viz .table th:nth-child(2) { width: 10%; }",
            self.template,
        )


class CountryAndHistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_country_filter_and_distribution_are_available(self):
        self.assertIn('data-control="country"', self.template)
        self.assertIn("person.countryCode !== state.country", self.template)
        self.assertIn('Outcome-country distribution', self.template)
        self.assertIn("kind === 'sector' ? person.sector : person.countryCode", self.template)

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
