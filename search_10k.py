"""Search the 10-K vector store.

Usage:
  python search_10k.py                          run the three test searches
  python search_10k.py "question" [TICKER]      search, optionally within one company

If the question names companies ("Tesla", "Ford and GM"), results are limited
to those companies automatically, using the aliases in tickers.json. A ticker
given on the command line overrides that.

Prints the top five chunks with their metadata and cosine distance
(0 = same meaning; lower is closer).
"""

import json
import os
import re
import sys

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from fastembed import TextEmbedding

from embed_10k import CHROMA_DIR, COLLECTION, EMBED_MODEL, QUERY_PREFIX
from fetch_10k import TICKERS_FILE

TOP_K = 5
TEST_SEARCHES = [
    "What supply chain risks does Tesla describe?",
    "How fast did Microsoft's cloud revenue grow?",
    "What restructuring charges did Ford record in Europe?",
]


def companies_in(question: str) -> list[str]:
    """Tickers whose aliases appear in the question as whole words."""
    aliases = json.loads(TICKERS_FILE.read_text())["aliases"]
    found = []
    for ticker, names in aliases.items():
        for name in names:
            # Tickers ("GM", "AAPL") must match in capitals; names in any case.
            flags = 0 if name.isupper() else re.IGNORECASE
            if re.search(rf"\b{re.escape(name)}\b", question, flags):
                found.append(ticker)
                break
    return found


def query(collection, vector: list[float], n: int, ticker: str | None) -> list[tuple]:
    where = {"ticker": ticker} if ticker else None
    r = collection.query(query_embeddings=[vector], n_results=n, where=where)
    return list(zip(r["documents"][0], r["metadatas"][0], r["distances"][0]))


def search(collection, model: TextEmbedding, question: str, tickers: list[str] | None = None) -> None:
    tickers = tickers or companies_in(question)
    vector = next(iter(model.embed([QUERY_PREFIX + question]))).tolist()
    if len(tickers) > 1:
        # Comparison question: split the top results evenly across the companies.
        per_company = -(-TOP_K // len(tickers))  # ceiling division
        hits = [h for t in tickers for h in query(collection, vector, per_company, t)]
        hits.sort(key=lambda h: h[2])
    else:
        hits = query(collection, vector, TOP_K, tickers[0] if tickers else None)

    print(f'\n=== "{question}"  [companies: {", ".join(tickers) if tickers else "all"}]')
    for rank, (doc, meta, dist) in enumerate(hits, start=1):
        snippet = doc[:200].replace("\n", " / ")
        print(
            f"{rank}. {meta['company']} | {meta['year']} | {meta['section']} {meta['section_title']}"
            f" | chunk {meta['chunk']} | distance {dist:.3f}\n   {snippet}..."
        )


def main() -> None:
    collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)
    model = TextEmbedding(EMBED_MODEL)
    if len(sys.argv) > 1:
        tickers = [sys.argv[2].upper()] if len(sys.argv) > 2 else None
        search(collection, model, sys.argv[1], tickers)
    else:
        for question in TEST_SEARCHES:
            search(collection, model, question)


if __name__ == "__main__":
    main()
