"""Split clean 10-K sections into overlapping chunks with metadata.

Usage: python chunk_10k.py

Reads data/clean/<ticker>/<year>/item_<n>.txt and writes data/chunks/chunks.jsonl,
one JSON object per line:
  {"id": "TSLA-2025-1A-003", "ticker": "TSLA", "company": "Tesla, Inc.",
   "year": "2025", "section": "Item 1A", "section_title": "Risk Factors",
   "chunk": 3, "tokens": 642, "text": "..."}

Chunks are built from whole sentences (and whole table rows), so they never
cut a sentence in half. Token counts are estimated at ~4 characters per token.
"""

import json
import re
from collections import Counter
from pathlib import Path

from fetch_10k import company_name

CLEAN_DIR = Path("data/clean")
OUT_FILE = Path("data/chunks/chunks.jsonl")

TARGET_TOKENS = 650  # aim for 500-800
MAX_TOKENS = 800
OVERLAP_TOKENS = 80  # repeated from the end of the previous chunk
MIN_TOKENS = 150  # a smaller last chunk is merged into the one before it
CHARS_PER_TOKEN = 4

SECTION_TITLES = {
    "1": "Business", "1a": "Risk Factors", "1b": "Unresolved Staff Comments",
    "1c": "Cybersecurity", "2": "Properties", "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures", "4a": "Information About Executive Officers",
    "5": "Market for Registrant's Common Equity", "6": "[Reserved]",
    "7": "Management's Discussion and Analysis",
    "7a": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9a": "Controls and Procedures", "9b": "Other Information",
    "9c": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules", "16": "Form 10-K Summary",
}
# Sentence end: ". " / "? " / "! " followed by a capital, digit, quote or bracket.
SENTENCE_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"”)]))\s+(?=[A-Z0-9“\"(])")


def count_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def split_units(text: str) -> list[str]:
    """Break text into sentences; each line (paragraph or table row) ends with "\\n"."""
    units = []
    for line in text.splitlines():
        sentences = [line] if " | " in line else SENTENCE_END.split(line)
        units += [s + " " for s in sentences[:-1]] + [sentences[-1] + "\n"]
    # A single sentence longer than a chunk is cut at word boundaries.
    out = []
    for unit in units:
        while count_tokens(unit) > MAX_TOKENS:
            cut = unit.rfind(" ", 0, TARGET_TOKENS * CHARS_PER_TOKEN)
            cut = cut if cut > 0 else TARGET_TOKENS * CHARS_PER_TOKEN
            out.append(unit[:cut] + " ")
            unit = unit[cut:].lstrip()
        out.append(unit)
    return out


def overlap_tail(units: list[str]) -> list[str]:
    """The last few sentences of a chunk, up to OVERLAP_TOKENS, to repeat in the next."""
    tail: list[str] = []
    for unit in reversed(units):
        if count_tokens("".join(tail) + unit) > OVERLAP_TOKENS:
            break
        tail.insert(0, unit)
    return tail


def chunk_text(text: str) -> list[str]:
    chunks: list[list[str]] = []
    current: list[str] = []
    repeated = 0  # how many units at the start of `current` are overlap
    for unit in split_units(text):
        size = count_tokens("".join(current))
        if current and (size >= TARGET_TOKENS or size + count_tokens(unit) > MAX_TOKENS):
            chunks.append(current)
            current = overlap_tail(current)
            repeated = len(current)
        current.append(unit)

    new_part = current[repeated:]
    if chunks and count_tokens("".join(new_part)) < MIN_TOKENS and count_tokens(
        "".join(chunks[-1] + new_part)
    ) <= MAX_TOKENS + MIN_TOKENS:
        chunks[-1] += new_part  # fold a short tail into the previous chunk
    elif new_part:
        chunks.append(current)
    return ["".join(c).strip() for c in chunks]


def build_chunks() -> list[dict]:
    records = []
    for path in sorted(CLEAN_DIR.glob("*/*/item_*.txt")):
        ticker, year = path.parent.parent.name, path.parent.name
        item = path.stem.removeprefix("item_")
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(text), start=1):
            records.append({
                "id": f"{ticker}-{year}-{item.upper()}-{i:03d}",
                "ticker": ticker,
                "company": company_name(ticker),
                "year": year,
                "section": f"Item {item.upper()}",
                "section_title": SECTION_TITLES[item],
                "chunk": i,
                "tokens": count_tokens(chunk),
                "text": chunk,
            })
    return records


def print_counts(records: list[dict]) -> None:
    by_company = Counter(r["ticker"] for r in records)
    print(f"{'Company':<8} {'Chunks':>7}")
    for ticker, n in sorted(by_company.items()):
        print(f"{ticker:<8} {n:>7}")
    print(f"{'Total':<8} {len(records):>7}\n")

    by_section = Counter(r["section"] for r in records)
    order = {f"Item {k.upper()}": i for i, k in enumerate(SECTION_TITLES)}
    print(f"{'Section':<9} {'Chunks':>7}  Title")
    for section, n in sorted(by_section.items(), key=lambda kv: order[kv[0]]):
        title = SECTION_TITLES[section.removeprefix("Item ").lower()]
        print(f"{section:<9} {n:>7}  {title}")


if __name__ == "__main__":
    records = build_chunks()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} chunks to {OUT_FILE}\n")
    print_counts(records)
