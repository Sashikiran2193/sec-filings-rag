"""Search the 10-K vector store.

Usage:
  python search_10k.py                          run the three test searches
  python search_10k.py "question" [TICKER]      search, optionally within one company

In code:
  from search_10k import retrieve
  chunks = retrieve("What supply chain risks does Tesla describe?", k=5)

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
from functools import cache

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from fastembed import TextEmbedding

from embed_10k import CHROMA_DIR, COLLECTION, EMBED_MODEL, QUERY_PREFIX
from fetch_10k import TICKERS_FILE

TOP_K = 5
MIN_PER_COMPANY = 2  # when several companies are searched, each gets at least this many
# "all companies", "each company", "every company's", "which companies", "all of the companies"
ALL_COMPANIES = re.compile(r"\b(all|each|every|which|what)\s+(of\s+the\s+)?compan(y|ies)", re.IGNORECASE)
TEST_SEARCHES = [
    "What supply chain risks does Tesla describe?",
    "How fast did Microsoft's cloud revenue grow?",
    "What restructuring charges did Ford record in Europe?",
]


@cache
def collection():
    return chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)


@cache
def model() -> TextEmbedding:
    return TextEmbedding(EMBED_MODEL)


def all_tickers() -> list[str]:
    config = json.loads(TICKERS_FILE.read_text())
    listed = [t for group in config["tickers"].values() for t in group]
    return listed + [t for t in config["aliases"] if t not in listed]


def companies_in(question: str) -> list[str]:
    """Tickers whose aliases appear in the question as whole words.

    A question about "all/each/every/which companies" with none named means
    every company, so each one gets a share of the results.
    """
    aliases = json.loads(TICKERS_FILE.read_text())["aliases"]
    found = []
    for ticker, names in aliases.items():
        for name in names:
            # Tickers ("GM", "AAPL") must match in capitals; names in any case.
            flags = 0 if name.isupper() else re.IGNORECASE
            if re.search(rf"\b{re.escape(name)}\b", question, flags):
                found.append(ticker)
                break
    if not found and ALL_COMPANIES.search(question):
        return all_tickers()
    return found


def query(vector: list[float], n: int, ticker: str | None) -> list[dict]:
    where = {"ticker": ticker} if ticker else None
    r = collection().query(query_embeddings=[vector], n_results=n, where=where)
    return [
        {"id": id_, "text": doc, "distance": dist, **meta}
        for id_, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
    ]


def retrieve(question: str, k: int = TOP_K, tickers: list[str] | None = None) -> list[dict]:
    """Return the top chunks for a question, closest first.

    Each chunk is a dict: id, text, distance, ticker, company, year, section,
    section_title, chunk, tokens. Companies named in the question (or given as
    `tickers`) limit the search to them; with more than one, each company gets
    an equal share of k (rounded up, and at least MIN_PER_COMPANY), so more
    than k chunks can come back.
    """
    tickers = tickers or companies_in(question)
    vector = next(iter(model().embed([QUERY_PREFIX + question]))).tolist()
    if len(tickers) > 1:
        per_company = max(MIN_PER_COMPANY, -(-k // len(tickers)))  # ceiling division
        hits = [h for t in tickers for h in query(vector, per_company, t)]
        return sorted(hits, key=lambda h: h["distance"])
    return query(vector, k, tickers[0] if tickers else None)


def search(question: str, tickers: list[str] | None = None) -> None:
    tickers = tickers or companies_in(question)
    print(f'\n=== "{question}"  [companies: {", ".join(tickers) if tickers else "all"}]')
    for rank, hit in enumerate(retrieve(question, TOP_K, tickers), start=1):
        snippet = hit["text"][:200].replace("\n", " / ")
        print(
            f"{rank}. {hit['company']} | {hit['year']} | {hit['section']} {hit['section_title']}"
            f" | chunk {hit['chunk']} | distance {hit['distance']:.3f}\n   {snippet}..."
        )


def main() -> None:
    if len(sys.argv) > 1:
        tickers = [sys.argv[2].upper()] if len(sys.argv) > 2 else None
        search(sys.argv[1], tickers)
    else:
        for question in TEST_SEARCHES:
            search(question)


if __name__ == "__main__":
    main()
