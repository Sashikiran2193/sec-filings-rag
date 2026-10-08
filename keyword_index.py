"""Keyword (BM25) index over the chunks, using SQLite's built-in full-text search.

Meaning-based vector search misses chunks whose match is an exact phrase, such
as a signature page listing "Chief Executive Officer". This index finds those;
search_10k.retrieve() merges both result lists.

The index lives in data/keywords.db and mirrors data/chunks/chunks.jsonl.
embed_10k.py rebuilds it and ingest.py updates it per filing; if it's missing,
search() builds it on first use.
"""

import json
import re
import sqlite3
from pathlib import Path

DB_FILE = Path("data/keywords.db")
CHUNKS_FILE = Path("data/chunks/chunks.jsonl")

# Words that carry no meaning for matching; dropped from keyword queries.
STOPWORDS = set("""
a an and are as at be been by can could did do does for from had has have how i in
into is it its me my of on or our over should so than that the their them then there
these they this those to under was we were what when where which who whom whose why
will with would you your about all any each every other some such tell describe
describes say says said mention mentions company companies firm firms business businesses
""".split())
YEARS = re.compile(r"\b(?:19|20)\d\d\b|\bfiscal\b|\bFY\d*\b", re.IGNORECASE)
# Abbreviations filings spell out. Each expands to the abbreviation OR the full phrase.
ABBREVIATIONS = {
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "coo": "chief operating officer",
    "cto": "chief technology officer",
    "ev": "electric vehicle",
    "evs": "electric vehicles",
    "ai": "artificial intelligence",
    "r&d": "research and development",
    "capex": "capital expenditures",
}


def connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_FILE)


def _insert(db: sqlite3.Connection, chunks: list[dict]) -> None:
    db.executemany(
        "INSERT INTO chunks (id, ticker, year, text) VALUES (?, ?, ?, ?)",
        [(c["id"], c["ticker"], c["year"], c["text"]) for c in chunks],
    )


def rebuild(chunks: list[dict]) -> None:
    with connect() as db:
        db.execute("DROP TABLE IF EXISTS chunks")
        # porter: match "tariff" with "tariffs"; ids and filters aren't searched.
        db.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5("
            "id UNINDEXED, ticker UNINDEXED, year UNINDEXED, text, tokenize='porter unicode61')"
        )
        _insert(db, chunks)


def replace_filing(ticker: str, year: str, chunks: list[dict]) -> None:
    if not DB_FILE.exists():
        rebuild_from_file()
    with connect() as db:
        db.execute("DELETE FROM chunks WHERE ticker = ? AND year = ?", (ticker, year))
        _insert(db, chunks)


def rebuild_from_file() -> None:
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        rebuild([json.loads(line) for line in f])


def to_query(question: str) -> str | None:
    """'Who is the CEO of all companies?' -> 'ceo OR "chief executive officer"'.

    Years and "fiscal" are left out: every filing also reports the prior year,
    so "2025" matches the FY2026 filing as strongly as the FY2025 one.
    """
    question = YEARS.sub(" ", question)
    terms = []
    for word in re.findall(r"[a-z0-9&]+(?:'[a-z]+)?", question.lower()):
        word = word.removesuffix("'s")
        if word in STOPWORDS or len(word) < 2:
            continue
        terms.append(f'"{word}"')
        if word in ABBREVIATIONS:
            terms.append(f'"{ABBREVIATIONS[word]}"')
    return " OR ".join(dict.fromkeys(terms)) or None


def search(question: str, n: int, ticker: str | None = None) -> list[str]:
    """Ids of the n chunks that best match the question's keywords, best first."""
    query = to_query(question)
    if query is None:
        return []
    if not DB_FILE.exists():
        rebuild_from_file()
    sql = "SELECT id FROM chunks WHERE chunks MATCH ?"
    params: list = [query]
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker)
    sql += " ORDER BY bm25(chunks) LIMIT ?"
    params.append(n)
    with connect() as db:
        return [row[0] for row in db.execute(sql, params)]
