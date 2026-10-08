# Hybrid search vs. meaning-only search

Same ten questions as `retrieval_review.md`, run on 2026-10-08 against the
current store (signature pages split out, all-company questions searched per
company). Results: `retrieval_results_dense.md` (meaning only) and
`retrieval_results.md` (hybrid: meaning + keyword, merged by reciprocal rank
fusion).

**Summary:** both modes have a relevant chunk in the top 5 for 10 of 10
questions. Hybrid puts one at rank 1 for 8 of 10 (meaning-only: 7), clears out
the generic section openings, and fixed the case that started this: "Who is the
CEO of all companies?" went from 7 CEOs named to all 11.

| # | Question | First relevant rank: meaning only | Hybrid | Change |
|---|---|---|---|---|
| 1 | Tesla supply chain risks | 1 (plus 2 generic "Risk Factors" openings) | 1 (Item 1 "Supply Chain"; openings gone) | Better |
| 2 | Microsoft Intelligent Cloud growth, FY2025 | 2 (segment table) | 5 (same table) | **Worse** |
| 3 | Ford restructuring in Europe, 2025 | 4 | 1 (special-items table: Europe $(736)M) | Better |
| 4 | Ford and GM on EV transition risks | Ford 1; GM none | Ford 1; GM 3 (EV launch risk factor) | Better |
| 5 | NVIDIA export controls | 1 | 1 | Same |
| 6 | Amazon employee count | 1 | 1 (ranks 3–4 now generic Item 1 openings) | Same |
| 7 | Alphabet total revenue, 2025 | 5 | 2 (income statement: $402,836M) | Better |
| 8 | Which companies cite tariffs | 1 | 1, and 5 different companies in the top 5 | Better |
| 9 | Snowflake cybersecurity oversight | 1 | 1 (the oversight committee chunk) | Better |
| 10 | Rivian–Volkswagen joint venture | 1 (plus 2 general overviews) | 1 (all 5 about the joint venture) | Better |

## The CEO question

"Who is ceo of all companies?" through `answer()`:

- Meaning only: 7 of 11 CEOs named; Ford, Apple, AMD and Alphabet "not found".
- Hybrid: all 11 companies covered, 10 with the CEO named and cited (Ford from
  Item 4A, Apple from the signature page). For Tesla the excerpts only say
  "our CEO"; the answer notes the 2018 CEO Performance Award went to Elon Musk
  rather than stating it outright.

## What was tuned

- **"CEO" is expanded to "chief executive officer"** (and CFO, EV, AI and a few
  others), since filings spell titles out.
- **Years and "fiscal" are left out of keyword queries.** With them, "fiscal
  2025" matched the FY2026 filing (which compares against 2025) as strongly as
  the FY2025 one, and pushed Q2's answer from rank 2 to 8. Without them it's
  rank 5; Q3 stays at 1 and Q7 moves from 1 to 2.

## Still weak

- **Q2:** both modes rank Microsoft's FY2026 highlights first for a fiscal 2025
  question. A year filter is the real fix.
- **Generic section openings** still appear for broad questions (Q6 ranks 3–4).
