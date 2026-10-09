"""Check that each cited claim's numbers appear in the chunks it cites.

Usage: python eval/check_citations.py [eval/results/answers_baseline.jsonl]

Splits each raw answer into claims: the text before each citation group such
as [S2] or [S1][S4]. For every number in a claim (amounts, counts,
percentages; not years or day-of-month numbers) it checks the same value
appears in at least one cited chunk. Values are compared after applying
"thousand/million/billion", and a chunk's bare numbers are also tried scaled
by 1,000, 1,000,000 and 1,000,000,000, since filings' tables are often "in thousands",
"in millions" or "in billions". So "$3,100 million" matches "3.1 billion", and "169,000"
matches a "169" in a table in thousands.

Also flags lines that state numbers without citing anything. Claims without
numbers can't be checked this way; they're counted and left to a human review.
Prints a summary and writes eval/results/citation_check_<name>.json.
"""

import json
import re
import sys
from pathlib import Path

SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
# A number ("2,863", "2.9") and its unit, if any. Not part of "10-K", and no trailing comma.
NUMBER = re.compile(
    r"(?<![\w.])(\d(?:[\d,]*\d)?(?:\.\d+)?)(?!-[KQ]\b)(\s*%|\s*(?:thousand|million|billion|trillion)\b)?",
    re.IGNORECASE,
)
CITATION_GROUP = re.compile(r"((?:\[S\d+(?:\s*[,;]\s*S\d+)*\]\s*)+)")
MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"


def numbers(text: str, from_answer: bool) -> list[tuple[str, float, float]]:
    """(as written, value, rounding allowance) for each number.

    Skips years, "10-K" and the day in dates like 'December 31'. The allowance is
    half the last written digit, so "$2.9 billion" matches 2,863 (million).
    """
    text = re.sub(rf"{MONTHS}\s+\d{{1,2}}", " ", text)
    out = []
    for m in NUMBER.finditer(text):
        digits, unit = m.group(1), (m.group(2) or "").strip().lower()
        try:
            v = float(digits.replace(",", ""))
        except ValueError:
            continue
        if not unit and re.fullmatch(r"(19|20)\d\d", digits):
            continue  # a year
        if from_answer and not unit and v < 10:
            continue  # "3 chunks", list numbering, item numbers
        scale = SCALE.get(unit, 1)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        out.append((m.group(0).strip(), v * scale, 0.5 * 10 ** -decimals * scale))
    return out


def candidates(chunk_text: str) -> set[float]:
    vals = set()
    for _, v, _ in numbers(chunk_text, from_answer=False):
        vals |= {v, v * 1e3, v * 1e6, v * 1e9}
    return vals


def supported(value: float, allowance: float, cands: set[float]) -> bool:
    return any(abs(value - c) <= max(allowance, 0.002 * abs(value)) for c in cands)


def claims(raw: str) -> list[tuple[str, list[int]]]:
    """(claim text, cited source numbers) for each citation group, line by line."""
    out = []
    for line in raw.splitlines():
        pos = 0
        for m in CITATION_GROUP.finditer(line):
            refs = [int(n) for n in re.findall(r"S(\d+)", m.group(1))]
            out.append((line[pos:m.start()].strip(" -*•:"), refs))
            pos = m.end()
    return out


def check(row: dict) -> dict:
    texts = {i: row["cited_text"].get(cid, "") for i, cid in enumerate(row["retrieved"], start=1)}
    result = {"id": row["id"], "claims": 0, "claims_with_numbers": 0, "numbers": 0, "unsupported": [], "uncited_lines": []}
    for claim, refs in claims(row["raw_answer"]):
        result["claims"] += 1
        nums = numbers(claim, from_answer=True)
        if not nums:
            continue
        result["claims_with_numbers"] += 1
        cands = set().union(*(candidates(texts.get(r, "")) for r in refs)) if refs else set()
        for written, value, allowance in nums:
            result["numbers"] += 1
            if not supported(value, allowance, cands):
                result["unsupported"].append({"number": written, "cites": [f"S{r}" for r in refs], "claim": claim[:160]})
    for line in row["raw_answer"].splitlines():
        if not CITATION_GROUP.search(line) and numbers(line, from_answer=True) and not line.lower().startswith("not in the excerpts"):
            result["uncited_lines"].append(line.strip()[:160])
    return result


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/results/answers_baseline.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    answered = [r for r in rows if not r["declined"]]
    results = [check(r) for r in answered]

    total_numbers = sum(r["numbers"] for r in results)
    unsupported = sum(len(r["unsupported"]) for r in results)
    flagged = [r for r in results if r["unsupported"] or r["uncited_lines"]]
    summary = {
        "answers_checked": len(results),
        "claims": sum(r["claims"] for r in results),
        "claims_with_numbers": sum(r["claims_with_numbers"] for r in results),
        "numbers_checked": total_numbers,
        "numbers_supported_pct": round(100 * (total_numbers - unsupported) / total_numbers, 1) if total_numbers else None,
        "answers_with_no_flags": len(results) - len(flagged),
    }
    out = path.with_name(path.name.replace("answers_", "citation_check_").replace(".jsonl", ".json"))
    out.write_text(json.dumps({"summary": summary, "answers": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    for r in flagged:
        for u in r["unsupported"]:
            print(f"{r['id']}: {u['number']} not in {','.join(u['cites'])} | {u['claim']}")
        for line in r["uncited_lines"]:
            print(f"{r['id']}: numbers without a citation | {line}")
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
