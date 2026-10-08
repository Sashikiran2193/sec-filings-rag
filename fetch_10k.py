"""Download 10-K filings from SEC EDGAR.

Usage:
  python fetch_10k.py <ticker> <year>   download one 10-K
  python fetch_10k.py                   download every ticker/year in tickers.json

Saves to data/raw/<ticker>/<year>/<primaryDocument>. The year is the fiscal
year from the filing's report date, not the date it was filed.
"""

import json
import sys
import time
import urllib.request
from functools import cache
from pathlib import Path

HEADERS = {"User-Agent": "Sashikiran Vairavan Sashi.kiran.211993@gmail.com"}
REQUEST_DELAY = 0.2  # seconds; SEC limit is 10 requests/second
TICKERS_FILE = Path("tickers.json")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    time.sleep(REQUEST_DELAY)
    return data


@cache
def ticker_to_cik() -> dict[str, int]:
    tickers = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
    return {entry["ticker"].upper(): entry["cik_str"] for entry in tickers.values()}


def lookup_cik(ticker: str) -> int:
    try:
        return ticker_to_cik()[ticker.upper()]
    except KeyError:
        raise ValueError(f"Ticker not found: {ticker}") from None


@cache
def recent_filings(cik: int) -> dict:
    subs = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    return subs["filings"]["recent"]


def find_10k(cik: int, year: str) -> tuple[str, str]:
    """Return (accession number, primary document) for the 10-K of the given report year."""
    recent = recent_filings(cik)
    for form, accession, doc, report_date in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], recent["reportDate"]
    ):
        if form == "10-K" and report_date.startswith(year):
            return accession, doc
    raise ValueError(f"No 10-K with report date in {year} for CIK {cik}")


def fetch_10k(ticker: str, year: str) -> Path:
    cik = lookup_cik(ticker)
    accession, doc = find_10k(cik, year)

    out_dir = Path("data/raw") / ticker.upper() / year
    out_path = out_dir / doc
    if out_path.exists():
        return out_path

    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(get(url))
    return out_path


def fetch_all() -> None:
    config = json.loads(TICKERS_FILE.read_text())
    tickers = [t for group in config["tickers"].values() for t in group]
    for ticker in tickers:
        for year in config["years"]:
            try:
                print(f"{ticker} {year}: saved {fetch_10k(ticker, year)}")
            except ValueError as e:
                print(f"{ticker} {year}: skipped ({e})")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        fetch_all()
    elif len(sys.argv) == 3:
        print(f"Saved {fetch_10k(sys.argv[1], sys.argv[2])}")
    else:
        sys.exit("Usage: python fetch_10k.py [<ticker> <year>]")
