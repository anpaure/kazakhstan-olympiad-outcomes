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

## Tables

- `people.csv`: one final outcome per canonical person, plus evidence counts and
  a traceability status.
- `participations.csv`: one row per Olympiad appearance, joined to `person_id`
  and its evidence record.
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
- `superseded`: an automated candidate replaced by stronger manual evidence.
- `rejected`: explicitly reviewed and excluded from final outcomes.

`traceability_status=complete` means a probable or confirmed person has both
accepted participation evidence and accepted or supporting outcome evidence.

## Regenerate

```bash
python scripts/build_audit_bundle.py
python scripts/validate_research.py
```
