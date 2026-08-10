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
7. Use `organization_aliases.csv` to audit every canonical-name merge and its
   rationale; the original source wording remains in `evidence_text`.
8. Use `organization_sectors.csv` to audit organization type and sector assignments.
9. Use `destination_reviews.csv` to inspect any source-level correction that filled or superseded the earlier displayed destination.

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
  usually follows public profile/role location, with reviewed overrides for
  stale profile headers; it is not legal residence or citizenship.
- `organization_aliases.csv`: reviewed alias-to-canonical mappings for legal
  names, acronyms, multilingual labels, campuses, and parent organizations.
- `organization_sectors.csv`: reviewed type and sector for every displayed
  non-educational destination.
- `destination_reviews.csv`: reviewed final organization, role, dates, direct
  source, review date, and rationale for every source-to-row reconciliation.
- `evidence.csv`: one row per person-source-claim relationship. This is the main
  audit ledger.
- `sources.csv`: one row per deduplicated URL with usage and review-status
  counts.
- `rejections.csv`: explicit reviewed rejection decisions and reasons.
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

- `exa_linkedin_review_queue.csv`: all 325 exact-name profile results and their
  deterministic review and outcome statuses.
- `exa_outcome_integrations.csv`: 55 accepted career updates with direct
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
python scripts/validate_research.py
```
