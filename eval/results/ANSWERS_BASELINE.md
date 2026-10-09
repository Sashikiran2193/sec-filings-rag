# Answer baseline

Full pipeline (`answer()`: hybrid retrieval, 8 chunks, `claude-opus-5-5` at
medium effort) on the 47-question test set, run 2026-10-09 at commit
`f71e267` plus `answer()` returning the raw answer. 47 calls, about 4 minutes,
about $1.45.

| Measure | Baseline |
|---|---|
| **Answer accuracy** (correct, of 41 answerable) | **90.2%** (37) |
| **Citation correctness** (numbers in cited claims found in the cited chunk) | **100%** (179 of 179) |
| **Correct refusals** (no-answer questions declined) | **100%** (6 of 6) |
| False refusals (answerable questions declined) | 7.3% (3 of 41) |
| Answers with figures on uncited lines | 8 of 38 answered |

## Accuracy by question type

| Type | Questions | Correct | Partly correct | Wrong | Accuracy |
|---|---|---|---|---|---|
| Fact | 25 | 21 | 0 | 4 | 84.0% |
| Summary | 8 | 8 | 0 | 0 | 100.0% |
| Comparison | 8 | 8 | 0 | 0 | 100.0% |
| **Overall** | **41** | **37** | **0** | **4** | **90.2%** |

## The four wrong answers: all retrieval, none made up

| Question | What happened |
|---|---|
| F15 Snowflake headcount | Said the total wasn't in its excerpts and gave three functions' headcounts instead (correctly added). The total (9,060) wasn't retrieved. |
| F16 Rivian headcount | "Not found in the filings." The headcount chunk ranks below 20th. |
| F18 AMD's CEO | "Not found in the filings." AMD's signature page wasn't retrieved. |
| F25 Apple headcount | "Not found in the filings." Apple's Item 1 headcount chunk wasn't retrieved. |

These are the same questions the retrieval baseline flagged (F18, F25 missed;
F15, F16 right section but wrong chunk). No answer stated a wrong fact: when
the chunk wasn't there, the model declined or said what was missing.

## How each measure was checked

- **Grades** (`answer_grades_baseline.jsonl`): every answer read against the
  verified expected answer, by hand, with a note per question. Correct = all
  key facts right and nothing wrong added; partly correct = some key facts
  missing or a minor error; wrong = the answer is missing or incorrect.
- **Citations** (`citation_check_baseline.json`, from
  `eval/check_citations.py`): every number in a cited claim was matched against
  the chunks that claim cites, allowing unit changes and rounding. All 179
  matched. Claims without numbers were spot-checked by hand (12 checked, such
  as Huang's biography, Ford's Saarlouis plant and AWS's 18% share of net
  sales); all were in the cited chunks.
- **Uncited figures:** 8 answers have figures on lines without their own
  citation: sub-bullets under a cited line (F03, F06, S03), an opening summary
  that repeats figures cited below (C01, C08), or the model's own arithmetic
  (F15, C02, C07). Every one was checked and is correct and drawn from the
  retrieved chunks, but a reader can't trace them from the answer alone.
- **Refusals:** an answer counts as declined when it starts with "Not found in
  the filings".

## Caveats

- **One grader, first pass.** The grades are mine; a second reader could
  differ on borderline cases (S05 uses the FY2024 wording "substantially all"
  where FY2025 says "a significant majority"; graded correct because both are
  in the cited chunks).
- **Small sets.** 41 answerable and 6 no-answer questions, so one question is
  2.4 points of accuracy. The no-answer questions are clear-cut; harder ones
  (a figure for a year just outside the filings, say) would test refusals more.
- **One run.** Model output varies between runs; the numbers could move a
  point or two on a re-run.

Files: `answers_baseline.jsonl` (every answer, raw citations, retrieved and
cited chunks), `answer_grades_baseline.jsonl`, `citation_check_baseline.json`,
`answer_scores_baseline.json`. Reproduce with `python eval/run_answers.py`,
`python eval/check_citations.py`, then `python eval/score_answers.py` once
the grades file exists.
