"""Run every test question through the full pipeline and save the answers.

Usage:
  python eval/run_answers.py                  -> eval/results/answers_baseline.jsonl
  python eval/run_answers.py --name after_x   -> eval/results/answers_after_x.jsonl

Calls answer_10k.answer() for each question in eval/questions.jsonl (about a
few cents each) and saves, per question: the answer, the raw answer with [S1]
style citations, whether it declined, the retrieved and cited chunk ids, the
cited chunks' text (so citations can be checked later even if the chunks
change), the model, tokens and time.

It also records key_facts_found, an automatic check of which of the
question's key facts appear in the answer (numbers compared by value, so
"$3,100 million" matches "3.1 billion"). That's an aid for grading, not the
grade: grades are recorded separately in eval/results/answer_grades.jsonl.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from answer_10k import answer  # noqa: E402

QUESTIONS = Path("eval/questions.jsonl")
RESULTS_DIR = Path("eval/results")
SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
NUMBER = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|trillion)?", re.IGNORECASE)


def values(text: str) -> set[float]:
    """Numbers in text, each with its stated scale applied ("3.1 billion" -> 3.1e9)."""
    out = set()
    for digits, unit in NUMBER.findall(text):
        try:
            v = float(digits.replace(",", ""))
        except ValueError:
            continue
        out.add(v * SCALE[unit.lower()] if unit else v)
    return out


def fact_found(fact: str, text: str) -> bool:
    """A key fact ("a|b" = either) is in the text, as words or as the same number."""
    for alt in fact.split("|"):
        if alt.lower() in text.lower():
            return True
        wanted = values(alt)
        if wanted and all(any(abs(w - v) <= 0.005 * max(w, 1) for v in values(text)) for w in wanted):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--name", default="baseline")
    args = parser.parse_args()
    out = RESULTS_DIR / f"answers_{args.name}.jsonl"

    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for n, q in enumerate(questions, start=1):
            start = time.perf_counter()
            r = answer(q["question"])
            seconds = round(time.perf_counter() - start, 2)
            row = {
                "id": q["id"], "type": q["type"], "question": q["question"],
                "expected_answer": q["expected_answer"],
                "answer": r["answer"], "raw_answer": r.get("raw_answer", r["answer"]),
                "declined": not r["found"],
                "key_facts_found": {fact: fact_found(fact, r["answer"]) for fact in q["key_facts"]},
                "filters": r["filters"],
                "retrieved": [c["id"] for c in r["retrieved"]],
                "cited": [c["id"] for c in r["cited"]],
                "cited_text": {c["id"]: c["text"] for c in r["cited"]},
                "model": r.get("model"), "usage": r.get("usage"), "seconds": seconds,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            status = "declined" if row["declined"] else f"{sum(row['key_facts_found'].values())}/{len(q['key_facts'])} key facts"
            print(f"[{n:>2}/{len(questions)}] {q['id']} {status} ({seconds}s)", flush=True)
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
