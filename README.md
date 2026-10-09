# sec-filings-rag

Ask questions in plain English about companies' SEC 10-K annual reports and
get answers that cite the filing sections they came from.

```
> python ask.py "How did Ford and GM describe tariff risks in 2025?"

[tickers: F, GM | years: 2025 | sections: all | search: hybrid]

Ford and GM both called tariffs a significant, still-evolving threat ...
- In 2025, Ford's gross costs from tariffs ... were about $3 billion ...
  [Ford Motor Company | FY2025 | Item 7 Management's Discussion and Analysis]
...
Sources:
  - Ford Motor Company | FY2025 | Item 7 Management's Discussion and Analysis, chunk 1 (F-2025-7-001)
  ...
```

The filings come from SEC EDGAR, search runs locally, and answers are written
by Claude using only the retrieved excerpts. When the filings don't cover a
question, it says "Not found in the filings." instead of guessing.

## Quick start

You need Python 3.11 or newer (tested on 3.14), git, and a Claude API key from
[console.anthropic.com](https://console.anthropic.com).

**1. Clone and install**

```bash
git clone https://github.com/Sashikiran2193/sec-filings-rag.git
cd sec-filings-rag
python -m venv .venv
```

Activate the virtual environment, then install:

```bash
.venv\Scripts\activate          # Windows (PowerShell or cmd)
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
```

**2. Add your settings**

Copy `.env.example` to `.env` (`copy .env.example .env` on Windows,
`cp .env.example .env` elsewhere) and fill in both lines:

```
ANTHROPIC_API_KEY=sk-ant-...
SEC_USER_AGENT=Your Name your.email@example.com
```

The SEC requires your name and email on every download. `.env` is git-ignored,
so neither value is committed.

**3. Download and index the filings**

```bash
python ingest.py
```

This fetches every company and year in `tickers.json` from EDGAR, cleans and
chunks them, and builds the local search index. The first run takes about 10
minutes (it also downloads a small embedding model, about 70 MB). Filings that
don't exist yet, such as a 10-K not filed, are reported as missing and skipped.
To try it faster, load one filing: `python ingest.py --ticker TSLA --year 2025`.

**4. Ask a question**

```bash
python ask.py "What risks did Tesla list in 2025?"
```

Each answer takes a few seconds and costs a few cents in API usage. Questions
are logged to `logs/ask.jsonl` with the chunks retrieved, the answer and the
time taken.

### Asking good questions

- **Name the company:** "Tesla", "Ford and GM", or a ticker in capitals
  (`AMD`, `NVDA`). Lowercase tickers such as "amd" aren't recognized. "All
  companies" or "which companies" searches every company.
- **Name a year** to limit to that fiscal year's filing: "in 2025", "fiscal
  2025", "FY2025".
- **Options** override what's detected: `--ticker F --ticker GM`, `--year 2025`,
  `--section "Item 1A"`, and `--mode dense` for vector-only search.

Companies included: Ford, GM, Tesla, Rivian, Microsoft, Amazon, Alphabet,
Snowflake, NVIDIA and AMD, fiscal years 2024 to 2026. To add one, put its
ticker in `tickers.json` (under `tickers`, plus `names` and `aliases`) and run
`python ingest.py --ticker XXX`.

## How it works

| Step | Script | Output |
|---|---|---|
| 1. Download 10-Ks from EDGAR | `fetch_10k.py` | `data/raw/<ticker>/<year>/*.htm` |
| 2. Clean HTML and split by 10-K item | `parse_10k.py` | `data/clean/<ticker>/<year>/item_<n>.txt` |
| 3. Chunk with metadata | `chunk_10k.py` | `data/chunks/chunks.jsonl` |
| 4. Embed and index | `embed_10k.py`, `keyword_index.py` | `chroma/` (vectors), `data/keywords.db` (keywords) |
| 5. Search | `search_10k.py` | top chunks; `retrieve(question, k)` for code |
| 6. Answer with citations | `answer_10k.py` | `answer(question)` for code |
| 7. Ask | `ask.py` | the command-line entry point |
| Evaluate retrieval | `eval_retrieval.py [--mode dense]` | `eval/` |

`ingest.py` runs steps 1-4 for each filing. Answers use Claude
(`claude-opus-5-5`); the model sees only the retrieved chunks, must cite one
for every claim, and replies "Not found in the filings." when they don't cover
the question (see `eval/answer_check.md`).

### Ingest options

```bash
python ingest.py --ticker TSLA --year 2025   # one filing
python ingest.py --ticker TSLA               # every year in tickers.json
python ingest.py                             # every ticker and year in tickers.json
python ingest.py --force                     # rebuild filings already loaded
```

Re-runs are safe. A filing already loaded is skipped. With `--force`, its old
chunks are deleted from the vector store, the keyword index and
`chunks.jsonl` before the new ones go in, so nothing is stored twice. Each step
and the chunk count per filing are logged to the screen and to
`logs/ingest.log`. The command exits with code 1 if any filing failed.

Any ticker works, not just those in `tickers.json`. For a new ticker, add it
to `aliases` in `tickers.json` so questions that name the company filter to it
automatically, and to `names` for a cleaner name than the SEC's.

The scripts also run on their own over everything on disk:
`python fetch_10k.py`, `parse_10k.py`, `chunk_10k.py`, then `embed_10k.py`,
which rebuilds the vector store and keyword index from `chunks.jsonl`.

## EDGAR access rules

From the SEC's [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
page (checked 2026-10-08):

- **Rate limit:** at most 10 requests per second. `fetch_10k.py` waits 0.2s
  after each request, so it stays at 5 or fewer.
- **User-Agent:** every request must declare a name and contact email in the
  `User-Agent` header; requests without one are rejected.
- The SEC may limit or block automated traffic that doesn't follow these rules.

## Embeddings

- **Model:** `BAAI/bge-small-en-v1.5`, run locally with `fastembed` (no API key)
- **Dimension:** 384
- **Max input:** 512 tokens. Chunks are sized with this model's own tokenizer
  to at most 480 tokens (target 380, 50-token overlap), leaving room for the
  header below, so nothing is cut off. This is smaller than the original
  500-800 token plan, which would not fit.
- **Header:** each chunk is embedded as
  `<company> | FY<year> 10-K | <section> <title>` + the chunk text, because
  filings say "we" rather than the company's name. The stored text has no header.
- **Distance:** cosine. Vectors are normalized.
- **Queries** are prefixed with
  `Represent this sentence for searching relevant passages: `, as bge
  recommends; stored chunks are not.

Changing the model means re-chunking (if its token limit differs) and
re-embedding every chunk, since vectors from different models don't mix.

## Search

Search is hybrid. Each question runs through two searches: meaning-based
vector search in Chroma and keyword (BM25) search in `data/keywords.db`
(SQLite full-text search, built by `keyword_index.py`). Their top 20 are merged
with reciprocal rank fusion, so a chunk that ranks well in either list rises.
Keyword search catches exact terms that vector search misses, such as "Chief
Executive Officer" on a signature page or "rare earth". It expands a few
abbreviations (CEO, CFO, EV, AI) and ignores years, which every filing repeats
for the prior year. `embed_10k.py` and `ingest.py` keep the keyword index in
step with Chroma. To turn hybrid off and use vector search only, pass
`mode="dense"` to `retrieve()` or `answer()`, or `--mode dense` to
`ask.py`, `search_10k.py`, `answer_10k.py` or `eval_retrieval.py`. The on/off comparison
on the ten review questions is in `eval/hybrid_comparison.md`.

### Filters

`retrieve()` and `answer()` take optional `tickers`, `years` and `sections`
filters (`--ticker`, `--year`, `--section` on the command line, each repeatable).
Any filter not given is detected from the question:

- **Year:** "2025", "fiscal 2025" or "FY2025" limits results to that fiscal
  year's filing. A year with no filing loaded uses the next one or two filings,
  which report it as a prior year; if none covers it, nothing is returned and
  `answer()` replies "Not found in the filings." without calling the model.
- **Section:** only when the question names one ("Item 7", "signature page").
- **Company:** see below.

```bash
python ask.py "What risks did Tesla list in 2025?"
python search_10k.py "tariff risks" --ticker F --ticker GM --year 2025 --section "Item 1A"
```

When a question names companies ("Tesla", "Ford and GM", "Google"), results
are limited to those companies, using the aliases in `tickers.json`. Tickers
only match in capitals, so a lowercase "gm" doesn't trigger a filter. Questions
without a company name search everything.

Questions about "all companies", "each company", "every company" or "which
companies" search every company separately, so each one gets at least 2 of the
results instead of the closest few companies taking them all.

Each filing's signature page (the CEO, CFO and directors who signed it) is its
own section, `Signature page`, rather than part of the last 10-K item.

## Known limits

- Tables are flattened to one row per line with ` | ` between cells; alignment
  and multi-row headers are lost.
- Token counts and chunk sizes are tied to the bge tokenizer.
