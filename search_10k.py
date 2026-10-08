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
import numpy as np
from fastembed import TextEmbedding

import keyword_index

from embed_10k import CHROMA_DIR, COLLECTION, EMBED_MODEL, QUERY_PREFIX
from fetch_10k import TICKERS_FILE

TOP_K = 5
CANDIDATES = 20  # from each search, before merging
RRF_K = 60  # standard reciprocal rank fusion constant
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


def dense_query(vector: list[float], n: int, where: dict | None) -> list[dict]:
    r = collection().query(query_embeddings=[vector], n_results=n, where=where)
    return [
        {"id": id_, "text": doc, "distance": dist, **meta}
        for id_, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
    ]


def fetch(ids: list[str], vector: list[float]) -> dict[str, dict]:
    """Chunks found only by keyword search, with their cosine distance to the question."""
    r = collection().get(ids=ids, include=["documents", "metadatas", "embeddings"])
    return {
        id_: {"id": id_, "text": doc, "distance": 1 - float(np.dot(vector, emb)), **meta}
        for id_, doc, meta, emb in zip(r["ids"], r["documents"], r["metadatas"], r["embeddings"])
    }


def query(vector: list[float], question: str, n: int, ticker: str | None, mode: str) -> list[dict]:
    """Top n chunks for one company (or all), by meaning alone or merged with keywords."""
    where = {"ticker": ticker} if ticker else None
    if mode == "dense":
        return dense_query(vector, n, where)

    # Reciprocal rank fusion: a chunk scores 1/(RRF_K + rank) in each list it's in.
    dense = dense_query(vector, CANDIDATES, where)
    keyword_ids = keyword_index.search(question, CANDIDATES, ticker)
    scores: dict[str, float] = {}
    for ranked in ([h["id"] for h in dense], keyword_ids):
        for rank, id_ in enumerate(ranked, start=1):
            scores[id_] = scores.get(id_, 0) + 1 / (RRF_K + rank)
    top = sorted(scores, key=scores.get, reverse=True)[:n]

    hits = {h["id"]: h for h in dense}
    keyword_only = [i for i in top if i not in hits]
    if keyword_only:
        hits |= fetch(keyword_only, vector)
    return [{**hits[i], "score": scores[i]} for i in top if i in hits]


def retrieve(question: str, k: int = TOP_K, tickers: list[str] | None = None, mode: str = "hybrid") -> list[dict]:
    """Return the top chunks for a question, best first.

    Each chunk is a dict: id, text, distance, ticker, company, year, section,
    section_title, chunk, tokens (plus score, in hybrid mode). Companies named
    in the question (or given as `tickers`) limit the search to them; with more
    than one, each company gets an equal share of k (rounded up, and at least
    MIN_PER_COMPANY), so more than k chunks can come back.

    mode "hybrid" (default) merges meaning-based and keyword search; "dense"
    uses meaning alone.
    """
    tickers = tickers or companies_in(question)
    vector = next(iter(model().embed([QUERY_PREFIX + question]))).tolist()
    if len(tickers) > 1:
        per_company = max(MIN_PER_COMPANY, -(-k // len(tickers)))  # ceiling division
        hits = [h for t in tickers for h in query(vector, question, per_company, t, mode)]
        return sorted(hits, key=lambda h: -h["score"] if mode == "hybrid" else h["distance"])
    return query(vector, question, k, tickers[0] if tickers else None, mode)


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
