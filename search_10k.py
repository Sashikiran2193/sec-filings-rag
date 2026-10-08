"""Search the 10-K vector store.

Usage:
  python search_10k.py                                    run the three test searches
  python search_10k.py "question"                         search; filters detected from the question
  python search_10k.py "question" --ticker F --ticker GM --year 2025 --section "Item 1A"

In code:
  from search_10k import retrieve
  chunks = retrieve("What risks did Tesla list in 2025?", k=5)
  chunks = retrieve("tariff risks", k=5, tickers=["F", "GM"], years=["2025"], sections=["Item 1A"])

Filters (any combination; each one given overrides detection for that filter):
- Companies: detected from names and tickers in the question (aliases in
  tickers.json); "all/each/every/which companies" means every company.
- Years: detected from "2025", "fiscal 2025" or "FY2025" and matched to the
  filing for that fiscal year. A year with no filing loaded (e.g. 2023) uses
  the next one or two filings, which report it as a prior year.
- Sections: detected only when the question names one ("Item 7", "signature page").

Prints the top five chunks with their metadata and cosine distance
(0 = same meaning; lower is closer).
"""

import argparse
import json
import os
import re
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
# "2025", "FY2025", "fiscal 2025"; not "ASU 2023-09" or "$2,025".
YEAR = re.compile(r"(?<![\w$,-])(?:FY\s?)?((?:19|20)\d\d)(?![\w-])", re.IGNORECASE)
SECTION = re.compile(r"\bitem\s+(\d{1,2}[a-c]?)\b|\b(signature page|signatures)\b", re.IGNORECASE)
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


def years_in(question: str) -> list[str]:
    """Filing years for the years a question names.

    A year with no filing loaded maps to the next one or two loaded filings,
    since each 10-K also reports the two years before it.
    """
    loaded = set(keyword_index.loaded_years())
    years = set()
    for year in YEAR.findall(question):
        if year in loaded:
            years.add(year)
        else:
            later = {str(int(year) + i) for i in (1, 2)} & loaded
            years |= later or {year}  # nothing loaded covers it: no chunks match
    return sorted(years)


def sections_in(question: str) -> list[str]:
    sections = []
    for item, signatures in SECTION.findall(question):
        sections.append("Signature page" if signatures else f"Item {item.upper()}")
    return list(dict.fromkeys(sections))


def filters_for(
    question: str, tickers: list[str] | None = None,
    years: list[str] | None = None, sections: list[str] | None = None,
) -> dict[str, list[str]]:
    """The filters a search uses: those given, else those detected in the question."""
    return {
        "tickers": [t.upper() for t in tickers] if tickers is not None else companies_in(question),
        "years": [str(y) for y in years] if years is not None else years_in(question),
        "sections": sections if sections is not None else sections_in(question),
    }


def without_companies(question: str, tickers: list[str]) -> str:
    """Drop the filtered companies' names from the keyword query.

    Once results are limited to a company, its name adds nothing to keyword
    matching, and it ranks chunks that repeat it (exhibit lists naming "AMD"
    dozens of times) above ones about the question.
    """
    aliases = json.loads(TICKERS_FILE.read_text())["aliases"]
    for ticker in tickers:
        for name in aliases.get(ticker, []) + [ticker]:
            question = re.sub(rf"\b{re.escape(name)}(?:'s)?\b", " ", question, flags=re.IGNORECASE)
    return question


def where_for(ticker: str | None, years: list[str], sections: list[str]) -> dict | None:
    conditions = []
    if ticker:
        conditions.append({"ticker": ticker})
    for field, values in (("year", years), ("section", sections)):
        if values:
            conditions.append({field: values[0]} if len(values) == 1 else {field: {"$in": values}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


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


def query(
    vector: list[float], question: str, n: int, ticker: str | None,
    years: list[str], sections: list[str], mode: str,
) -> list[dict]:
    """Top n chunks for one company (or all), by meaning alone or merged with keywords."""
    where = where_for(ticker, years, sections)
    if mode == "dense":
        return dense_query(vector, n, where)

    # Reciprocal rank fusion: a chunk scores 1/(RRF_K + rank) in each list it's in.
    dense = dense_query(vector, CANDIDATES, where)
    keyword_question = without_companies(question, [ticker]) if ticker else question
    keyword_ids = keyword_index.search(keyword_question, CANDIDATES, ticker, years, sections)
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


def retrieve(
    question: str, k: int = TOP_K, tickers: list[str] | None = None,
    years: list[str] | None = None, sections: list[str] | None = None, mode: str = "hybrid",
) -> list[dict]:
    """Return the top chunks for a question, best first.

    Each chunk is a dict: id, text, distance, ticker, company, year, section,
    section_title, chunk, tokens (plus score, in hybrid mode).

    tickers, years and sections filter the search ("Item 1A", "Signature page");
    any left as None are detected from the question (see filters_for). With
    more than one company, each gets an equal share of k (rounded up, and at
    least MIN_PER_COMPANY), so more than k chunks can come back.

    mode "hybrid" (default) merges meaning-based and keyword search; "dense"
    uses meaning alone.
    """
    f = filters_for(question, tickers, years, sections)
    vector = next(iter(model().embed([QUERY_PREFIX + question]))).tolist()
    if len(f["tickers"]) > 1:
        per_company = max(MIN_PER_COMPANY, -(-k // len(f["tickers"])))  # ceiling division
        hits = [
            h for t in f["tickers"]
            for h in query(vector, question, per_company, t, f["years"], f["sections"], mode)
        ]
        return sorted(hits, key=lambda h: -h["score"] if mode == "hybrid" else h["distance"])
    ticker = f["tickers"][0] if f["tickers"] else None
    return query(vector, question, k, ticker, f["years"], f["sections"], mode)


def describe(f: dict[str, list[str]]) -> str:
    return " | ".join(f"{name}: {', '.join(values) or 'all'}" for name, values in f.items())


def search(question: str, **filters) -> None:
    f = filters_for(question, **filters)
    print(f'\n=== "{question}"  [{describe(f)}]')
    hits = retrieve(question, TOP_K, **f)
    if not hits:
        print("No chunks match these filters.")
    for rank, hit in enumerate(hits, start=1):
        snippet = hit["text"][:200].replace("\n", " / ")
        print(
            f"{rank}. {hit['company']} | {hit['year']} | {hit['section']} {hit['section_title']}"
            f" | chunk {hit['chunk']} | distance {hit['distance']:.3f}\n   {snippet}..."
        )


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ticker", action="append", help="repeat for several, e.g. --ticker F --ticker GM")
    parser.add_argument("--year", action="append", help="fiscal year of the filing, e.g. 2025")
    parser.add_argument("--section", action="append", help='e.g. "Item 1A" or "Signature page"')


def filter_kwargs(args: argparse.Namespace) -> dict:
    return {"tickers": args.ticker, "years": args.year, "sections": args.section}


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the 10-K vector store.")
    parser.add_argument("question", nargs="?")
    parser.add_argument("ticker_arg", nargs="?", metavar="TICKER", help="shorthand for --ticker")
    add_filter_args(parser)
    args = parser.parse_args()
    if args.ticker_arg:
        args.ticker = (args.ticker or []) + [args.ticker_arg]
    if args.question:
        search(args.question, **filter_kwargs(args))
    else:
        for question in TEST_SEARCHES:
            search(question)


if __name__ == "__main__":
    main()
