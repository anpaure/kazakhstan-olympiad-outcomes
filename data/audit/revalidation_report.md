# Revalidation: September 7, 2026

## Scope

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
