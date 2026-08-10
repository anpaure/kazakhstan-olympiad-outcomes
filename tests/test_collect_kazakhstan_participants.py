import unittest

from scripts.collect_kazakhstan_participants import (
    extract_ibo_links,
    parse_ibo_pdf,
    parse_ibo_row,
    parse_imo,
    parse_ioi,
)


class IboArchiveParsingTest(unittest.TestCase):
    def test_site_root_relative_pdf_link(self):
        html = '<a href="files/downloads/results-reports/results/IBO2005.pdf">IBO 2005</a>'
        self.assertEqual(
            extract_ibo_links(html, "https://www.ibo-info.org/en/info/results-reports.html"),
            [
                (
                    2005,
                    "IBO 2005",
                    "https://www.ibo-info.org/files/downloads/results-reports/results/IBO2005.pdf",
                )
            ],
        )

    def test_recent_kaz_code_and_award(self):
        participant = parse_ibo_row(
            [
                "44 KAZ-S4 Alikhan Ashirkhanov Kazakhstan Silver "
                "64 +0.52 63.7 +0.64"
            ],
            "https://example.test/2026.pdf",
            2026,
        )
        self.assertIsNotNone(participant)
        self.assertEqual(participant.name, "Alikhan Ashirkhanov")
        self.assertEqual(participant.award, "Silver")

    def test_country_joined_to_rank(self):
        participant = parse_ibo_row(
            ["100KAZAKHSTAN Yersultan Kairken 47,5 0,101 Bronze"],
            "https://example.test/2025.pdf",
            2025,
        )
        self.assertIsNotNone(participant)
        self.assertEqual(participant.name, "Yersultan Kairken")
        self.assertEqual(participant.award, "Bronze")

    def test_country_before_and_after_name_layouts(self):
        before = parse_ibo_row(
            ["342 KAZAKHSTAN MUKASHEV Maxim 25,27 26 55 SILVER"],
            "https://example.test/2006.pdf",
            2006,
        )
        after = parse_ibo_row(
            ["79 Dudnik Alexey Kazakhstan 47 30,5 26 79 Bronze"],
            "https://example.test/2003.pdf",
            2003,
        )
        self.assertEqual(before.name, "Mukashev Maxim")
        self.assertEqual(after.name, "Dudnik Alexey")

    def test_single_letter_bronze_marker(self):
        participant = parse_ibo_row(
            ["127 Zhanat Koshenov 16 53 2.5 Kazakhstan B"],
            "https://example.test/2008.pdf",
            2008,
        )
        self.assertEqual(participant.name, "Zhanat Koshenov")
        self.assertEqual(participant.award, "Bronze")

    def test_image_only_legacy_rows_are_audited(self):
        participants = parse_ibo_pdf(b"", "https://example.test/1996.pdf", 1996)
        self.assertEqual(
            [(participant.name, participant.award) for participant in participants],
            [
                ("Saken Serhanov", "Gold"),
                ("Nurbol Sihimbayev", "Gold"),
                ("Azamat Abilkhanov", "Bronze"),
            ],
        )


class ImoResultsParsingTest(unittest.TestCase):
    def test_embedded_country_results_json(self):
        html = """
        <script type="application/json" data-results-individual-country-contestants>
        [{"year":"2026","contestantId":36189,"name":"Batyrkhan","surname":"Beiganov",
          "total":28,"rank":56,"award":"silver","slug":"36189"}]
        </script>
        """
        participants = parse_imo(
            html,
            "https://www.imo-official.org/results/individual/country/KAZ/",
        )
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants[0].name, "Batyrkhan Beiganov")
        self.assertEqual(participants[0].award, "Silver medal")
        self.assertEqual(participants[0].rank, "56")
        self.assertEqual(participants[0].score, "28")
        self.assertEqual(
            participants[0].person_url,
            "https://www.imo-official.org/results/contestant/36189/",
        )


class IoiResultsParsingTest(unittest.TestCase):
    def test_person_link_is_resolved_from_site_root(self):
        html = """
        <table>
          <thead>
            <tr><th>Year</th><th>Contestant</th><th>Country</th><th>Score</th><th>Rank</th><th>Award</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><a href="olympiads/2000">2000</a></td>
              <td><a href="people/1516">Example Contestant</a></td>
              <td>Kazakhstan</td><td>100</td><td>10</td><td>Silver</td>
            </tr>
          </tbody>
        </table>
        """

        participants = parse_ioi(
            html,
            "https://stats.ioinformatics.org/results/KAZ",
        )

        self.assertEqual(len(participants), 1)
        self.assertEqual(
            participants[0].person_url,
            "https://stats.ioinformatics.org/people/1516",
        )


if __name__ == "__main__":
    unittest.main()
