"""Run a fixed set of questions through retrieve() and save the results.

Usage:
  python eval_retrieval.py                 hybrid search (the default) -> eval/retrieval_results.md
  python eval_retrieval.py --mode dense    meaning-only search -> eval/retrieval_results_dense.md

For each question, writes the chunks retrieve() returns (top five, or two per
company for questions about several companies) with metadata, distance and the
first 400 characters, for reviewing by hand.
"""

import argparse
from pathlib import Path

from search_10k import TOP_K, companies_in, retrieve

OUT_FILES = {"hybrid": Path("eval/retrieval_results.md"), "dense": Path("eval/retrieval_results_dense.md")}

QUESTIONS = [
    "What supply chain risks does Tesla describe?",
    "How much did Microsoft's Intelligent Cloud revenue grow in fiscal 2025?",
    "What restructuring charges did Ford record in Europe in 2025?",
    "How do Ford and GM describe the risks of the transition to electric vehicles?",
    "What does NVIDIA say about export controls on sales to China?",
    "How many employees does Amazon have?",
    "What was Alphabet's total revenue in 2025?",
    "Which companies describe tariffs as a risk to their business?",
    "How does Snowflake manage cybersecurity risk and who oversees it?",
    "What is Rivian's joint venture with Volkswagen?",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=OUT_FILES, default="hybrid")
    mode = parser.parse_args().mode
    out_file = OUT_FILES[mode]

    lines = ["# Retrieval results", "", f'Chunks from `retrieve(question, {TOP_K}, mode="{mode}")` for each question.', ""]
    for n, question in enumerate(QUESTIONS, start=1):
        tickers = companies_in(question)
        lines += [f"## Q{n}. {question}", "", f"Companies filter: {', '.join(tickers) or 'all'}", ""]
        for rank, hit in enumerate(retrieve(question, TOP_K, mode=mode), start=1):
            text = hit["text"][:400].replace("\n", " / ")
            lines += [
                f"{rank}. **{hit['company']} | {hit['year']} | {hit['section']} {hit['section_title']}**"
                f" | `{hit['id']}` | distance {hit['distance']:.3f}",
                f"   > {text}...",
                "",
            ]
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_file} ({len(QUESTIONS)} questions)")


if __name__ == "__main__":
    main()
