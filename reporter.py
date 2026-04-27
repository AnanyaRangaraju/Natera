"""
reporter.py
-----------
Generates formatted validation reports from claim validation results.
Outputs both human-readable terminal reports and CSV summaries.

Author: Built for Natera front-end claim validation project
"""

import csv
import os
from datetime import datetime
from typing import List


STATUS_ICONS = {
    "PASS": "[PASS]",
    "FAIL": "[FAIL]",
    "WARNING": "[WARN]",
}

RISK_COLORS = {
    "HIGH RISK": "!! HIGH RISK !!",
    "MEDIUM RISK": "~~ MEDIUM RISK ~~",
    "LOW RISK": "** LOW RISK **",
}


def format_claim_report(result: dict) -> str:
    """Format a single claim validation result as a readable report string."""
    lines = []
    sep = "-" * 72

    lines.append(sep)
    lines.append(f"  CLAIM VALIDATION REPORT")
    lines.append(f"  Claim ID   : {result['claim_id']}")
    lines.append(f"  Subscriber : {result['subscriber']}")
    lines.append(f"  Payer      : {result['payer']}")
    lines.append(f"  DOS        : {result['date_of_service']}")
    lines.append(f"  Charge     : ${result['total_charge']:,.2f}")
    lines.append(f"  Risk Level : {RISK_COLORS.get(result['risk_level'], result['risk_level'])}")
    lines.append(sep)

    summary = result["summary"]
    lines.append(
        f"  Rules run: {summary['total_rules']}  |  "
        f"Passed: {summary['passed']}  |  "
        f"Failed: {summary['failed']}  |  "
        f"Warnings: {summary['warnings']}"
    )
    lines.append(sep)

    # Group findings by category
    categories = {}
    for f in result["findings"]:
        cat = f["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    for category, cat_findings in categories.items():
        lines.append(f"\n  [{category}]")
        for f in cat_findings:
            icon = STATUS_ICONS.get(f["status"], f["status"])
            lines.append(f"    {icon}  {f['description']}")
            if f["status"] != "PASS":
                lines.append(f"           Detail: {f['detail']}")
                if f.get("segment"):
                    lines.append(f"           Segment: {f['segment']}")
            else:
                lines.append(f"           {f['detail']}")

    if result.get("parse_errors"):
        lines.append(f"\n  [Parse Errors]")
        for err in result["parse_errors"]:
            lines.append(f"    !! {err}")

    lines.append("\n" + sep)
    return "\n".join(lines)


def format_batch_summary(results: List[dict]) -> str:
    """Format a batch summary across multiple claims."""
    lines = []
    sep = "=" * 72

    total = len(results)
    high_risk = sum(1 for r in results if r["risk_level"] == "HIGH RISK")
    medium_risk = sum(1 for r in results if r["risk_level"] == "MEDIUM RISK")
    low_risk = sum(1 for r in results if r["risk_level"] == "LOW RISK")
    total_charge = sum(r["total_charge"] for r in results)
    total_failed = sum(r["summary"]["failed"] for r in results)
    total_warnings = sum(r["summary"]["warnings"] for r in results)

    lines.append(sep)
    lines.append("  NATERA 837 CLAIM VALIDATION SUITE — BATCH SUMMARY")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(sep)
    lines.append(f"  Claims processed  : {total}")
    lines.append(f"  High risk         : {high_risk}  ({pct(high_risk, total)}% of batch)")
    lines.append(f"  Medium risk       : {medium_risk}  ({pct(medium_risk, total)}% of batch)")
    lines.append(f"  Low risk (clean)  : {low_risk}  ({pct(low_risk, total)}% of batch)")
    lines.append(f"  Clean claim rate  : {pct(low_risk, total)}%")
    lines.append(f"  Total charge      : ${total_charge:,.2f}")
    lines.append(f"  Total rule fails  : {total_failed}")
    lines.append(f"  Total warnings    : {total_warnings}")
    lines.append(sep)

    lines.append("\n  CLAIM-LEVEL RISK SUMMARY:")
    lines.append(f"  {'Claim ID':<14} {'Payer':<18} {'Subscriber':<20} {'Charge':>8} {'Risk':<16} {'Fails':>5} {'Warns':>5}")
    lines.append("  " + "-" * 86)

    for r in results:
        lines.append(
            f"  {r['claim_id']:<14} "
            f"{r['payer'][:16]:<18} "
            f"{r['subscriber'][:18]:<20} "
            f"${r['total_charge']:>7,.0f} "
            f"{r['risk_level']:<16} "
            f"{r['summary']['failed']:>5} "
            f"{r['summary']['warnings']:>5}"
        )

    lines.append(sep)
    lines.append("\n  TOP FAILURE CATEGORIES ACROSS BATCH:")
    category_fails = {}
    for r in results:
        for f in r["findings"]:
            if f["status"] == "FAIL":
                cat = f["category"]
                category_fails[cat] = category_fails.get(cat, 0) + 1

    for cat, count in sorted(category_fails.items(), key=lambda x: -x[1]):
        lines.append(f"    {count:>3}x  {cat}")

    lines.append(sep)
    return "\n".join(lines)


def pct(part, total):
    if total == 0:
        return 0
    return round((part / total) * 100, 1)


def export_csv(results: List[dict], output_path: str):
    """Export validation results to CSV for Excel/Power BI consumption."""
    rows = []
    for r in results:
        for f in r["findings"]:
            rows.append({
                "claim_id": r["claim_id"],
                "payer": r["payer"],
                "subscriber": r["subscriber"],
                "date_of_service": r["date_of_service"],
                "total_charge": r["total_charge"],
                "risk_level": r["risk_level"],
                "rule_id": f["rule_id"],
                "category": f["category"],
                "rule_description": f["description"],
                "status": f["status"],
                "detail": f["detail"],
                "segment": f["segment"],
            })

    if not rows:
        return

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  CSV exported to: {output_path}")
