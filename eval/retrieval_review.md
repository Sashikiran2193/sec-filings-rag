# Retrieval review: Week 2, Day 1

Hand review of `eval/retrieval_results.md` (top 5 from `retrieve()` for ten
questions). "Relevant" means the chunk contains information that answers the
question.

**Check: 10 of 10 questions have a relevant chunk in the top 5 (target: 7).**
7 of 10 have one at rank 1.

| # | Question | Relevant in top 5? | First relevant rank | Verdict |
|---|---|---|---|---|
| 1 | Tesla supply chain risks | Yes (1, 2, 5) | 1 | Good |
| 2 | Microsoft Intelligent Cloud growth, fiscal 2025 | Yes (2, 3) | 2 | Weak: wrong year ranked first |
| 3 | Ford restructuring charges in Europe, 2025 | Yes (4) | 4 | Weak: wrong year ranked first |
| 4 | Ford and GM on EV transition risks | Ford yes (1–3), GM no | 1 | Half: GM side missed |
| 5 | NVIDIA export controls on China | Yes (all 5) | 1 | Good |
| 6 | Amazon employee count | Yes (1, 2) | 1 | Good |
| 7 | Alphabet total revenue, 2025 | Yes (5) | 5 | Weak: answer only at rank 5 |
| 8 | Which companies cite tariffs as a risk | Yes (all 5) | 1 | Good, but only 4 companies |
| 9 | Snowflake cybersecurity oversight | Yes (all 5) | 1 | Good |
| 10 | Rivian's joint venture with Volkswagen | Yes (1, 3, 4) | 1 | Good |

## Where retrieval is poor, and why

1. **The year in a question is ignored (Q2, Q3, Q7).** Search filters by
   company but not by year. "Fiscal 2025" returned Microsoft's FY2026
   highlights first, and "Ford ... in 2025" returned the 2024 filing first; the
   right chunks (MSFT 2025 segment table, Ford 2025 special-items table, which
   shows Europe at $(736)M) came in at ranks 2 and 4. Possible fix: detect a
   year in the question and filter to it, keeping in mind that a later filing
   also reports the prior year's numbers.
2. **Answers in tables rank low (Q2, Q7).** Totals such as Alphabet's 2025
   revenue ($402,836M) sit in table rows. Narrative "highlights" chunks with the
   right words but not the number rank higher; the revenue table was rank 5.
3. **Comparison questions can fill one company's share with weak chunks
   (Q4).** Each company gets an equal share, but GM's three were about
   autonomous vehicles (AVs, which the model treats as close to EVs), general
   international risks, and the MD&A introduction. GM's actual EV strategy risk
   factor didn't make it in.
4. **The same passage repeats across years (Q1, Q5, Q9).** Risk factors and
   Item 1C are largely copied from year to year, so near-identical chunks from
   2024, 2025 and 2026 take several of the five slots. For Q8 ("which
   companies"), Apple took two slots, which leaves room for only 4 companies.
5. **Section openings match too easily (Q1, Q4).** Chunks that are just the
   standard opening of a section ("ITEM 1A. RISK FACTORS / You should carefully
   consider the risks…") match any risk question, because the section name is
   in their header. Two of Tesla's five results were these.

## Fixes worth trying (not done yet)

- Filter by year when the question names one (fixes 1).
- Drop near-duplicate chunks from other years, or keep only the latest year
  unless a year is asked for (fixes 4, and frees slots for 2 and 3).
- Fetch more candidates (say 20) and rerank them before keeping the top 5
  (helps 2, 3 and 5).
