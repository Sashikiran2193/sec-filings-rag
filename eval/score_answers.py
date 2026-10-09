"""Turn graded answers into accuracy, citation and refusal numbers.

Usage: python eval/score_answers.py [name]       (default name: baseline)

Reads eval/results/answers_<name>.jsonl (from run_answers.py),
answer_grades_<name>.jsonl (one line per question: grade = correct | partial |
wrong | correct_refusal | wrong_answer_to_no_answer) and citation_check_<name>.json
(from check_citations.py), and writes answer_scores_<name>.json.

  accuracy          questions with an answer graded correct (partial counts half
                    in "accuracy_with_partial")
  citations         numbers in cited claims found in the cited chunks; answers
                    with figures on uncited lines
  refusals          no-answer questions declined (correct refusals), and
                    answerable questions declined (false refusals)
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path("eval/results")


def pct(n: float, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    answers = {r["id"]: r for r in map(json.loads, (RESULTS / f"answers_{name}.jsonl").read_text(encoding="utf-8").splitlines())}
    grades = [json.loads(l) for l in (RESULTS / f"answer_grades_{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    citations = json.loads((RESULTS / f"citation_check_{name}.json").read_text(encoding="utf-8"))

    answerable = [g for g in grades if g["type"] != "no_answer"]
    no_answer = [g for g in grades if g["type"] == "no_answer"]
    by_type = defaultdict(list)
    for g in answerable:
        by_type[g["type"]].append(g)

    def accuracy(gs):
        correct = sum(g["grade"] == "correct" for g in gs)
        partial = sum(g["grade"] == "partial" for g in gs)
        return {"questions": len(gs), "correct": correct, "partial": partial,
                "wrong": len(gs) - correct - partial,
                "accuracy": pct(correct, len(gs)), "accuracy_with_partial": pct(correct + 0.5 * partial, len(gs))}

    false_refusals = [g["id"] for g in answerable if answers[g["id"]]["declined"]]
    cs = citations["summary"]
    uncited = [a["id"] for a in citations["answers"] if a["uncited_lines"]]
    scores = {
        "accuracy": {"overall": accuracy(answerable), **{t: accuracy(by_type[t]) for t in ("fact", "summary", "comparison")}},
        "failure_causes": {cause: sum(g.get("failure_cause") == cause for g in answerable if g["grade"] != "correct")
                           for cause in sorted({g.get("failure_cause") for g in answerable if g["grade"] != "correct"} - {None})},
        "citations": {
            "answers_checked": cs["answers_checked"],
            "numbers_checked": cs["numbers_checked"],
            "numbers_supported_pct": cs["numbers_supported_pct"],
            "answers_with_uncited_figures": len(uncited),
            "answers_with_uncited_figures_ids": uncited,
        },
        "refusals": {
            "no_answer_questions": len(no_answer),
            "correctly_declined": sum(answers[g["id"]]["declined"] for g in no_answer),
            "correct_refusal_rate": pct(sum(answers[g["id"]]["declined"] for g in no_answer), len(no_answer)),
            "false_refusals": len(false_refusals),
            "false_refusal_rate": pct(len(false_refusals), len(answerable)),
            "false_refusal_ids": false_refusals,
        },
    }
    out = RESULTS / f"answer_scores_{name}.json"
    out.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scores, indent=2))
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
