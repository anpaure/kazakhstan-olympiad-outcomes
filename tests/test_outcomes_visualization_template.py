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
        self.assertIn("historical_latest_known_location", self.template)
        self.assertIn("last known", self.template)
        self.assertIn('Country distribution', self.template)
        self.assertIn("kind === 'sector' ? person.sector : person.countryCode", self.template)
        self.assertIn("Boolean(person.countryCode)", self.template)

    def test_search_includes_alma_mater_and_history(self):
        self.assertIn("person.almaMater", self.template)
        self.assertIn("...(person.historyTerms || [])", self.template)
        self.assertIn('<th data-i18n="almaMater">Alma mater</th>', self.template)


class SourceDisplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_sources_are_compact_accessible_icon_links(self):
        self.assertIn("lucide@0.468.0", self.template)
        self.assertIn("className = 'iso-source-link'", self.template)
        self.assertIn("const sourceLabel = translatedSourceLabel(source.label)", self.template)
        self.assertIn("anchor.setAttribute('aria-label', sourceLabel)", self.template)
        self.assertIn("icon.setAttribute('data-lucide', source.icon)", self.template)

    def test_confidence_is_not_exposed_in_the_public_interface(self):
        self.assertNotIn('data-control="confidence"', self.template)
        self.assertNotIn("iso-confidence-dot", self.template)
        self.assertNotIn('data-chart="coverage"', self.template)
        self.assertNotIn('value="confidence"', self.template)


class LocalizationAndShareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_english_russian_and_kazakh_are_selectable(self):
        self.assertIn('data-language="en"', self.template)
        self.assertIn('data-language="ru"', self.template)
        self.assertIn('data-language="kk"', self.template)
        self.assertIn("const translations = {", self.template)
        self.assertIn("ru: {", self.template)
        self.assertIn("kk: {", self.template)

    def test_language_updates_dynamic_content_and_persists(self):
        self.assertIn("function applyLanguage(language, persist = true)", self.template)
        self.assertIn("document.documentElement.lang = currentLanguage", self.template)
        self.assertIn("localStorage.setItem('iso-outcomes-language', currentLanguage)", self.template)
        self.assertIn("url.searchParams.set('lang', currentLanguage)", self.template)
        self.assertIn("new Intl.DisplayNames", self.template)
        self.assertIn("const countryLabels = {", self.template)
        self.assertIn("countryLabels[currentLanguage]?.[code]", self.template)
        self.assertIn("translatedSector(person.sector)", self.template)
        self.assertIn("translatedSourceLabel(source.label)", self.template)

    def test_share_uses_native_api_with_clipboard_fallback(self):
        self.assertIn("data-share", self.template)
        self.assertIn('aria-live="polite" data-share-status', self.template)
        self.assertIn("await navigator.share(shareData)", self.template)
        self.assertIn("navigator.clipboard?.writeText", self.template)
        self.assertIn("document.execCommand('copy')", self.template)
        self.assertIn("controls.share.addEventListener('click', sharePage)", self.template)


class AnalyticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_ga4_loads_immediately_with_advertising_signals_disabled(self):
        self.assertIn(
            'https://www.googletagmanager.com/gtag/js?id=G-GPDVHJ29G6',
            self.template,
        )
        self.assertIn("gtag('config', 'G-GPDVHJ29G6'", self.template)
        self.assertIn("allow_google_signals: false", self.template)
        self.assertIn("allow_ad_personalization_signals: false", self.template)
        self.assertNotIn("gtag('consent'", self.template)

    def test_custom_events_cover_the_primary_interactions(self):
        for event_name in (
            "visualization_ready",
            "filter_change",
            "sort_change",
            "search_used",
            "language_change",
            "organization_filter",
            "chart_filter",
            "profile_open",
            "source_open",
            "resource_open",
            "page_share",
        ):
            self.assertIn(f"trackAnalyticsEvent('{event_name}'", self.template)

    def test_custom_events_do_not_send_search_text_names_or_urls(self):
        self.assertIn(
            "trackAnalyticsEvent('search_used', { results_count: filteredPeople().length })",
            self.template,
        )
        self.assertIn(
            "trackAnalyticsEvent('source_open', { source_kind: source.kind })",
            self.template,
        )
        self.assertNotIn("search_term:", self.template)
        self.assertNotIn("person_name:", self.template)
        self.assertNotIn("source_url:", self.template)


class IntroCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE.read_text(encoding="utf-8")

    def test_summary_number_cards_are_removed(self):
        self.assertNotIn('class="viz-grid iso-summary"', self.template)
        self.assertNotIn('data-stat="canonical"', self.template)
        self.assertNotIn("canonicalAlumni", self.template)

    def test_data_quality_disclaimer_is_localized(self):
        self.assertIn('data-i18n="dataDisclaimer"', self.template)
        self.assertIn("Public-source research may be incomplete", self.template)
        self.assertIn("Данные из открытых источников могут быть неполными", self.template)
        self.assertIn("мәліметтер толық емес", self.template)


if __name__ == "__main__":
    unittest.main()
