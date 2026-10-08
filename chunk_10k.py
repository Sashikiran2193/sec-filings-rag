"""Split clean 10-K sections into overlapping chunks with metadata.

Usage: python chunk_10k.py

Reads data/clean/<ticker>/<year>/item_<n>.txt and writes data/chunks/chunks.jsonl,
one JSON object per line:
  {"id": "TSLA-2025-1A-003", "ticker": "TSLA", "company": "Tesla, Inc.",
   "year": "2025", "section": "Item 1A", "section_title": "Risk Factors",
   "chunk": 3, "tokens": 412, "text": "..."}

Chunks are built from whole sentences (and whole table rows), so they never
cut a sentence in half. Tokens are counted with the embedding model's own
tokenizer (BAAI/bge-small-en-v1.5), and chunks are kept under its 512-token
input limit so nothing is cut off when they are embedded.
"""

import json
import re
from collections import Counter
from functools import cache
from pathlib import Path

from tokenizers import Tokenizer

from fetch_10k import company_name

CLEAN_DIR = Path("data/clean")
OUT_FILE = Path("data/chunks/chunks.jsonl")

TOKENIZER_MODEL = "BAAI/bge-small-en-v1.5"
TARGET_TOKENS = 380  # aim for 300-480
# Hard limit. The model reads 512 tokens: 2 special ones, up to ~30 for the
# company/section header embed_10k.py adds, and the chunk itself.
MAX_TOKENS = 480
OVERLAP_TOKENS = 50  # repeated from the end of the previous chunk
MIN_TOKENS = 100  # a smaller last chunk is merged into the one before it, if it fits

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
    "signatures": "(officers and directors who signed the report)",
}


def section_name(item: str) -> str:
    """ "1a" -> "Item 1A"; the signature page isn't a numbered item."""
    return "Signature page" if item == "signatures" else f"Item {item.upper()}"
# Sentence end: ". " / "? " / "! " followed by a capital, digit, quote or bracket.
SENTENCE_END = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"”)]))\s+(?=[A-Z0-9“\"(])")


@cache
def tokenizer() -> Tokenizer:
    tok = Tokenizer.from_pretrained(TOKENIZER_MODEL)
    tok.no_truncation()
    return tok


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


def split_long(unit: str) -> list[str]:
    """Cut a sentence longer than MAX_TOKENS into pieces at word boundaries."""
    pieces = []
    while count_tokens(unit) > MAX_TOKENS:
        offsets = tokenizer().encode(unit, add_special_tokens=False).offsets
        limit = offsets[TARGET_TOKENS][0]  # character position of token TARGET_TOKENS
        cut = unit.rfind(" ", 0, limit)
        cut = cut if cut > 0 else limit
        pieces.append(unit[:cut] + " ")
        unit = unit[cut:].lstrip()
    return pieces + [unit]


def split_units(text: str) -> list[tuple[str, int]]:
    """Break text into (sentence, token count); each line ends with "\\n"."""
    units = []
    for line in text.splitlines():
        sentences = [line] if " | " in line else SENTENCE_END.split(line)
        units += [s + " " for s in sentences[:-1]] + [sentences[-1] + "\n"]
    units = [piece for unit in units for piece in split_long(unit)]
    counts = tokenizer().encode_batch(units, add_special_tokens=False)
    return [(u, len(c.ids)) for u, c in zip(units, counts)]


def overlap_tail(units: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """The last few sentences of a chunk, up to OVERLAP_TOKENS, to repeat in the next."""
    tail: list[tuple[str, int]] = []
    for unit in reversed(units):
        if sum(n for _, n in tail) + unit[1] > OVERLAP_TOKENS:
            break
        tail.insert(0, unit)
    return tail


def chunk_text(text: str) -> list[str]:
    chunks: list[list[tuple[str, int]]] = []
    current: list[tuple[str, int]] = []
    size = 0
    repeated = 0  # how many units at the start of `current` are overlap
    for unit in split_units(text):
        if current and (size >= TARGET_TOKENS or size + unit[1] > MAX_TOKENS):
            chunks.append(current)
            current = overlap_tail(current)
            size = sum(n for _, n in current)
            if size + unit[1] > MAX_TOKENS:  # no room for overlap before a long sentence
                current, size = [], 0
            repeated = len(current)
        current.append(unit)
        size += unit[1]

    new_part = current[repeated:]
    new_size = sum(n for _, n in new_part)
    if chunks and new_size < MIN_TOKENS and sum(n for _, n in chunks[-1]) + new_size <= MAX_TOKENS:
        chunks[-1] += new_part  # fold a short tail into the previous chunk
    elif new_part:
        chunks.append(current)
    return ["".join(u for u, _ in c).strip() for c in chunks]


def chunk_filing(ticker: str, year: str) -> list[dict]:
    """Chunk every section of one filing in data/clean/<ticker>/<year>/."""
    records = []
    company = company_name(ticker)
    for path in sorted((CLEAN_DIR / ticker / year).glob("item_*.txt")):
        item = path.stem.removeprefix("item_")
        text = path.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(text), start=1):
            records.append({
                "id": f"{ticker}-{year}-{item.upper()}-{i:03d}",
                "ticker": ticker,
                "company": company,
                "year": year,
                "section": section_name(item),
                "section_title": SECTION_TITLES[item],
                "chunk": i,
                "tokens": count_tokens(chunk),
                "text": chunk,
            })
    return records


def build_chunks() -> list[dict]:
    filings = sorted({(p.parent.name, p.name) for p in CLEAN_DIR.glob("*/*") if p.is_dir()})
    return [r for ticker, year in filings for r in chunk_filing(ticker, year)]


def save_filing_chunks(ticker: str, year: str, records: list[dict]) -> None:
    """Replace one filing's lines in chunks.jsonl, keeping every other filing's."""
    kept = []
    if OUT_FILE.exists():
        with OUT_FILE.open(encoding="utf-8") as f:
            kept = [l for l in f if not l.startswith(f'{{"id": "{ticker}-{year}-')]
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        f.writelines(kept)
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def print_counts(records: list[dict]) -> None:
    by_company = Counter(r["ticker"] for r in records)
    print(f"{'Company':<8} {'Chunks':>7}")
    for ticker, n in sorted(by_company.items()):
        print(f"{ticker:<8} {n:>7}")
    print(f"{'Total':<8} {len(records):>7}\n")

    by_section = Counter(r["section"] for r in records)
    print(f"{'Section':<14} {'Chunks':>7}  Title")
    for item, title in SECTION_TITLES.items():
        if section_name(item) in by_section:
            print(f"{section_name(item):<14} {by_section[section_name(item)]:>7}  {title}")


if __name__ == "__main__":
    records = build_chunks()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} chunks to {OUT_FILE}\n")
    print_counts(records)
