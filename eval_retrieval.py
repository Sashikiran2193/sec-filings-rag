"""Run a fixed set of questions through retrieve() and save the results.

Usage: python eval_retrieval.py

Writes eval/retrieval_results.md: for each question, the top five chunks with
metadata, distance and the first 400 characters, for reviewing by hand.
"""

from pathlib import Path

from search_10k import TOP_K, companies_in, retrieve

OUT_FILE = Path("eval/retrieval_results.md")

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
    lines = ["# Retrieval results", "", f"Top {TOP_K} chunks from `retrieve()` for each question.", ""]
    for n, question in enumerate(QUESTIONS, start=1):
        tickers = companies_in(question)
        lines += [f"## Q{n}. {question}", "", f"Companies filter: {', '.join(tickers) or 'all'}", ""]
        for rank, hit in enumerate(retrieve(question, TOP_K), start=1):
            text = hit["text"][:400].replace("\n", " / ")
            lines += [
                f"{rank}. **{hit['company']} | {hit['year']} | {hit['section']} {hit['section_title']}**"
                f" | `{hit['id']}` | distance {hit['distance']:.3f}",
                f"   > {text}...",
                "",
            ]
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_FILE} ({len(QUESTIONS)} questions)")


if __name__ == "__main__":
    main()
