import unittest

from scripts.collect_kazakhstan_participants import (
    extract_ibo_links,
    parse_ibo_pdf,
    parse_ibo_row,
    parse_imo,
    parse_ioi,
    parse_ioi_live_scoreboard,
)


class IboArchiveParsingTest(unittest.TestCase):
    def test_heading_is_not_a_participant(self):
        self.assertIsNone(parse_ibo_row(["Ranking of IBO 2024 in Astana, Kazachstan"], "https://example.test/results.pdf", 2024))

    def test_2016_final_rank_is_not_the_leading_identifier(self):
        row = parse_ibo_row(["117 30C Kazakhstan Mr. Otarbayev Daniyar Male 57,03 Bronze 83"], "https://example.test/2016.pdf", 2016)
        self.assertEqual((row.name, row.rank, row.award), ("Otarbayev Daniyar", "83", "Bronze"))

    def test_older_final_rank_is_not_the_leading_identifier(self):
        for year in [2002, 2003, 2004, 2006]:
            with self.subTest(year=year):
                result = parse_ibo_row(["342 Kazakhstan Example Student 25.27 55 Silver"], "https://example.test/results.pdf", year)
                self.assertEqual(result.rank, "55")

    def test_country_code_and_separate_name_columns(self):
        cases = [
            (2010, "90 KAZ- 2704 Talap KOSSYBAKOV 53.511 Bronze", "Talap Kossybakov", "90", "Bronze"),
            (2013, "35 silver Nurislam Yeshenkulov KAZ Kazakhstan 31,4", "Nurislam Yeshenkulov", "35", "Silver"),
            (2014, "61SILVER Kazakhstan KAZ01 KAZ 01 Askarbek ORAKOV 35.5", "Askarbek Orakov", "61", "Silver"),
            (2019, "105 B Kazahstan Adlet Turtemir 53 50", "Adlet Turtemir", "105", "Bronze"),
        ]
        for year, line, name, rank, award in cases:
            with self.subTest(year=year):
                result = parse_ibo_row([line], "https://example.test/result.pdf", year)
                self.assertEqual((result.name, result.rank, result.award), (name, rank, award))

    def test_table_and_text_names_have_identical_punctuation(self):
        a = parse_ibo_row(["Bronze", "KAZAKHSTAN", "TAIMANOV, ADAM"], "https://example.test/2020.pdf", 2020)
        b = parse_ibo_row(["Bronze KAZAKHSTAN TAIMANOV, ADAM"], "https://example.test/2020.pdf", 2020)
        self.assertEqual(a.name, b.name)

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

    def test_live_scoreboard_fills_archive_lag_with_medals(self):
        teams = {"KAZ": {"name": "Kazakhstan"}, "USA": {"name": "United States"}}
        users = {
            "KAZ1": {"f_name": "Gold", "l_name": "Person", "team": "KAZ"},
            "KAZ2": {"f_name": "Silver", "l_name": "Person", "team": "KAZ"},
        }
        scores = {
            "KAZ1": {"day1": 100, "day2": 100},
            "KAZ2": {"day1": 80, "day2": 80},
        }
        for index, total in enumerate((190, 180), start=20):
            user_id = f"USA{index}"
            users[user_id] = {"f_name": "Other", "l_name": str(index), "team": "USA"}
            scores[user_id] = {"contest": total}
        for index, total in enumerate(range(159, 148, -1), start=1):
            user_id = f"USA{index}"
            users[user_id] = {"f_name": "Other", "l_name": str(index), "team": "USA"}
            scores[user_id] = {"contest": total}

        participants = parse_ioi_live_scoreboard(
            2026,
            "https://stats.example/results/KAZ",
            teams,
            users,
            scores,
            eligible_user_ids=set(users),
        )

        self.assertEqual(
            [(row.name, row.award, row.rank, row.score) for row in participants],
            [
                ("Gold Person", "Gold", "1/15", "200"),
                ("Silver Person", "Silver", "4/15", "160"),
            ],
        )
        self.assertEqual(participants[1].person_url, "")
        self.assertEqual(
            participants[1].source_url,
            "https://stats.example/results/KAZ",
        )
        self.assertEqual(participants[1].source_type, "scoreboard")

    def test_unverified_live_population_cannot_supply_awards(self):
        with self.assertRaises(ValueError):
            parse_ioi_live_scoreboard(2026, "https://example.test/", {}, {}, {})

    def test_guests_are_excluded_from_live_rank_denominator(self):
        teams = {"KAZ": {"name": "Kazakhstan"}, "GUEST": {"name": "Guest"}}
        users = {"KAZ1": {"f_name": "Test", "l_name": "Person", "team": "KAZ"}, "X": {"team": "GUEST"}}
        rows = parse_ioi_live_scoreboard(2026, "https://example.test/", teams, users,
                                        {"KAZ1": {"score": 5}, "X": {"score": 10}}, {"KAZ1"})
        self.assertEqual(rows[0].rank, "1/1")


if __name__ == "__main__":
    unittest.main()
