#!/usr/bin/env python3
"""Report validation progress against the go/no-go gates (docs/customs/08-validation-programme.md).

    python scripts/validation_gates.py --interviews private/interviews.csv [--pilots private/pilots.csv]

Counts only what is recorded in the tracking sheets; it never estimates or fills gaps.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

TARGETS = {"interviews": 15, "countries": 3, "max_country_share": 0.40, "pain": 5, "paid_or_loi": 3, "samples": 50}


def _rows(path: str | Path | None) -> list[dict[str, str]]:
    if not path or not Path(path).is_file():
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if any((v or "").strip() for v in row.values())]


def _int(value: str | None) -> int:
    try:
        return int(float((value or "").strip()))
    except ValueError:
        return 0


def evaluate(interviews: list[dict[str, str]], pilots: list[dict[str, str]]) -> dict:
    n = len(interviews)
    countries = Counter((r.get("country") or "unknown").strip() for r in interviews)
    segments = Counter((r.get("segment") or "unknown").strip() for r in interviews)
    top_share = max(countries.values()) / n if n else 0.0
    pain = sum(1 for r in interviews if _int(r.get("pain_score_0_3")) >= 2 and (r.get("invoice_rank_top3") or "").strip() in {"1", "2", "3"})
    committed = sum(1 for r in interviews if (r.get("pilot_status") or "").strip() in {"loi_signed", "paid"})
    samples = sum(_int(r.get("samples_received")) for r in interviews if (r.get("consent_form_signed") or "").strip().lower() == "yes")
    paid = sum(1 for p in pilots if (p.get("paid") or "").strip().lower() == "yes")
    converted = sum(1 for p in pilots if (p.get("converted_to_subscription") or "").strip().lower() == "yes")
    gates = {
        "interviews": (n, TARGETS["interviews"], n >= TARGETS["interviews"]),
        "countries": (len(countries), TARGETS["countries"], len(countries) >= TARGETS["countries"]),
        "max_country_share": (round(top_share, 2), TARGETS["max_country_share"], n > 0 and top_share <= TARGETS["max_country_share"]),
        "pain_top3_with_score>=2": (pain, TARGETS["pain"], pain >= TARGETS["pain"]),
        "paid_pilot_or_signed_loi": (committed, TARGETS["paid_or_loi"], committed >= TARGETS["paid_or_loi"]),
        "consented_sample_invoices": (samples, TARGETS["samples"], samples >= TARGETS["samples"]),
    }
    return {"gates": gates, "countries": dict(countries), "segments": dict(segments),
            "pilots_paid": paid, "pilots_converted": converted}


def report(result: dict) -> str:
    lines = ["Validation gates (recorded data only)", ""]
    for name, (value, target, ok) in result["gates"].items():
        lines.append(f"  [{'MET' if ok else '   '}] {name:30} {value}  (target {'<=' if 'share' in name else '>='} {target})")
    lines += ["", f"  Countries: {result['countries']}", f"  Segments:  {result['segments']}",
              f"  Pilots paid: {result['pilots_paid']}  converted to subscription: {result['pilots_converted']}",
              "", "  Accuracy and cost gates come from scripts/compare_engines.py (>= 50 consented invoices)."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interviews", default="docs/customs/tracking/interviews.csv")
    parser.add_argument("--pilots", default=None)
    args = parser.parse_args(argv)
    print(report(evaluate(_rows(args.interviews), _rows(args.pilots))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
