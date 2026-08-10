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


if __name__ == "__main__":
    unittest.main()
