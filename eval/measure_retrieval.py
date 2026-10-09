"""Measure retrieval on the test set: is the right section in the top results?

Usage:
  python eval/measure_retrieval.py                      hybrid search, top 5 -> eval/results/retrieval_hybrid.json
  python eval/measure_retrieval.py --mode dense         vector search only
  python eval/measure_retrieval.py --k 8 --name k8      top 8 (what answer() passes the model)

Runs every question in eval/questions.jsonl through search_10k.retrieve() only;
no model calls. For each question with an answer it records:

  hit          a top-k chunk comes from a correct section: the company and 10-K
               section of one of the question's sources, any fiscal year
               (the headline number)
  hit_year     the same, but the fiscal year must match too
  hit_all      every source's company and section is hit (differs from hit only
               for questions with several sources, mostly comparisons)
  quote_found  the exact quote holding the answer is in a top-k chunk

Questions of type no_answer have no correct section; they're counted
separately and left out of the rates. Comparisons can return more than k chunks
(each company gets a share); only the first k are scored.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from search_10k import retrieve  # noqa: E402

QUESTIONS = Path("eval/questions.jsonl")
RESULTS_DIR = Path("eval/results")
METRICS = ["hit", "hit_year", "hit_all", "quote_found"]
TYPES = ["fact", "summary", "comparison"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def score(q: dict, chunks: list[dict]) -> dict:
    found = {(c["ticker"], c["section"]) for c in chunks}
    found_year = {(c["ticker"], c["year"], c["section"]) for c in chunks}
    text = normalize(" ".join(c["text"] for c in chunks))
    sources = q["sources"]
    return {
        "hit": any((s["ticker"], s["section"]) in found for s in sources),
        "hit_year": any((s["ticker"], s["year"], s["section"]) in found_year for s in sources),
        "hit_all": all((s["ticker"], s["section"]) in found for s in sources),
        "quote_found": any(normalize(s["quote"]) in text for s in sources),
    }


def rate(rows: list[dict], metric: str) -> float:
    return round(100 * sum(r[metric] for r in rows) / len(rows), 1) if rows else 0.0


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mode", choices=["hybrid", "dense"], default="hybrid")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--name", help="results file name (default: the mode, plus k if not 5)")
    args = parser.parse_args()
    name = args.name or (args.mode if args.k == 5 else f"{args.mode}_k{args.k}")

    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows, no_answer = [], []
    start = time.perf_counter()
    for q in questions:
        chunks = retrieve(q["question"], args.k, mode=args.mode)[: args.k]
        if q["type"] == "no_answer":
            no_answer.append({"id": q["id"], "retrieved": [c["id"] for c in chunks]})
            continue
        rows.append({
            "id": q["id"], "type": q["type"], "question": q["question"],
            **score(q, chunks),
            "expected": [f'{s["ticker"]} {s["year"]} {s["section"]}' for s in q["sources"]],
            "retrieved": [f'{c["id"]} ({c["section"]})' for c in chunks],
        })
    seconds = round(time.perf_counter() - start, 1)

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
    summary = {
        "overall": {"questions": len(rows), **{m: rate(rows, m) for m in METRICS}},
        "by_type": {t: {"questions": len(by_type[t]), **{m: rate(by_type[t], m) for m in METRICS}} for t in TYPES},
    }
    result = {
        "run": {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": git_commit(), "mode": args.mode, "k": args.k,
            "questions_file": str(QUESTIONS), "seconds": seconds,
        },
        "summary": summary,
        "misses": [r["id"] for r in rows if not r["hit"]],
        "questions": rows,
        "no_answer": no_answer,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"retrieval_{name}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Retrieval, mode={args.mode}, top {args.k}: {len(rows)} questions with answers "
          f"(+{len(no_answer)} no-answer, not scored), {seconds}s\n")
    print(f"{'':12} {'n':>3}  {'hit':>6}  {'hit_year':>8}  {'hit_all':>7}  {'quote':>6}")
    for label, s in [("overall", summary["overall"]), *summary["by_type"].items()]:
        print(f"{label:12} {s['questions']:>3}  {s['hit']:>5}%  {s['hit_year']:>7}%  {s['hit_all']:>6}%  {s['quote_found']:>5}%")
    print(f"\nMissed (no correct section in top {args.k}): {', '.join(result['misses']) or 'none'}")
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
