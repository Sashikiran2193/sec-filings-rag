"""Check eval/questions.jsonl against the filings.

Usage: python eval/validate_questions.py

Each line of questions.jsonl is one question:
  id               "F01" (F = fact, S = summary, C = comparison, N = no answer)
  type             fact | summary | comparison | no_answer
  question         the question as a user would ask it
  expected_answer  the verified answer ("Not found in the filings." for no_answer)
  key_facts        strings a correct answer must contain; "a|b" means a or b
  sources          [{ticker, year, section, quote}]: where the answer is, with an
                   exact quote from that section of the cleaned filing
  note             optional; for no_answer, how the absence was checked

This checks that every answered question has at least one source, that every
quote appears word for word in data/clean/<ticker>/<year>/ for its section,
that every key fact appears in the expected answer or a quote, and that
no_answer questions have no sources and explain how absence was checked.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

QUESTIONS = Path("eval/questions.jsonl")
CLEAN_DIR = Path("data/clean")
TYPES = {"fact", "summary", "comparison", "no_answer"}
NOT_FOUND = "Not found in the filings."


def section_file(ticker: str, year: str, section: str) -> Path:
    item = "signatures" if section == "Signature page" else section.removeprefix("Item ").lower()
    return CLEAN_DIR / ticker / year / f"item_{item}.txt"


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check(q: dict) -> list[str]:
    errors = []
    for field in ("id", "type", "question", "expected_answer", "key_facts", "sources"):
        if field not in q:
            errors.append(f"missing field {field!r}")
    if errors:
        return errors
    if q["type"] not in TYPES:
        errors.append(f"unknown type {q['type']!r}")

    if q["type"] == "no_answer":
        if q["expected_answer"] != NOT_FOUND:
            errors.append(f"expected_answer should be {NOT_FOUND!r}")
        if q["sources"]:
            errors.append("no_answer question has sources")
        if not q.get("note"):
            errors.append("no_answer question needs a note on how absence was checked")
        return errors

    if not q["sources"]:
        errors.append("no sources")
    if not q["key_facts"]:
        errors.append("no key_facts")
    quotes = []
    for s in q["sources"]:
        path = section_file(s["ticker"], s["year"], s["section"])
        if not path.exists():
            errors.append(f"section file not found: {path}")
            continue
        if normalize(s["quote"]) not in normalize(path.read_text(encoding="utf-8")):
            errors.append(f"quote not in {path}: {s['quote'][:60]!r}")
        quotes.append(s["quote"])
    evidence = normalize(" ".join([q["expected_answer"], *quotes]))
    for fact in q["key_facts"]:
        if not any(alt in evidence for alt in fact.split("|")):
            errors.append(f"key fact {fact!r} not in the expected answer or a quote")
    return errors


def main() -> int:
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = Counter(q.get("id") for q in questions)
    failed = 0
    for q in questions:
        errors = check(q)
        if ids[q.get("id")] > 1:
            errors.append("duplicate id")
        if errors:
            failed += 1
            for e in errors:
                print(f"{q.get('id')}: {e}")

    types = Counter(q.get("type") for q in questions)
    sections = Counter(s["section"] for q in questions for s in q.get("sources", []))
    companies = Counter(s["ticker"] for q in questions for s in q.get("sources", []))
    print(f"\n{len(questions)} questions: " + ", ".join(f"{n} {t}" for t, n in types.most_common()))
    print(f"{sum(sections.values())} source quotes from {len(companies)} companies, sections: "
          + ", ".join(f"{s} ×{n}" for s, n in sections.most_common()))
    print("OK: every question has a verified answer and a source section" if not failed
          else f"FAILED: {failed} question(s) have problems")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
