# Metadata filter check: Week 2, Day 3

Run on 2026-10-08.

## Check: "What risks did company A list in 2025?"

`retrieve(question, 8)` with filters detected from the question. **Passed:**
every chunk was the named company's FY2025 filing.

| Question | Detected filters | Only that company and 2025? | Sections in the 8 chunks |
|---|---|---|---|
| What risks did Tesla list in 2025? | TSLA, 2025 | Yes | 1A ×5, 1C ×3 |
| What risks did Ford list in 2025? | F, 2025 | Yes | 1A ×2, 1C, 7 ×2, 7A ×3 |
| What risks did Microsoft list in 2025? | MSFT, 2025 | Yes | 1A ×7, 8 |
| What risks did NVIDIA list in 2025? | NVDA, 2025 | Yes | 1, 1A ×4, 1C, 7 ×2 |
| What risks did Snowflake list in 2025? | SNOW, 2025 | Yes | 1A ×5, 1C ×2, 8 |
| What risks did AMD list in 2025? | AMD, 2025 | Yes | 1, 1A ×5, 1C, 7A |

The first run had exhibit lists (Item 15) in AMD's, Snowflake's, Microsoft's
and NVIDIA's results, because the keyword query included the company name and
exhibit lists repeat it dozens of times. The filtered companies' names are now
left out of the keyword query.

Through `answer()`, the Tesla question gave nine cited risk areas, all from the
FY2025 filing (Item 1A and 1C).

## Comparison across two companies

"How did Ford and GM describe tariff risks in 2025?" → filters F, GM, 2025.
The answer covered both companies with FY2025 citations only (Items 1A and 7),
and every figure matched its source:

- Ford: about $3 billion gross tariff cost and about $2 billion net EBIT
  impact in 2025; a $974 million receivable for tariffs awaiting refund
  (`F-2025-7-001`).
- GM: $3.1 billion EBIT-adjusted impact in 2025, $3.0–4.0 billion estimated
  for 2026 (`GM-2025-7-002`).

## Year detection

| Question mentions | Filter |
|---|---|
| "2025", "fiscal 2025", "FY2025" | the FY2025 filing |
| "2023" (no filing loaded) | FY2024 and FY2025 filings, which report 2023 |
| "2015" (nothing covers it) | no chunks; `answer()` returns "Not found in the filings." without calling the model |
| "ASU 2023-09" | not treated as a year |

The year filter also fixed the Microsoft question from the Day 1 review ("…in
fiscal 2025"): the FY2025 segment table moved from rank 5 to 3, and the chunk
stating the growth directly entered the top 8 (rank 6).
