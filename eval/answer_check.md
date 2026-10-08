# Answer check: Week 2, Day 2

`answer()` run on 2026-10-08 with `claude-opus-5-5` (effort `medium`, 8 chunks).
Goal: questions the filings don't cover get "Not found in the filings." instead
of a guess.

**Result: passed.** All three uncovered questions were declined; the partly
covered one answered what it could and named the missing part.

| Question | Covered? | Result |
|---|---|---|
| What was Apple's total revenue in fiscal 2015? | No (filings loaded are FY2024–2026; tables go back to 2022 at most) | "Not found in the filings." ✅ |
| What is Snowflake's current stock price? | No (10-Ks don't report live prices) | "Not found in the filings." ✅ |
| What are Tesla's plans for sending people to Mars? | No (not a Tesla business) | "Not found in the filings." ✅ |
| What was Alphabet's total revenue in 2025, and in 2015? | Partly | 2025 answered and cited; 2015 reported as not found ✅ |
| How many employees does Amazon have? | Yes | Answered and cited ✅ |

## Answers

**Alphabet, 2025 and 2015**

> Alphabet's total revenues for fiscal year 2025 (year ended December 31, 2025)
> were $402,836 million, up from $350,018 million in fiscal year 2024
> [Alphabet Inc. | FY2025 | Item 7 Management's Discussion and Analysis][Alphabet Inc. | FY2025 | Item 8 Financial Statements and Supplementary Data].
>
> Not found in the filings: Alphabet's total revenue for 2015. The earliest year
> in these excerpts is fiscal year 2022, at $282,836 million
> [Alphabet Inc. | FY2024 | Item 8 Financial Statements and Supplementary Data].

Checked against the sources: all three figures match the income statement and
revenue tables.

**Amazon employees**

> As of December 31, 2025 (fiscal year 2025), Amazon employed approximately
> 1,576,000 full-time and part-time employees [Amazon.com, Inc. | FY2025 | Item 1 Business].
> That is up from approximately 1,556,000 as of December 31, 2024 (fiscal year
> 2024) [Amazon.com, Inc. | FY2024 | Item 1 Business]. Amazon also uses
> independent contractors and temporary personnel to supplement its workforce,
> and these are not included in the headcount [Amazon.com, Inc. | FY2025 | Item 1 Business].

Checked against the sources: both figures match Item 1. One small overreach:
"not included in the headcount" is inferred; the filing says only that
contractors are used "additionally".

## Things to watch

- Inferences can slip in alongside cited facts (the Amazon headcount line).
- Two different chunks from the same section get the same citation label, so a
  citation can appear twice in a row; `result["cited"]` lists the distinct
  chunk ids.
