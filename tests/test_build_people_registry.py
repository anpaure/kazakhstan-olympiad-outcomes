import unittest

from scripts.build_people_registry import build_registry, token_key


class StablePersonIdTest(unittest.TestCase):
    def test_reuses_id_when_source_reorders_name(self):
        rows = [
            {
                "olympiad": "IPhO",
                "year": "2009",
                "name": "Vyacheslav Li",
                "award": "Silver Medal",
                "source_url": "https://example.test/results",
            }
        ]
        people, _ = build_registry(
            rows,
            {token_key("Li Vyacheslav"): "kaz-existing"},
        )
        self.assertEqual(people[0].person_id, "kaz-existing")

    def test_uses_verified_given_name_order_for_nurdaulet_kemel(self):
        rows = [
            {
                "olympiad": "IPhO",
                "year": "2018",
                "name": "Kemel Nurdaulet",
                "award": "Bronze Medal",
                "source_url": "https://example.test/results",
            }
        ]
        people, _ = build_registry(rows)
        self.assertEqual(people[0].canonical_name, "Nurdaulet Kemel")
        self.assertEqual(people[0].aliases, "Kemel Nurdaulet")

    def test_reviewed_merge_can_cross_olympiads_and_preserve_id(self):
        rows = [
            {
                "olympiad": "IMO",
                "year": "2016",
                "name": "Temirlan Amangeldin",
                "award": "Bronze medal",
                "source_url": "https://example.test/imo",
            },
            {
                "olympiad": "IPhO",
                "year": "2017",
                "name": "Temirlan Amangeldinov",
                "award": "Silver Medal",
                "source_url": "https://example.test/ipho",
            },
        ]
        reviewed = [
            {
                "canonical_person_id": "kaz-reviewed",
                "canonical_name": "Temirlan Amangeldinov",
                "aliases": ("Temirlan Amangeldin", "Temirlan Amangeldinov"),
                "reason": "Same sourced profile and education timeline.",
                "evidence_url": "https://linkedin.com/in/example",
            }
        ]

        people, merge_audit = build_registry(
            rows,
            {
                token_key("Temirlan Amangeldin"): "kaz-old-1",
                token_key("Temirlan Amangeldinov"): "kaz-old-2",
            },
            reviewed,
        )

        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].person_id, "kaz-reviewed")
        self.assertEqual(people[0].canonical_name, "Temirlan Amangeldinov")
        self.assertEqual(people[0].olympiads, "IMO;IPhO")
        self.assertEqual(merge_audit[-1]["reason"], "reviewed_cross_olympiad_merge")


if __name__ == "__main__":
    unittest.main()
