# Revalidation: September 7, 2026

## Scope

The figures below describe the initial pass. The follow-up at the end records
subsequent corrections and the final checked export.

- All 457 people and 684 participations passed structural, identity, chronology,
  country, organization, and source-ledger checks.
- All 684 participations matched fresh archive extraction by Olympiad, year,
  and name after name-order normalization. Image-only legacy IBO records still
  use the prior audited transcriptions, not a new visual transcription.
- All 302 accepted LinkedIn URLs were attempted through Exa. Content returned
  for 288; 14 failed. Exa responses can be cached or internally inconsistent.
- 285 refreshed profiles were integrated. Three conflicting or incomplete
  responses and the 14 failures retain earlier reviewed evidence. The original
  and retrieved text hashes and decisions are in `profile_revalidation.csv`.
- All 1,772 evidence URLs received a reachability classification. LinkedIn URLs
  use the separate Exa audit. HTTP success alone does not verify a claim.
- A deterministic sample of 12 non-LinkedIn profiles was inspected. Results and
  limitations are in `../revalidation/2026-09-07/non_linkedin_sample.csv`.

## Corrections

Ten destination reviews were added or updated:

| Person | Corrected destination or role |
| --- | --- |
| Nurgali Arystanov | KazAID, Chairman of the Board; Astana replaces the former Seoul embassy outcome |
| Birzhan Muldagaliyev | AgroCredit Corporation, ML Team Lead; current role is in Astana |
| Madi Baltagulov | Yale, Program Administrator and Data Engineer; NutraLens remains searchable history |
| Azamat Smagulov | Vacuumlabs, Senior Software Engineer; Slovakia is explicitly last known, since the role ended in August 2026 |
| Roman Cheremnov | Ecole Polytechnique, Mathematics and Physics undergraduate; replaces the ended tournament role |
| Aiganym Baltashova | MIT undergraduate transfer; the degree section supplies 2026-2029 |
| Galymzhan Baktybai | KAIST Biological Sciences undergraduate; chemical engineering is a minor |
| Tamirlan Seidakhmetov | Meta, Data Science Manager |
| Renat Bekbolatov | Genie, Founder and Lead Engineer |
| Rassul Karabalin | Amazon, Tech Lead in Processor Fabrication and Quantum Computing |

Additional corrections and protections:

- All four IOI 2026 rank denominators now use the official 375, not 386.
- IChO 2010: Ilya Skripin is rank 104, and Zhalgas Serimbetov is rank 121,
  following the official archive rather than Scoreboard's 105 and 122.
- Short summer programs no longer become alma maters. Student outreach jobs
  and the Clinton leadership initiative do not imply a degree. Dean's-list
  honors do not turn a genuine education record into employment.
- IBO parsing no longer turns document headings into people, duplicates comma
  variants, includes country/gender tokens in names, or uses the 2016 ID as rank.
- The retired IOI live fallback cannot silently count guests. A future live
  extraction requires an explicit verified eligible-user list.
- Zhomart's concurrent AGI Lab and Khan Group CEO roles are explicitly recorded
  and tested; they no longer depend on a particular wording in review notes.
- Nineteen confirmed dead public URLs were suppressed. Audit evidence retains
  the original URLs. No new person/source hyperlink was added to the page.
- Unknown countries remain unknown: 43 people have no published outcome country.

## Remaining Limits

The source check found 839 readable HTML responses, 84 PDF responses, 449
LinkedIn URLs routed to Exa review, 230 responses with insufficient extracted
content, 70 access restrictions, 51 other HTTP errors, 21 network failures,
11 missing URLs, and 17 soft errors. Some government pages expose only a
JavaScript shell to direct requests; indexed article text was checked for the
sampled school announcements. Scoreboard returned HTTP 502, so comparison used
the official IBO/IChO archives without overwriting the more detailed prior scores.

The following failed exact-profile attempts were not presented as fresh
verification: Abylay Kabdulkhadyr, Adilet Uvaliyev, Aigerim Shamshidin, Akhmet
Issa, Akhyn Zhagsalag, Alibek Aldangarov, Asset Mussagaliyev, Bakdaulet Yernazarov,
Demeu Shakhanov, Doszhan Bissimbi, Iliyas Kazymbek, Nurbakyt Madibek, Nursultan
Erkinovich Tompiyev, and Zhan Dautov.

Yuriy Ten's retrieved education dates conflict with reviewed school/university
chronology; Vladislav Cherdantsev's new unnamed employer does not establish a
job change; Shapagat Berdibek's response omits the earlier education section.
All three alternate responses are preserved rather than silently promoted.

The non-LinkedIn sample includes unavailable Galaxy and IBS pages and a partly
revalidated historical Baiken-U record. An admissions list proves admission,
not matriculation; a 2024 report does not independently prove 2026 enrollment.
No missing end date, new employer, degree completion, or residence was invented.

## Reproducible Checks

Run `python -m unittest discover -s tests -q`,
`python scripts/validate_research.py`, and
`python scripts/validate_artifacts.py` after rebuilding/exporting.
The independent artifact check compares 27 CSV/JSON pairs, all 253,751 cells
in the 13 workbook data sheets, workbook summary counts, and all 457 embedded
public records. The raw retrieval and per-record comparison files are in
`../revalidation/2026-09-07/`.

Final run: 363 unit tests passed. Browser checks passed at 1440px and 390px in
English, Russian, and Kazakh, covering five sort toggles, historical-employer
search, updated profiles, concurrent CEO roles, empty results, and unknown
countries. Country-chart counts sum to the 414 known-country records. No page
overflow, clipped chart counts/legends, or JavaScript exceptions were detected.
The published link set contains no additions. Publishable files and workbook
XML were scanned for local home paths and embedded API-key assignments.

## Follow-up Review

- Aldiyar Seitbay: an August 2026 interview reports Astana IT University
  enrollment after Bilim-Innovation Astana. The destination is Student, with
  probable confidence in the audit. No degree level or graduation date is
  inferred. The interview's competition-date claims do not replace official
  IOI results.
- Sanzhar Bidaibek: HKUST's 2018-2019 roster explicitly identifies first-year
  Engineering study. This now supplies alma-mater attendance. Graduation,
  current employment, and current country remain unestablished.
- Removed Sanzhar's sports-club-based country override. The existing guard
  already excluded it from the public page; deleting the input also prevents
  its later reuse as career-location evidence.

The per-person decisions, sources, and root causes are recorded in
`../revalidation/2026-09-07/followup_review.json`. The updated dataset has
448 accepted identities, 413 resolved destinations, and 42 unknown countries.
No person or source hyperlinks were added to the public page.
All three newly used evidence URLs returned readable responses; their separate
reachability results are in `../revalidation/2026-09-07/followup_source_health.json`.

Final checks: 371 tests passed; all 27 CSV/JSON pairs, 253,995 workbook data
cells, summary counts, and 457 embedded public records agree. Browser checks
passed at desktop and mobile widths in all three languages, including the
two changed profiles, five sort toggles, and chart/filter counts.

The privacy check inspected 138 publishable files and 2,157 reachable Git
blobs, commits, and tags, including workbook XML. It found no local home paths
or common embedded credential formats. An additional scan found no owner
username or space-separated name in the publishable files. All reachable
commit authors and committers use the anpaure GitHub noreply identity. These
checks do not establish that every possible secret format is absent or remove
copies held elsewhere.

Repeat the publishable-file check with
`python scripts/check_publishable_privacy.py`; add `--history` to inspect
reachable Git history as well. Reports omit matching secret text.

## Final Follow-up

The additional search audit is in
`../revalidation/2026-09-07/missing_outcomes_followup.json`: 32 searches for
missing outcomes, four exact-profile retrieval attempts, and one targeted
Akezhan search. It records result URLs, text hashes, and decisions. Search
results alone did not establish any new identity.

- Zhaslan Baraissov: Cornell's Center for Bright Beams explicitly announces
  his PhD graduation and lists his next role as Scientist at KLA. The alumni
  row links the already accepted LinkedIn profile. The 2019-2026 Cornell PhD
  remains in alma-mater history alongside NTU; no KLA start date is inferred.
  United States is explicitly last known from Cornell in 2026, not an inferred
  KLA office or a claim about current residence.
- Akezhan Askar: a new exact-name LinkedIn snippet mentions two IOI silver
  medals and Nanyang Technological University Singapore, class of 2030.
  Exact-profile retrieval returned `ENTITY_NOT_FOUND`. The follow-up search
  still returned only a snippet, so enrollment dates, degree, and residence
  remain unverified. The lead is retained without adding a public link.
- Three newly inspected namesakes were rejected for incompatible school or
  university chronology. These are included in the rejection ledger and
  workbook, not just discarded from the search response.

Root cause: refreshing LinkedIn and ORCID can reproduce a stale student role.
Explicit university graduation and subsequent-employment evidence must take
precedence. A new regression check prevents a reviewed degree completion from
remaining active in older open-ended records, while preserving later degrees,
other institutions, and university employment. The history-preservation
validator now uses the same case-insensitive role comparison as deduplication.

UI review also found that the mobile stacked table hid every sorting control
with its header. The same five header controls are now visible above the mobile
list; the removed top-level sorting dropdown has not returned.

The final dataset retains 457 people, 684 participations, 448 accepted
identities, 413 resolved destinations, and 42 unknown countries. There are
still eight unmatched identities, one candidate identity, and 44 people without
a selected destination. Absence of evidence is not treated as Kazakhstan
residence, continued study, or a current job.

All four newly checked institutional/company URLs returned readable responses;
see `../revalidation/2026-09-07/late_source_health.json`. The public page has
1,159 person/source URLs, with no additions. The former Cornell visitor link
was removed because it no longer supports a current-student location.

Verification: 376 unit tests and full dataset validation passed. Browser checks
exercised every sort in both directions at 1440px and 390px in English,
Russian, and Kazakh, plus historical-job search, changed profiles, unknown
countries, empty results, and chart totals. No page overflow, clipped chart
counts/legends, or JavaScript exceptions were detected. Test traffic did not
reach Google Analytics.
The independent export comparison passed for all 27 CSV/JSON pairs, 254,285
workbook data cells across 13 sheets, summary totals, and 457 embedded page
records.

The additional privacy scan found no local home paths or common credential
patterns in publishable files or 2,192 reachable Git objects, including workbook
XML. A separate current-file scan found no owner account name. As above, this
is not proof that every possible secret format is absent.
