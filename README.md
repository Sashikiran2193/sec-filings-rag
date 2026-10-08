# sec-filings-rag

Retrieval over SEC 10-K filings: download, clean, chunk, embed and search.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Download 10-Ks from EDGAR | `fetch_10k.py` | `data/raw/<ticker>/<year>/*.htm` |
| 2. Clean HTML and split by 10-K item | `parse_10k.py` | `data/clean/<ticker>/<year>/item_<n>.txt` |
| 3. Chunk with metadata | `chunk_10k.py` | `data/chunks/chunks.jsonl` |
| 4. Embed and load the vector store | `embed_10k.py` | `chroma/` (collection `sec_10k`) |
| 5. Search | `search_10k.py` | prints top 5 chunks |

Tickers and years are listed in `tickers.json`.

```powershell
pip install -r requirements.txt
python fetch_10k.py
python parse_10k.py
python chunk_10k.py
python embed_10k.py
python search_10k.py                       # three test searches
python search_10k.py "question" [TICKER]   # your own search
```

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

## Known limits

- Tables are flattened to one row per line with ` | ` between cells; alignment
  and multi-row headers are lost.
- Token counts and chunk sizes are tied to the bge tokenizer.
