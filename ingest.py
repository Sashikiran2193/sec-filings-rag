"""Run the whole pipeline for one or more filings: download, clean, chunk, embed, store.

Usage:
  python ingest.py --ticker TSLA --year 2025   one filing
  python ingest.py --ticker TSLA               every year in tickers.json
  python ingest.py --year 2025                 every ticker in tickers.json
  python ingest.py                             every ticker and year in tickers.json
  add --force to rebuild filings that are already loaded

Safe to re-run: a filing already in the vector store is skipped, and with
--force its old chunks are replaced, never duplicated. Logs go to the screen
and to logs/ingest.log.
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
from functools import cache
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from fastembed import TextEmbedding

from chunk_10k import chunk_filing, save_filing_chunks
from embed_10k import CHROMA_DIR, EMBED_MODEL, get_collection, is_loaded, replace_filing
from fetch_10k import TICKERS_FILE, fetch_10k
from parse_10k import parse_filing

LOG_FILE = Path("logs/ingest.log")
log = logging.getLogger("ingest")


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


@cache
def model() -> TextEmbedding:
    log.info("Loading embedding model %s", EMBED_MODEL)
    return TextEmbedding(EMBED_MODEL)


def ingest_filing(collection, ticker: str, year: str, force: bool) -> tuple[str, int]:
    """Run every step for one filing. Returns (status, chunks written)."""
    tag = f"[{ticker} {year}]"
    if not force and is_loaded(collection, ticker, year):
        log.info("%s already loaded, skipping (use --force to rebuild)", tag)
        return "skipped", 0

    start = time.time()
    log.info("%s 1/4 download", tag)
    try:
        raw = fetch_10k(ticker, year)
    except ValueError as e:  # unknown ticker, or no 10-K for that year yet
        log.warning("%s no filing: %s", tag, e)
        return "missing", 0
    log.info("%s      %s (%.1f MB)", tag, raw, raw.stat().st_size / 1e6)

    log.info("%s 2/4 clean and split into sections", tag)
    out_dir = parse_filing(raw)
    log.info("%s      %d sections -> %s", tag, len(list(out_dir.glob("item_*.txt"))), out_dir)

    log.info("%s 3/4 chunk", tag)
    chunks = chunk_filing(ticker, year)
    if not chunks:
        raise ValueError("no chunks produced; the filing's sections could not be found")
    save_filing_chunks(ticker, year, chunks)
    log.info("%s      %d chunks", tag, len(chunks))

    log.info("%s 4/4 embed and store", tag)
    replace_filing(collection, model(), ticker, year, chunks)
    log.info("%s done: %d chunks written in %.0fs", tag, len(chunks), time.time() - start)
    return "loaded", len(chunks)


def filings_to_run(ticker: str | None, year: str | None) -> list[tuple[str, str]]:
    config = json.loads(TICKERS_FILE.read_text())
    tickers = [ticker.upper()] if ticker else [t for g in config["tickers"].values() for t in g]
    years = [year] if year else config["years"]
    return [(t, y) for t in tickers for y in years]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ticker", help="e.g. TSLA (default: every ticker in tickers.json)")
    parser.add_argument("--year", help="fiscal year, e.g. 2025 (default: every year in tickers.json)")
    parser.add_argument("--force", action="store_true", help="rebuild filings already loaded")
    args = parser.parse_args()

    setup_logging()
    filings = filings_to_run(args.ticker, args.year)
    log.info("Ingesting %d filing(s)%s", len(filings), " with --force" if args.force else "")
    collection = get_collection(chromadb.PersistentClient(path=str(CHROMA_DIR)))

    results = {}
    for ticker, year in filings:
        try:
            results[(ticker, year)] = ingest_filing(collection, ticker, year, args.force)
        except (urllib.error.URLError, OSError, ValueError) as e:
            log.error("[%s %s] failed: %s", ticker, year, e)
            results[(ticker, year)] = ("failed", 0)

    by_status = {s: [f"{t} {y}" for (t, y), (st, _) in results.items() if st == s]
                 for s in ("loaded", "skipped", "missing", "failed")}
    written = sum(n for _, n in results.values())
    log.info("Summary: %d chunks written; %d in the store in total", written, collection.count())
    for status, names in by_status.items():
        if names:
            log.info("  %-8s %2d  %s", status, len(names), ", ".join(names))
    return 1 if by_status["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
