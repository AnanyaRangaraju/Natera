"""
main.py
-------
Entry point for the Natera 837 Front-End Claim Validation Suite.

Usage:
    python main.py                          # validate all sample claims
    python main.py --file path/to/claim.837 # validate a single file
    python main.py --csv                    # also export CSV report

Author: Built for Natera front-end claim validation project
"""

import os
import sys
import argparse
from datetime import datetime

from parser_837 import parse_837
from validator import validate_claim
from reporter import format_claim_report, format_batch_summary, export_csv


SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def load_claim_file(filepath: str) -> str:
    """Load raw 837 EDI content from file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def run_validation(claim_text: str, filename: str = "") -> dict:
    """Full pipeline: parse -> validate -> return result."""
    parsed = parse_837(claim_text)
    result = validate_claim(parsed)
    result["source_file"] = os.path.basename(filename)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Natera 837 Front-End Claim Validation Suite"
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Path to a single 837 EDI file to validate"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Export results to CSV in the output/ directory"
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n" + "=" * 72)
    print("  NATERA 837 CLAIM VALIDATION SUITE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    results = []

    if args.file:
        # Single file mode
        if not os.path.exists(args.file):
            print(f"\n  ERROR: File not found: {args.file}")
            sys.exit(1)
        print(f"\n  Validating: {args.file}\n")
        claim_text = load_claim_file(args.file)
        result = run_validation(claim_text, args.file)
        results.append(result)
        print(format_claim_report(result))
    else:
        # Batch mode — all sample claims
        claim_files = sorted([
            f for f in os.listdir(SAMPLE_DIR)
            if f.endswith(".837")
        ])

        if not claim_files:
            print(f"\n  No .837 files found in {SAMPLE_DIR}")
            sys.exit(1)

        print(f"\n  Found {len(claim_files)} claim(s) in sample_data/\n")

        for filename in claim_files:
            filepath = os.path.join(SAMPLE_DIR, filename)
            print(f"  Processing: {filename}")
            claim_text = load_claim_file(filepath)
            result = run_validation(claim_text, filename)
            results.append(result)
            print(format_claim_report(result))

    # Batch summary (only meaningful for multiple claims)
    if len(results) > 1:
        print(format_batch_summary(results))

    # CSV export
    if args.csv and results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(OUTPUT_DIR, f"validation_report_{timestamp}.csv")
        export_csv(results, csv_path)
        print(f"\n  Report saved to: {csv_path}")

    print("\n  Done.\n")


if __name__ == "__main__":
    main()
