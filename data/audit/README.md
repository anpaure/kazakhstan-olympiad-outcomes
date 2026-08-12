# Audit Bundle

This directory is the audit-facing view of the research dataset. Every table is
flat, every row has a stable key, and every evidence row includes the direct
source URL used for review.

## Audit a Person

1. Find the person in `people.csv` and copy `person_id`.
2. Filter `evidence.csv` by that `person_id`.
3. Open the `source_url` values on rows marked `accepted` or `supporting`.
4. Confirm at least one `olympiad_participation` row and one row where
   `supports_final_outcome` is `True`.
5. Review any `candidate`, `superseded`, or `rejected` rows for contrary or
   discarded matches.
6. Filter `affiliations.csv` for sourced past jobs, schools, and the selected
   alma maters; filter `locations.csv` for the sourced outcome-country claim.
7. Use `organization_aliases.csv` to audit every canonical-name merge, its
   rationale, and the direct `evidence_url` for nontrivial entity relationships;
   the original source wording remains in `evidence_text`.
8. Use `organization_sectors.csv` to audit organization type and sector assignments.
9. Use `destination_reviews.csv` to inspect any source-level correction that filled or superseded the earlier displayed destination.
10. Use `profile_sanity_review.csv` for the reproducible 48-person review sample,
    including separate links for participation, identity, destination, location,
    and alma-mater claims.
11. Use `linkedin_destination_reconciliation.csv` to compare all 298 accepted
    profiles with the published single destination; conflicts must have an
    explicit review decision and direct reference URL.
12. Use `profile_sanity_review_findings.csv` to inspect the detected downstream
    causes, corrections, and regression guards.

## Tables

- `people.csv`: one final outcome per canonical person, plus evidence counts and
  a traceability status.
- `participations.csv`: one row per Olympiad appearance, joined to `person_id`
  and its evidence record.
- `affiliations.csv`: accepted employment and education history. Every row
  joins to evidence/source IDs; each distinct higher-education institution has
  `selected_as_alma_mater=true`, with one secondary-school fallback only when
  no higher education is known.
- `locations.csv`: one sourced outcome-country claim per covered person. It
  follows the explicit location of the selected current role; active students
  use the sourced campus country in the parent `organization_locations.csv`
  registry. A profile header may corroborate the role but is never accepted by
  itself, and a conflicting header is discarded. It is not legal residence or
  citizenship.
- `organization_aliases.csv`: reviewed alias-to-canonical mappings for legal
  names, acronyms, multilingual labels, campuses, and parent organizations;
  source-backed parent, former-name, and successor mappings include a direct
  `evidence_url`.
- `organization_sectors.csv`: reviewed type and sector for every displayed
  non-educational destination.
- `destination_reviews.csv`: reviewed final organization, role, dates, direct
  source, review date, and rationale for every source-to-row reconciliation.
- `evidence.csv`: one row per person-source-claim relationship. This is the main
  audit ledger.
- `sources.csv`: one row per deduplicated URL with usage and review-status
  counts.
- `rejections.csv`: explicit reviewed rejection decisions and reasons.
- `profile_sanity_review.csv`: deterministic, stratified 48-person manual review
  with field-level checks and direct source columns.
- `linkedin_destination_reconciliation.csv`: one row per accepted LinkedIn
  profile, its parsed current affiliations, published destination, and any
  required source-precedence decision.
- `profile_sanity_review_findings.csv`: root-cause ledger linking each detected
  issue to its correction, prevention rule, and evidence URLs.
- `profile_sanity_review_manifest.json`: sample seed/method, cohort counts,
  reconciliation totals, and unresolved counts.
- `manifest.json`: schema version, keys, joins, status vocabulary, and row
  counts.

JSON equivalents are generated beside every CSV table.

## Review Statuses

- `accepted`: selected evidence supporting an official participation or final
  identity, education, or career outcome.
- `supporting`: useful corroboration, such as a reviewed public profile.
- `candidate`: automatically discovered but not selected as final evidence.
- `superseded`: an automated candidate or earlier manual summary replaced by
  stronger source-level review.
- `rejected`: explicitly reviewed and excluded from final outcomes.

`traceability_status=complete` means a probable or confirmed person has both
accepted participation evidence and accepted or supporting outcome evidence.

## Exa Review Trail

The complete exact-name LinkedIn review trail remains in the parent `data/`
directory rather than being flattened into the final-outcome tables:

- `exa_linkedin_review_queue.csv`: all 358 exact-name profile results and their
  deterministic review and outcome statuses.
- `exa_outcome_integrations.csv`: 104 accepted career updates with direct
  Olympiad and career evidence links.
- `exa_identity_review_decisions.csv`: supporting, deferred, and rejected
  decisions for secondary profiles, each with a reason and review link.
- `exa_identity_rejections.csv`: namesakes promoted into the rejection ledger.
- `exa_outcome_review_decisions.csv`: explicit reasons for retaining a
  published outcome when an Exa profile exposes stale or conflicting current
  roles.

## Regenerate

```bash
python scripts/apply_exa_identity_rejections.py
python scripts/apply_exa_outcome_integrations.py
python scripts/build_research_dataset.py
python scripts/hydrate_linkedin_profiles_with_exa.py
python scripts/build_affiliation_history.py
python scripts/build_location_evidence.py
python scripts/build_audit_bundle.py
python scripts/build_profile_sanity_review.py
python scripts/validate_research.py
```
