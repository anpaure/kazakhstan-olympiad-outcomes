import unittest

from scripts.build_audit_bundle import (
    build_audit_people,
    build_audit_organization_aliases,
    build_bundle,
    build_evidence,
)


class AuditBundleTest(unittest.TestCase):
    def test_structured_identity_only_evidence_is_not_an_outcome(self):
        person_id = "kaz-structured"
        final = {
            "person_id": person_id,
            "name": "Structured Person",
            "aliases": "Structured Person",
            "olympiads": "IOI",
            "years": "2001",
            "awards": "",
            "research_scope": "career",
            "confidence": "confirmed",
            "destination_status": "none",
            "destination_note": "No reviewed destination is available.",
            "organization": "",
            "role": "",
            "affiliation_type": "",
            "start_year": "",
            "end_year": "",
            "country_code": "",
            "organization_category": "Unknown",
            "role_category": "Other",
            "profile_url": "https://cphof.org/profile/ioi:test",
            "linkedin_url": "",
            "evidence_urls": "https://cphof.org/profile/ioi:test",
            "verification_basis": "Registry-linked profile.",
        }
        participation = {
            "participation_id": "part-structured",
            "evidence_id": "",
            "person_id": person_id,
            "canonical_name": "Structured Person",
            "recorded_name": "Structured Person",
            "olympiad": "IOI",
            "country": "Kazakhstan",
            "country_code": "KAZ",
            "year": "2001",
            "award": "",
            "rank": "",
            "score": "",
            "person_url": "https://stats.ioinformatics.org/people/test",
            "source_url": "https://stats.ioinformatics.org/people/test",
            "source_type": "html",
        }
        identity = {
            "person_id": person_id,
            "canonical_name": "Structured Person",
            "matched_name": "Structured Person",
            "source": "cphof",
            "source_id": "ioi:test",
            "profile_url": "https://cphof.org/profile/ioi:test",
            "evidence_url": "https://cphof.org/profile/ioi:test",
            "organization": "",
            "role": "",
            "confidence": "confirmed",
            "evidence_text": "Registry-linked profile.",
            "score_reasons": "profile=ioi:test",
        }

        evidence = build_evidence([participation], [final], [identity], [], [], [])
        identity_row = next(
            row for row in evidence if row["claim_type"] == "identity_candidate"
        )
        self.assertEqual(identity_row["review_status"], "accepted")
        self.assertFalse(identity_row["supports_final_outcome"])

        [audit_person] = build_audit_people([final], [], evidence)
        self.assertEqual(audit_person["traceability_status"], "identity_verified")
        self.assertEqual(audit_person["outcome_evidence_count"], 0)

    def test_identity_only_manual_evidence_has_no_career_claim(self):
        person_id = "kaz-test"
        final = {
            "person_id": person_id,
            "name": "Test Person",
            "aliases": "Test Person",
            "olympiads": "IOI",
            "years": "2025",
            "awards": "Silver",
            "research_scope": "recent_competitor",
            "confidence": "confirmed",
            "destination_status": "none",
            "destination_note": "No reviewed destination is available.",
            "organization": "",
            "role": "",
            "affiliation_type": "",
            "start_year": "",
            "end_year": "",
            "country_code": "",
            "organization_category": "Unknown",
            "role_category": "Other",
            "profile_url": "https://example.test/identity",
            "linkedin_url": "https://linkedin.com/in/test-person",
            "evidence_urls": "https://example.test/identity",
            "verification_basis": "Reviewed school-to-Olympiad identity bridge.",
        }
        verified = {
            "person_id": person_id,
            "name": "Test Person",
            "organization": "",
            "role": "",
            "affiliation_type": "",
            "start_year": "",
            "end_year": "",
            "olympiad_evidence_url": "https://example.test/olympiad",
            "career_evidence_url": "https://example.test/identity",
            "linkedin_url": "https://linkedin.com/in/test-person",
            "confidence": "confirmed",
            "verification_basis": "Reviewed school-to-Olympiad identity bridge.",
        }

        participations = [
            {
                "participation_id": "part-test",
                "evidence_id": "",
                "person_id": person_id,
                "canonical_name": "Test Person",
                "recorded_name": "Test Person",
                "olympiad": "IOI",
                "country": "Kazakhstan",
                "country_code": "KAZ",
                "year": "2025",
                "award": "Silver",
                "rank": "",
                "score": "",
                "person_url": "https://example.test/olympiad",
                "source_url": "https://example.test/olympiad",
                "source_type": "html",
            }
        ]
        evidence = build_evidence(
            participations, [final], [], [], [verified], []
        )

        self.assertNotIn("career_outcome", {row["claim_type"] for row in evidence})
        identity = next(
            row for row in evidence if row["claim_type"] == "olympiad_identity_bridge"
        )
        self.assertEqual(identity["source_url"], "https://example.test/identity")
        self.assertEqual(
            identity["secondary_url"], "https://example.test/olympiad"
        )
        self.assertFalse(identity["supports_final_outcome"])
        public_profile = next(
            row for row in evidence if row["claim_type"] == "public_profile"
        )
        self.assertFalse(public_profile["supports_final_outcome"])

        [audit_person] = build_audit_people([final], [verified], evidence)
        self.assertEqual(audit_person["traceability_status"], "identity_verified")
        self.assertEqual(audit_person["outcome_evidence_count"], 0)

    def test_destination_review_supersedes_only_old_career_claim(self):
        person_id = "kaz-test"
        final = {
            "person_id": person_id,
            "name": "Test Person",
            "profile_url": "https://example.test/current",
            "linkedin_url": "https://linkedin.com/in/test",
            "evidence_urls": ";".join(
                [
                    "https://example.test/olympiad",
                    "https://example.test/old-career",
                    "https://example.test/current",
                ]
            ),
        }
        verified = {
            "person_id": person_id,
            "name": "Test Person",
            "organization": "Old Co",
            "role": "Analyst",
            "affiliation_type": "employment",
            "start_year": "2020",
            "end_year": "2024",
            "olympiad_evidence_url": "https://example.test/olympiad",
            "career_evidence_url": "https://example.test/old-career",
            "linkedin_url": "https://linkedin.com/in/test",
            "confidence": "confirmed",
            "verification_basis": "Reviewed identity and former role.",
        }
        review = {
            "person_id": person_id,
            "organization": "Current Co",
            "role": "Engineer",
            "affiliation_type": "employment",
            "start_year": "2025",
            "end_year": "",
        }
        identities = [
            {
                "person_id": person_id,
                "source": "orcid",
                "source_id": "namesake",
                "profile_url": "https://example.test/namesake",
                "evidence_url": "https://example.test/namesake",
                "matched_name": "Test Person",
                "confidence": "candidate",
                "score_reasons": "exact_name;ambiguous_same_name_source",
                "organization": "Wrong University",
                "role": "Researcher",
                "evidence_text": "Name-only candidate.",
            }
        ]

        evidence = build_evidence(
            [], [final], identities, [], [verified], [], [review]
        )
        by_type = {row["claim_type"]: row for row in evidence}

        self.assertEqual(by_type["olympiad_identity_bridge"]["review_status"], "accepted")
        self.assertTrue(by_type["olympiad_identity_bridge"]["supports_final_outcome"])
        self.assertEqual(by_type["career_outcome"]["review_status"], "superseded")
        self.assertFalse(by_type["career_outcome"]["supports_final_outcome"])
        self.assertEqual(by_type["identity_candidate"]["review_status"], "candidate")
        self.assertFalse(by_type["identity_candidate"]["supports_final_outcome"])

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
        self.assertEqual(bundle["manifest"]["counts"]["resolved_destinations"], 1)
        self.assertEqual(bundle["manifest"]["counts"]["verified_identities"], 1)
        self.assertEqual(bundle["manifest"]["counts"]["confirmed_identities"], 0)
        self.assertEqual(bundle["manifest"]["counts"]["probable_identities"], 1)
        self.assertEqual(bundle["manifest"]["counts"]["identity_only_people"], 0)
        self.assertEqual(bundle["manifest"]["counts"]["candidate_only_people"], 0)
        self.assertEqual(bundle["manifest"]["counts"]["unmatched_people"], 0)


if __name__ == "__main__":
    unittest.main()
