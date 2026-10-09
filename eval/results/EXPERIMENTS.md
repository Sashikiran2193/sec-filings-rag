# Experiments

Each row changes one thing and re-runs the full evaluation on the 47-question
test set: retrieval (`measure_retrieval.py`), answers (`run_answers.py`),
citations (`check_citations.py`), hand grades and scores (`score_answers.py`).

| # | Change | Hit rate (top 5) | Answer text retrieved (top 8) | Accuracy (of 41) | Cited numbers supported | No-answer declined | False refusals | Kept? |
|---|---|---|---|---|---|---|---|---|
| 0 | Baseline | 95.1% | 85.4% | 90.2% (37) | 100% (172/172) | 6/6 | 3 (F16, F18, F25) | — |
| 1 | Start a new chunk at sub-headings | **97.6%** | **95.1%** | **95.1% (39)** | 99.4% (174/175) | 6/6 (4 in the exact wording) | **1 (F18)** | Yes |

Accuracy by type, baseline → experiment 1: fact 84.0% → **96.0%**, summary
100% → 100%, comparison 100% → **87.5%**.

## Experiment 1: start a new chunk at sub-headings

**Why.** The four wrong baseline answers broke down as 3 bad chunking, 1 bad
retrieval, 0 bad generation:

| Question | Cause | Evidence |
|---|---|---|
| F15 Snowflake headcount | Chunking | The headcount sat 1,400 characters into a chunk that began with competitive-factor bullets; vector rank 14, keyword 32 |
| F16 Rivian headcount | Chunking | At the end of a chunk about supply-chain sourcing and sustainability; vector rank 60 |
| F25 Apple headcount | Chunking | In the middle of a chunk that began with net-sales seasonality; vector rank 23 |
| F18 AMD's CEO | Retrieval | A clean, self-contained signature page that vector search ranks below 60th |

The chunker broke text only by size, so a short section such as "Human
Capital" was tacked onto the end of the previous topic, and the chunk's
embedding was dominated by that other text.

**Change.** `chunk_10k.py` now ends a chunk at a sub-heading line (short, no
ending punctuation, not a table row: "Human Capital", "Reportable Segments")
once the chunk has at least 100 new tokens, and carries no overlap across the
heading. Everything else is unchanged. Chunks went from 5,682 to 7,116, with a
median of 334 tokens instead of 393.

**Effect.**

- Fixed: F15, F16, F25. Each headcount chunk now starts at its "Human
  Capital" heading, and all three answers give the exact figure.
- Broke: C03 (Ford vs GM vs Tesla headcount). Ford's employment table became
  its own small chunk and ranked 4th for Ford; a three-company question gives
  each company 3 chunks, so it was left out and the answer couldn't name
  Ford's headcount.
- Still wrong: F18 (AMD's CEO), the one retrieval failure; this change wasn't
  aimed at it.
- Refusals: all six no-answer questions were still declined without making
  anything up, but two (N02, N06) said "Not in the excerpts retrieved"
  instead of exactly "Not found in the filings." That wording isn't tied to
  chunking; it's likely run-to-run variation.
- Citations: one unsupported number, C03's "about 156,000" for GM, the
  model's own sum of hourly and salaried staff where GM's table says 155,000.

**Decision: keep.** Net two more correct answers (+4.9 points) and two fewer
false refusals, for one regression. The regression points at the next
experiment: give each company more than 3 chunks when a question compares
three or more companies, or fix how the employment-style tables rank.

**Cost.** About $1.25 for the answer run; retrieval runs are free.
