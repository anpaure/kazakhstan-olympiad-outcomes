# ISO Futures

Collect Kazakhstan participant lists for major International Science Olympiads, canonicalize repeat competitors, and research their later companies, roles, and universities from structured public sources.

The pipeline does not crawl LinkedIn or drive a browser across profiles. LinkedIn URLs are retained only when a public structured source or a manually reviewed result exposes one.

[Explore the interactive visualization](https://anpaure.github.io/kazakhstan-olympiad-outcomes/) or [download the audit workbook](https://anpaure.github.io/kazakhstan-olympiad-outcomes/kazakhstan_olympiad_outcomes_audit.xlsx).

## Current Snapshot

The checked-in data currently contains:

- 680 olympiad participation rows: 204 IMO, 112 IOI, 123 IPhO, 125 IBO, and 116 IChO
- 457 canonical people after 29 reviewed name merges
- 304 researched people, all classified as probable or confirmed
- 252 confirmed and 52 probable education or career outcomes
- 272 manually reviewed outcomes backed by public evidence
- 285 researched people with a resolved organization and 227 with a public LinkedIn URL
- 3 additional people with candidate-only evidence retained for audit but no accepted outcome
- 112 rejected identity sources retained with review reasons and supporting links

The current first step is implemented in `scripts/collect_kazakhstan_participants.py`. It collects Kazakhstan competitors from:

- IMO: official IMO country individual results
- IOI: IOI statistics results
- IPhO: IPhO individual country results
- IChO: Scoreboard JSON for recent years plus official IChO country results for older backfill
- IBO: Scoreboard JSON plus the official IBO result-report archive for historical and recent PDF backfill

Exa is used as the source-discovery/audit layer when `EXA_API_KEY` is set. The collector still uses curated result URLs for parsing so the participant list is deterministic.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Collect Kazakhstan Participants

```bash
EXA_API_KEY=your_key_here python scripts/collect_kazakhstan_participants.py --use-exa
```

Without Exa, including the PDF backfill needed to reproduce the checked-in IBO coverage:

```bash
python scripts/collect_kazakhstan_participants.py --include-ibo-pdfs
```

Outputs:

- `data/kazakhstan_participants.csv`
- `data/kazakhstan_participants.json`
- `data/exa_source_hits.json` when `--use-exa` and `EXA_API_KEY` are provided
- `data/cache/` cached source pages and PDFs

Useful options:

```bash
python scripts/collect_kazakhstan_participants.py --skip-ibo
python scripts/collect_kazakhstan_participants.py --include-ibo-pdfs
python scripts/collect_kazakhstan_participants.py --refresh
python scripts/collect_kazakhstan_participants.py --olympiads IMO IOI IPhO IChO
```

The CSV is the seed file for the research pipeline below.

The IBO parser handles changing country/name layouts, compact country codes, joined rank fields, uppercase names, and single-letter medal markers. A small audited fallback table covers six legacy image-only or surname-only reports (1994, 1995, 1996, 1998, 1999, and 2009). Kazakhstan has no IBO participant row for 2004 in the official archive.

## Build the People Registry

```bash
python scripts/build_people_registry.py
```

This merges repeat appearances, reviewed transliteration variants, and reversed name forms into one row per person. It also assigns a research scope so recent school-age competitors are not treated as established career profiles.

Outputs:

- `data/people.csv`
- `data/people.json`
- `data/people_merge_audit.json`

## Research Structured Public Sources

```bash
gh auth status
python scripts/enrich_structured_sources.py \
  --sources codeforces cphof github orcid openalex wikidata \
  --scopes career early_career_or_university
```

Adapters use:

- Codeforces public profiles for handles, names, organizations, and competitive-programming context
- CPHOF olympiad profiles for contestant identity, awards, education, employment, and linked Codeforces handles
- GitHub GraphQL user search through the authenticated `gh` CLI
- ORCID public search and records for education and employment affiliations
- OpenAlex author records and linked ORCID identities
- Batched Wikidata entity and claim lookup for notable people, occupations, employers, and education

Name-only matches remain `candidate`. Contextual Kazakhstan, olympiad, timeline, profile-link, and cross-source signals are needed for `probable` or `confirmed` confidence. Wikidata name matches are deliberately excluded from cross-source confidence boosts because common-name collisions are frequent. Requests are cached under `data/cache/enrichment/`, so interrupted or rate-limited runs can resume. If OpenAlex exhausts its anonymous daily allowance, the run skips only uncached people and still replays all later cached records; rerun later or set `OPENALEX_API_KEY` to fill the remaining gaps.

Outputs:

- `data/identity_candidates.csv` and `.json`
- `data/affiliation_candidates.csv` and `.json`
- `data/enrichment_audit.json`

## Assemble and Validate Outcomes

```bash
python scripts/apply_exa_identity_rejections.py
python scripts/apply_exa_outcome_integrations.py
python scripts/build_research_dataset.py
python scripts/build_audit_bundle.py
python scripts/validate_research.py
```

`data/verified_evidence.csv` contains reviewed public evidence and overrides lower-confidence inferred affiliations. `data/rejected_identity_candidates.csv` records reviewed false or unsupported namesakes by person and evidence URL; the assembler excludes those identities and their derived affiliations while allowing a different future source for the same person to surface.

The two apply scripts merge the auditable Exa review overlays before assembly. `data/exa_outcome_integrations.csv` records accepted career updates with their direct evidence URLs, while `data/exa_identity_rejections.csv` records newly identified namesakes. Both merges reject duplicate overlay keys and are safe to rerun. `data/exa_identity_review_decisions.csv` and `data/exa_outcome_review_decisions.csv` retain explicit reasons and supporting links for profiles that are supporting, deferred, rejected, or intentionally not used as the current outcome.

`scripts/build_audit_bundle.py` then creates normalized audit tables under `data/audit/`. The final people table joins to a row-level evidence ledger through `person_id`; evidence joins to a deduplicated source registry through `source_id`; every evidence row retains its direct `source_url`. Accepted, supporting, candidate, superseded, and rejected claims remain visible instead of being collapsed into one compound URL field. See `data/audit/README.md` for the audit procedure and data dictionary.

The validation step checks participant-row conservation, unique person IDs, confidence/evidence rules, timeline conflicts, recent-competitor exclusions, exact publication of every accepted Exa outcome overlay, preservation of manual evidence, rejection-ledger leakage, audit-table joins, direct HTTP(S) source links, and complete traceability for every probable or confirmed outcome.

Outputs:

- `data/researched_people.csv`
- `data/researched_people.json`
- `data/audit/people.csv` and `.json`
- `data/audit/participations.csv` and `.json`
- `data/audit/evidence.csv` and `.json`
- `data/audit/sources.csv` and `.json`
- `data/audit/rejections.csv` and `.json`
- `data/audit/manifest.json`

## Build the Visualization

```bash
python scripts/build_outcomes_visualization.py
```

The generator embeds `data/researched_people.json` into `docs/index.html`, the GitHub Pages site. Use `--template` and `--out` to target another visualization workspace.

## Optional LinkedIn Search Audit

For targeted LinkedIn discovery through Exa, provide the key only through the
process environment:

```bash
export EXA_API_KEY
python scripts/search_linkedin_with_exa.py --limit 20
```

The command defaults to unresolved and probable career-scope people. Use repeated
`--person-id` or `--name` flags for a reviewed cohort, and `--refresh` to replace an
existing query. To cover the complete canonical registry, run:

```bash
python scripts/search_linkedin_with_exa.py --all
```

`--all` resumes completed IDs and searches only people absent from the existing
audit; use `--retry-errors` to retry failed checkpoints. It never writes the API
key. Each checkpoint preserves the person ID, exact query, Exa request ID, request
cost, result rank, public URL, result type, name-match flag, and returned
highlights. The JSON also records input count, searched count, successful and
failed counts, and coverage percentage.

Current Exa audit coverage: 457 of 457 canonical people, 457 successful searches,
zero errors, and 2,285 ranked result rows. Total recorded API cost is $3.199.

Outputs:

- `data/exa_linkedin_search_audit.json`: nested request and result evidence
- `data/exa_linkedin_search_audit.csv`: one flat row per ranked result

Build the deterministic manual-review queue after a search run:

```bash
python scripts/build_exa_review_queue.py
```

The queue joins the current research status to exact-name LinkedIn profiles and
separately flags the expected Olympiad, participant-year overlap, award language,
and current-affiliation language. Its priority score orders unresolved explicit
identity bridges first without treating a name match alone as proof. Every row has
a deterministic `review_status` of `selected`, `supporting`, `deferred`, or `rejected`, matched
against the accepted evidence and rejection ledger after LinkedIn URL
canonicalization. The current queue contains 106 people with an explicit
expected-Olympiad bridge; none remain unmatched or probable, and none need an
outcome decision. Across all 326 exact-name profile results, 200 are selected, 5
are supporting duplicate profiles, 31 are explicitly deferred with review reasons,
and 90 are rejected. No result remains silently unreviewed.

Review-queue outputs:

- `data/exa_linkedin_review_queue.json`: summary plus complete candidate rows
- `data/exa_linkedin_review_queue.csv`: flat sortable review table

The older no-key helper remains available:

```bash
python scripts/search_linkedin_candidates.py
```

This legacy helper reads `data/kazakhstan_participants.csv`, deduplicates repeated competitors, and attempts public `site:linkedin.com/in` result discovery. It does not scrape LinkedIn profile pages or use browser automation. The structured-source pipeline above is the primary workflow.

The default `bing-rss` engine is a no-key fallback. Public search engines may block or ignore automated `site:` queries, so `data/linkedin_search_audit.json` is the source of truth for what was attempted.

Outputs:

- `data/linkedin_candidates.csv`
- `data/linkedin_candidates.json`
- `data/linkedin_search_audit.json`
- `data/linkedin_search_audit.csv`
- `data/cache/linkedin_search/` cached search responses

Useful options:

```bash
python scripts/search_linkedin_candidates.py --max-people 25
python scripts/search_linkedin_candidates.py --include-directory
python scripts/search_linkedin_candidates.py --refresh --sleep 1
```
