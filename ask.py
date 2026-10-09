"""Ask a question about the 10-K filings.

Usage:
  python ask.py "What risks did Tesla list in 2025?"
  python ask.py "How do Ford and GM describe tariff risks?" --year 2025
  python ask.py "question" --ticker F --ticker GM --year 2025 --section "Item 1A" --mode dense

Prints the answer, then the filing sections it cites. Companies, years and
sections named in the question are used as filters automatically (see
search_10k.py); the options override them.

Every question is appended to logs/ask.jsonl: the time, question, filters,
retrieved and cited chunk ids, the answer and how long it took.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

LOG_FILE = Path("logs/ask.jsonl")


def log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    from answer_10k import answer, label
    from search_10k import add_filter_args, describe, filter_kwargs

    parser = argparse.ArgumentParser(description="Ask a question about the 10-K filings.")
    parser.add_argument("question")
    add_filter_args(parser)
    args = parser.parse_args()

    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": args.question,
        "mode": args.mode,
    }
    start = time.perf_counter()
    try:
        result = answer(args.question, **filter_kwargs(args), mode=args.mode)
    except anthropic.AuthenticationError:
        return fail(entry, start, "The API key was rejected. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.APIConnectionError:
        return fail(entry, start, "Couldn't reach the Claude API. Check your internet connection.")
    except anthropic.APIStatusError as e:
        return fail(entry, start, f"The Claude API returned an error ({e.status_code}): {e.message}")
    except TypeError as e:
        if "api_key" in str(e) or "authentication" in str(e).lower():
            return fail(entry, start, "No API key found. Add ANTHROPIC_API_KEY=... to .env (see README).")
        raise
    except RuntimeError as e:  # the model declined, or the answer was cut off
        return fail(entry, start, str(e))
    except Exception as e:
        if "does not exist" in str(e) or "no such table" in str(e):
            return fail(entry, start, "No filings loaded yet. Run: python ingest.py (see README).")
        raise
    seconds = round(time.perf_counter() - start, 2)

    print(f"[{describe(result['filters'])} | search: {args.mode}]\n")
    print(result["answer"])
    if result["cited"]:
        print("\nSources:")
        for c in result["cited"]:
            print(f"  - {label(c)}, chunk {c['chunk']} ({c['id']})")
    print(f"\n({seconds}s)")

    log(entry | {
        "filters": result["filters"],
        "retrieved": [c["id"] for c in result["retrieved"]],
        "cited": [c["id"] for c in result["cited"]],
        "found": result["found"],
        "answer": result["answer"],
        "seconds": seconds,
    })
    return 0


def fail(entry: dict, start: float, message: str) -> int:
    print(message, file=sys.stderr)
    log(entry | {"error": message, "seconds": round(time.perf_counter() - start, 2)})
    return 1


if __name__ == "__main__":
    sys.exit(main())
