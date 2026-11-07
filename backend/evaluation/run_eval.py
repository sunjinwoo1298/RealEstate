"""
Loads eval_dataset.json and prints a summary grouped by category. Intended
as a manual/spot-check harness: LLM reply quality can't be asserted exactly,
so this script surfaces the dataset for a human (or a future LLM-judge) to
review against a running backend, rather than asserting pass/fail itself.

Usage:
    conda activate minor
    python -m backend.evaluation.run_eval
"""
import json
from collections import Counter
from pathlib import Path

DATASET_PATH = Path(__file__).parent / "eval_dataset.json"


def main() -> None:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    cases = dataset["cases"]
    by_category = Counter(c["category"] for c in cases)

    print(f"Loaded {len(cases)} evaluation cases from {DATASET_PATH.name}\n")
    print("By category:")
    for category, count in sorted(by_category.items()):
        print(f"  {category}: {count}")

    print("\nCases:")
    for case in cases:
        print(f"  [{case['id']}] ({case['category']}, {case['language']}) {case['buyer_message']!r}")
        print(f"      expects: {case['expected_behavior']}")


if __name__ == "__main__":
    main()
