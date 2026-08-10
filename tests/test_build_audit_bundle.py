import unittest

from scripts.build_audit_bundle import build_audit_organization_aliases, build_bundle


class AuditBundleTest(unittest.TestCase):
    def test_organization_alias_audit_preserves_normalization_source(self):
        rows = build_audit_organization_aliases(
            [
                {
                    "alias": "Example Lab",
                    "canonical_name": "Example University",
                    "display_name": "Example University",
                    "merge_type": "parent_organization",
                    "rationale": "University laboratory",
                    "evidence_url": "https://example.test/lab",
                }
            ]
        )

        self.assertEqual(rows[0]["evidence_url"], "https://example.test/lab")

    def test_final_outcome_traces_to_sources_and_rejection_stays_rejected(self):
        person_id = "kaz-test"
        participants = [
            {
                "olympiad": "IBO",
                "country": "Kazakhstan",
                "country_code": "KAZ",
                "year": "2003",
                "name": "Person Test",
                "award": "Bronze",
                "rank": "",
                "score": "",
                "person_url": "",
                "source_url": "https://example.test/ibo-2003.pdf",
                "source_type": "pdf",
            }
        ]
        people = [
            {
                "person_id": person_id,
                "canonical_name": "Test Person",
                "aliases": "Person Test;Test Person",
            }
        ]
        researched = [
            {
                "person_id": person_id,
                "name": "Test Person",
                "aliases": "Person Test;Test Person",
                "olympiads": "IBO",
                "years": "2003",
                "awards": "Bronze",
                "research_scope": "career",
                "confidence": "probable",
                "organization": "Example University",
                "role": "Researcher",
                "affiliation_type": "employment",
                "start_year": "2020",
                "end_year": "",
                "country_code": "US",
                "organization_category": "Academia",
                "role_category": "Research & Academia",
                "profile_url": "https://example.test/good-profile",
                "linkedin_url": "",
                "verification_basis": "Exact-name profile with a coherent timeline",
            }
        ]
        identities = [
            {
                "person_id": person_id,
                "source": "orcid",
                "source_id": "good",
                "profile_url": "https://example.test/good-profile",
                "evidence_url": "https://example.test/good-profile",
                "matched_name": "Test Person",
                "confidence": "probable",
                "score_reasons": "exact_name;country_context",
                "organization": "Example University",
                "role": "Researcher",
                "evidence_text": "Verified profile",
            },
            {
                "person_id": person_id,
                "source": "orcid",
                "source_id": "bad",
                "profile_url": "https://example.test/bad-profile",
                "evidence_url": "https://example.test/bad-profile",
                "matched_name": "Test Person",
                "confidence": "candidate",
                "score_reasons": "exact_name",
                "organization": "Wrong University",
                "role": "Researcher",
                "evidence_text": "Name only",
            },
        ]
        affiliations = [
            {
                "person_id": person_id,
                "source": "orcid",
                "evidence_url": "https://example.test/good-profile",
                "confidence": "probable",
                "organization": "Example University",
                "role": "Researcher",
                "affiliation_type": "employment",
                "evidence_text": "Example University",
            },
            {
                "person_id": person_id,
                "source": "orcid",
                "evidence_url": "https://example.test/bad-profile",
                "confidence": "candidate",
                "organization": "Wrong University",
                "role": "Researcher",
                "affiliation_type": "employment",
                "evidence_text": "Wrong University",
            },
        ]
        rejections = [
            {
                "person_id": person_id,
                "evidence_url": "https://example.test/bad-profile",
                "reason": "Name-only collision",
                "review_evidence_url": "https://example.test/bad-profile",
            }
        ]

        bundle = build_bundle(
            participants,
            people,
            researched,
            identities,
            affiliations,
            [],
            rejections,
        )

        [audit_person] = bundle["people"]
        self.assertEqual(audit_person["traceability_status"], "complete")
        self.assertEqual(audit_person["participation_evidence_count"], 1)
        self.assertEqual(audit_person["outcome_evidence_count"], 2)

        participation = bundle["participations"][0]
        evidence_by_id = {row["evidence_id"]: row for row in bundle["evidence"]}
        self.assertEqual(
            evidence_by_id[participation["evidence_id"]]["source_url"],
            "https://example.test/ibo-2003.pdf",
        )

        good_rows = [
            row
            for row in bundle["evidence"]
            if row["source_url"] == "https://example.test/good-profile"
        ]
        self.assertTrue(all(row["review_status"] == "accepted" for row in good_rows))
        self.assertTrue(all(row["supports_final_outcome"] for row in good_rows))

        bad_rows = [
            row
            for row in bundle["evidence"]
            if row["source_url"] == "https://example.test/bad-profile"
        ]
        self.assertTrue(all(row["review_status"] == "rejected" for row in bad_rows))
        self.assertTrue(all(not row["supports_final_outcome"] for row in bad_rows))

        source_urls = {row["source_url"] for row in bundle["sources"]}
        self.assertEqual(
            source_urls,
            {
                "https://example.test/ibo-2003.pdf",
                "https://example.test/good-profile",
                "https://example.test/bad-profile",
            },
        )
        self.assertEqual(bundle["rejections"][0]["reason"], "Name-only collision")


if __name__ == "__main__":
    unittest.main()
