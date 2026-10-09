# Hybrid search on vs. off

> **Update, later on 2026-10-08:** questions about several companies with no
> year now use each company's latest filing, with 3 chunks each. Re-running
> both modes, the top result differs for 7 of 10 questions (Q4 and Q8 now draw
> on latest filings only). The result files hold the new run; the table below
> is the review of the earlier run.

The ten Day 1 questions, run on 2026-10-08 with the current code (company,
year and section filters on) in both modes:

- Off (vector search only): `retrieval_results_dense.md`, from
  `python eval_retrieval.py --mode dense`
- On (keyword + vector, merged by reciprocal rank fusion):
  `retrieval_results.md`, from `python eval_retrieval.py`

The switch is `mode="dense"` / `mode="hybrid"` on `retrieve()` and `answer()`,
and `--mode dense|hybrid` on `search_10k.py`, `answer_10k.py` and
`eval_retrieval.py`. Hybrid is the default.

**Check: the top result changed for 6 of 10 questions.** Judged by reading the
chunks: 2 better, 1 slightly better, 3 equal, none worse.

| # | Question | Top result, off | Top result, on | Verdict |
|---|---|---|---|---|
| 1 | Tesla supply chain risks | `TSLA-2025-1A-004` | same | unchanged |
| 2 | Microsoft Intelligent Cloud growth, FY2025 | `MSFT-2025-8-061`: Item 8 segment table, Intelligent Cloud revenue 106,265 vs 87,464 | `MSFT-2025-7-008`: MD&A segment table, "Intelligent Cloud / Revenue \| 106,265 \| 87,464 \| 21%" | Equal. Both contain the answer (first judged "worse" from the chunk's opening lines; corrected after reading the whole chunk) |
| 3 | Ford restructuring in Europe, 2025 | `F-2025-8-118`: restructuring accrual table, no Europe breakdown | `F-2025-7-012`: special items by geography, Europe $(736)M | **Better.** Answers the question directly |
| 4 | Ford and GM on EV transition risks | `F-2024-1A-023` | same | unchanged |
| 5 | NVIDIA export controls | `NVDA-2026-1A-042` | same | unchanged |
| 6 | Amazon employee count | `AMZN-2024-1-005` | same | unchanged |
| 7 | Alphabet total revenue, 2025 | `GOOGL-2025-7-012`: revenues by type | `GOOGL-2025-8-030`: revenues by region, with "Total revenues … 402,836" | Slightly better. Both relevant; the new one states the total |
| 8 | Which companies cite tariffs | `GM-2025-1A-013` | `TSLA-2025-1A-012` | Equal. Both are tariff risk factors |
| 9 | Snowflake cybersecurity, and who oversees it | `SNOW-2024-1C-002`: how threats are monitored | `SNOW-2026-1C-004`: the cybersecurity committee and its oversight role | **Better.** Answers "who oversees it" |
| 10 | Rivian–Volkswagen joint venture | `RIVN-2024-8-014` | `RIVN-2025-8-014` | Equal. Same note, next year's filing |

Outside the ten: "Who is the CEO of Apple?" gets Item 9B (Other
Information) first with hybrid off, and Apple's signature page, which names
Timothy D. Cook, with it on.

## Why it helps, and where it doesn't

Keyword search rewards chunks containing the question's exact terms: "Europe"
and "restructuring" (Q3), "oversees" (Q9), "chief executive officer" (Apple).
The risk is the reverse case, where a chunk repeats the question's words
without answering it; none of the ten showed that. Through `answer()`, Q2
came back correct with hybrid on: "$18.8 billion, or 21%", from $87,464 million
to $106,265 million, cited to `MSFT-2025-7-010` and `MSFT-2025-7-008`.
`answer()` passes 8 chunks to the model, so a rank change inside the top 8
doesn't change what it sees. Re-run both modes after any retrieval change to
catch a regression.

## How the tuning was chosen

- **"CEO" expands to "chief executive officer"** (and CFO, EV, AI and a few
  others), since filings spell titles out.
- **Years and "fiscal" are left out of keyword queries.** The year filter
  handles them, and as keywords they matched the next year's filing, which
  compares against the prior year.
- **The filtered companies' names are left out of keyword queries.** Otherwise
  exhibit lists that repeat "AMD" dozens of times outranked risk factors.
