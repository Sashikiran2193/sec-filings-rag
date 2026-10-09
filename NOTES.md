# Week 1 notes: what broke and how it was fixed

1. **EDGAR requests:** the header key was `Sashi-Agent`, and the SEC only accepts `User-Agent`, so every request would have been rejected. Renamed it, and checked the rules on the SEC's own page (10 requests/second, name and email required).
2. **Section splitting:** each item heading appears in the table of contents and again as a page header (Microsoft, Ford), so sections came out empty or mixed up, and Ford's financials (placed after the signatures) landed in Item 16. Now the table of contents is skipped, each item starts at its first real heading, page headers are stripped, and anything after SIGNATURES moves to Item 8.
3. **Tables:** `$` and `%` sat in cells of their own, which shifted numbers into the wrong columns, and Microsoft's tables split one cell per line because of line breaks in the HTML source. Now `$` cells are dropped, `%` is joined onto its number, and source line breaks count as spaces.
4. **Chunk size:** bge-small reads only 512 tokens, and half the 500–800 token chunks were longer, so their ends were never embedded. Re-chunked to at most 480 tokens counted with the model's own tokenizer, leaving room for a header, and fixed an overlap bug that let one chunk reach 528.
5. **Search ignored the company:** filings say "we", not "Tesla", so a Tesla question returned Alphabet first. Now each chunk is embedded with a company/year/section header, questions that name a company are filtered to it, and comparison questions get results from each company named.

## Week 2

- **Exact terms got lost in meaning-based search:** "Who is the CEO of all companies?" named only 7 of 11 CEOs, because signature pages (a list of names and titles) don't *mean* much like the question even though they contain "Chief Executive Officer". Added keyword search (SQLite FTS5, BM25) merged with vector search by reciprocal rank fusion; all 11 are now covered. Years had to be left out of keyword queries, or "fiscal 2025" matched the FY2026 filing first. Before/after in `eval/hybrid_comparison.md`.

- **"Which company employs the most people?" was incomplete and mixed years:** with 2 chunks per company from any year, near-duplicate chunks from different years filled the slots, so 5 companies' headcounts never reached the model (it then wrongly said their filings had none), and Amazon's figure was from FY2024. Multi-company questions without a year now use each company's latest filing, 3 chunks each; "employed/staff/workforce" also match "employees"; and the model now says "Not in the excerpts retrieved" for gaps rather than claiming the filing lacks them. 10 of 11 headcounts now come back (Rivian's still doesn't).

## Week 2: what surprised me about retrieval quality

1. **The most literal answer can be the hardest to find.** A signature page saying "Timothy D. Cook, Chief Executive Officer" ranked behind Item 9B for "Who is the CEO of Apple?", because a list of names and titles doesn't *mean* much like a question. Adding keyword search took "Who is the CEO of all companies?" from 7 CEOs to 11.
2. **Years in a question pull toward the wrong filing.** Each 10-K repeats the prior year's figures, so "fiscal 2025" matched Microsoft's FY2026 filing first. Leaving years out of keyword search and filtering on the filing year instead put the right table in the top results.
3. **Copy-pasted text crowds out the answer.** Risk factors barely change between years, so near-identical chunks from 2024, 2025 and 2026 filled the few slots each company got. Using only each company's latest filing took "which company employs the most people" from 6 to 10 of 11 headcounts.
4. **One word in the question matters a lot.** "Which company has the most employees?" found 5 of 6 headcount chunks; "the highest number of people employed" found 3. Synonyms that match the filings' wording ("employed" → "employees") closed most of the gap.
5. **Retrieval gaps show up as confident answers.** When a chunk wasn't retrieved, the model said "not found in the filings" for companies whose filings do report the figure, and every number it did give was still correct. The answer looked right but was incomplete, so I checked answers against the full chunk set, not just the cited sources, and changed the wording to "not in the excerpts retrieved".

## Known issues (not fixed)

- **Lowercase tickers aren't recognized:** "supply chain risk for amd" searched every company, so NVIDIA's similar risk factors filled 3 of the top 5. Ticker aliases only match in capitals, so "gm" doesn't trigger General Motors. Workaround: type `AMD`, or pass the ticker: `search_10k.py "supply chain risk" AMD`. Look for `[companies: all]` above the results.
- **Unknown or misspelled companies return other companies' results:** searching "nvida" before NVIDIA was loaded returned Microsoft, with no warning. Search always returns the 5 closest chunks. NVIDIA and AMD are now loaded with aliases, but misspellings still aren't caught.
