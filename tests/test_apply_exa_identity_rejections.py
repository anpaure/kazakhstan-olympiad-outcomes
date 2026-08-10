import unittest

from scripts.apply_exa_identity_rejections import merge_rows


class ExaIdentityRejectionTest(unittest.TestCase):
    def test_adds_only_new_person_url_pairs(self):
        base = [
            {
                "person_id": "kaz-1",
                "evidence_url": "https://example.test/profile/",
            }
        ]
        additions = [
            {"person_id": "kaz-1", "evidence_url": "https://example.test/profile"},
            {"person_id": "kaz-2", "evidence_url": "https://example.test/other"},
        ]

        merged, added = merge_rows(base, additions)

        self.assertEqual(added, 1)
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
