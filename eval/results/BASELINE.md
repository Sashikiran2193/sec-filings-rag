# Retrieval baseline

**Hit rate: 95.1%** (39 of 41 questions): a chunk from a correct section was in
the top 5 results.

Measured 2026-10-09 at commit `da4e8ac` with `python eval/measure_retrieval.py`
(hybrid search, top 5) on the 47-question test set (`eval/questions.jsonl`).
Retrieval only, no model calls. Full per-question results:
`retrieval_baseline.json`.

## By question type

| Type | Questions | Hit | Hit, fiscal year too | Every source hit | Answer quote retrieved |
|---|---|---|---|---|---|
| **Overall** | 41 | **95.1%** | 95.1% | 92.7% | 78.0% |
| Fact | 25 | 92.0% | 92.0% | 92.0% | 72.0% |
| Summary | 8 | 100.0% | 100.0% | 100.0% | 75.0% |
| Comparison | 8 | 100.0% | 100.0% | 87.5% | 100.0% |

The 6 no-answer questions have no correct section, so they aren't scored here;
they're tested on answers, not retrieval.

## What the columns mean

- **Hit** (the headline): a top-5 chunk comes from the right company and 10-K
  section of one of the question's sources, in any fiscal year.
- **Hit, fiscal year too:** the year must match as well. Same as Hit here,
  because the year filter already does this whenever a question names a year.
- **Every source hit:** all of a question's sources are hit. Lower only for one
  comparison (C03, Ford vs GM vs Tesla headcount): with three companies,
  retrieval returns 9 chunks (3 each) but only the first 5 are scored, and GM's
  Item 1 chunk wasn't among them.
- **Answer quote retrieved:** the exact sentence or table row holding the answer
  is in a top-5 chunk. This is the strict measure, and the gap from Hit is the
  main thing to know about this baseline.

## How to read it

The section-level hit rate is generous: Item 7 alone is 50–150 chunks per
filing, so "a chunk from Item 7" doesn't mean the chunk with the answer. The
quote measure is strict in the other direction: it misses when the same fact
is retrieved in a different form. For example, F06 retrieves Tesla's revenue
table (94,827) but not the sentence quoted as the source ($94.83 billion). The
truth sits between 78% and 95%.

## Misses

| Question | Expected | Retrieved instead | Why |
|---|---|---|---|
| F18 Who is AMD's CEO? | Signature page | Item 15 ×2, Item 1 ×2, Item 9A | Exhibit lists and certifications repeat "Chief Executive Officer"; the signature page ranks lower |
| F25 How many employees did Apple have at the end of fiscal 2025? | Item 1 | Item 8, 15, 7 ×2, 1A | Apple's headcount sentence sits in a short Item 1, outranked by financial sections |

Section hit but answer text not retrieved: F06, F09, F10 (the figure appears
elsewhere in a retrieved table), S02 (one of two Snowflake cybersecurity
quotes), S05, and F15 and F16. The last two are the clearest weakness: the
Snowflake and Rivian headcount chunks rank below 20th even for a question
asking for exactly that, so the Item 1 "hit" is a different Item 1 chunk.

## Reference runs (same test set)

| Run | Hit | Answer quote retrieved | File |
|---|---|---|---|
| **Hybrid, top 5 (baseline)** | **95.1%** | **78.0%** | `retrieval_baseline.json` |
| Vector search only, top 5 | 90.2% | 75.6% | `retrieval_dense.json` |
| Hybrid, top 8 (what `answer()` passes the model) | 95.1% | 85.4% | `retrieval_hybrid_k8.json` |

Hybrid search adds 4.9 points of hit rate over vector search alone (it
recovers F03 and F15). Passing 8 chunks instead of 5 doesn't change which
sections are found, but raises how often the exact answer text is included
from 78% to 85%.
