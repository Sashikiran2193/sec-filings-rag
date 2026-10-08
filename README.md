# sec-filings-rag

Retrieval over SEC 10-K filings: download, clean, chunk, embed and search.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Download 10-Ks from EDGAR | `fetch_10k.py` | `data/raw/<ticker>/<year>/*.htm` |
| 2. Clean HTML and split by 10-K item | `parse_10k.py` | `data/clean/<ticker>/<year>/item_<n>.txt` |
| 3. Chunk with metadata | `chunk_10k.py` | `data/chunks/chunks.jsonl` |
| 4. Embed and load the vector store | `embed_10k.py` | `chroma/` (collection `sec_10k`) |
| 5. Search | `search_10k.py` | prints top 5 chunks; `retrieve(question, k)` for code |
| 6. Evaluate retrieval | `eval_retrieval.py` | `eval/retrieval_results.md` (reviewed in `eval/retrieval_review.md`) |
| 7. Answer with citations | `answer_10k.py` | answer citing company, fiscal year and section; `answer(question)` for code |

Answers use Claude (`claude-opus-5-5`) and need `ANTHROPIC_API_KEY` in `.env`.
The model sees only the retrieved chunks, must cite one for every claim, and
replies "Not found in the filings." when they don't cover the question (see
`eval/answer_check.md`).

Tickers and years are listed in `tickers.json`.

### One command

`ingest.py` runs steps 1-4 for each filing:

```powershell
pip install -r requirements.txt
python ingest.py --ticker TSLA --year 2025   # one filing
python ingest.py --ticker TSLA               # every year in tickers.json
python ingest.py                             # every ticker and year in tickers.json
python ingest.py --force                     # rebuild filings already loaded
python search_10k.py                         # three test searches
python search_10k.py "question" [TICKER]     # your own search
```

Re-runs are safe. A filing already in the vector store is skipped. With
`--force`, its old chunks are deleted from Chroma and from `chunks.jsonl`
before the new ones go in, so nothing is stored twice. Filings that don't
exist yet (e.g. a 10-K not filed) are logged as missing and the run carries
on. Each step and the chunk count per filing are logged to the screen and to
`logs/ingest.log`. The command exits with code 1 if any filing failed.

Any ticker works, not just those in `tickers.json`. For a new ticker, add it
to `aliases` in `tickers.json` so searches that name the company filter to it
automatically, and to `names` for a cleaner name than the SEC's.

### Step by step

The scripts also run on their own, over everything on disk:

```powershell
python fetch_10k.py; python parse_10k.py; python chunk_10k.py; python embed_10k.py
```

`embed_10k.py` rebuilds the whole vector store from `chunks.jsonl`.

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
