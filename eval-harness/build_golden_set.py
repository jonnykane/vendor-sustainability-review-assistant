"""
Rubric definitions and golden set builder.

The rubric covers the five climate-focused dimensions defined in schemas.py.
Run this script to print the rubric or scaffold an empty annotation template.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Rubric — source of truth for scoring criteria
# ---------------------------------------------------------------------------

RUBRIC_VERSION = "1.0"

RUBRIC: dict[int, dict] = {
    1: {
        "name": "Net Zero commitment and transition plan",
        "description": (
            "Whether the vendor has stated a net zero or carbon neutral target "
            "and provided a credible transition plan with milestones."
        ),
        "criteria": {
            0: (
                "No mention of net zero, carbon neutral, or any climate commitment."
            ),
            1: (
                "General climate ambition stated (e.g. 'we are committed to reducing "
                "our environmental impact') but no net zero target or timeline."
            ),
            2: (
                "Net zero or carbon neutral target stated with a specific year "
                "(e.g. 'net zero by 2040'), but no transition pathway or interim milestones."
            ),
            3: (
                "Net zero target with a credible transition plan: interim milestones, "
                "a named decarbonisation pathway, and board-level accountability stated."
            ),
        },
    },
    2: {
        "name": "Scope 1 & 2 emissions disclosure",
        "description": (
            "Whether the vendor discloses quantified Scope 1 (direct) and Scope 2 "
            "(purchased energy) greenhouse gas emissions."
        ),
        "criteria": {
            0: "No Scope 1 or Scope 2 emissions data reported.",
            1: (
                "Emissions mentioned qualitatively (e.g. 'we measure our carbon "
                "footprint') but no quantified Scope 1 or Scope 2 figures provided."
            ),
            2: (
                "Quantified Scope 1 and/or Scope 2 emissions reported "
                "(absolute tonnes CO₂e or an intensity metric)."
            ),
            3: (
                "Both Scope 1 and Scope 2 (market-based and/or location-based) "
                "disclosed with year-on-year comparison and third-party assurance."
            ),
        },
    },
    3: {
        "name": "Scope 3 emissions disclosure",
        "description": (
            "Whether the vendor discloses quantified Scope 3 (value chain) "
            "emissions across relevant categories."
        ),
        "criteria": {
            0: "No mention of Scope 3 or value chain / supply chain emissions.",
            1: (
                "Scope 3 acknowledged as material or relevant but no quantified "
                "data provided."
            ),
            2: (
                "Scope 3 emissions quantified — at least one material category "
                "disclosed with a figure in tonnes CO₂e."
            ),
            3: (
                "Comprehensive Scope 3 disclosure across material categories, "
                "with methodology note and third-party assurance."
            ),
        },
    },
    4: {
        "name": "Third-party verification and assurance",
        "description": (
            "Whether the vendor's emissions or sustainability data has been "
            "independently verified or assured by a named third party."
        ),
        "criteria": {
            0: "No external verification, assurance, or audit of any kind mentioned.",
            1: (
                "External review or audit mentioned vaguely; no named standard, "
                "named assurer, or defined scope."
            ),
            2: (
                "Third-party limited assurance of GHG data to a named standard "
                "(e.g. ISAE 3000, ISO 14064-3); assurer named."
            ),
            3: (
                "Reasonable assurance of emissions data to a named standard; "
                "assurance statement published and named auditor identified."
            ),
        },
    },
    5: {
        "name": "Science-based targets validation",
        "description": (
            "Whether the vendor has committed to or received validation of "
            "science-based emissions reduction targets (SBTi or equivalent)."
        ),
        "criteria": {
            0: "No mention of science-based targets, SBTi, or 1.5 °C alignment.",
            1: (
                "SBTi or science-based targets mentioned as an aspiration or "
                "intention to set targets, but no commitment letter or submission."
            ),
            2: (
                "SBTi commitment letter signed, or targets submitted for validation, "
                "but validation not yet confirmed."
            ),
            3: (
                "SBTi-validated targets in place (near-term and/or long-term, "
                "1.5 °C aligned) with progress against those targets reported."
            ),
        },
    },
}

DIMENSION_IDS = list(RUBRIC.keys())  # [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Golden set scaffold builder
# ---------------------------------------------------------------------------

def build_scaffold(vendor_names: list[str]) -> dict:
    """Return an empty annotation template ready for human scoring."""
    return {
        "version": "v1",
        "rubric_version": RUBRIC_VERSION,
        "created_date": date.today().isoformat(),
        "description": (
            "Human-annotated ground truth for vendor sustainability scoring eval. "
            "Fill in expected_score (0–3) and acceptable_range for each dimension."
        ),
        "entries": [
            {
                "vendor_name": name,
                "annotator": "",
                "annotation_date": "",
                "notes": "",
                "dimensions": {
                    str(dim_id): {
                        "name": RUBRIC[dim_id]["name"],
                        "expected_score": None,
                        "acceptable_range": [None, None],
                        "key_evidence_hint": "",
                        "notes": "",
                    }
                    for dim_id in DIMENSION_IDS
                },
            }
            for name in vendor_names
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_rubric() -> None:
    print("=" * 70)
    print(f"VENDOR SUSTAINABILITY SCORING RUBRIC  (version {RUBRIC_VERSION})")
    print("=" * 70)
    for dim_id, dim in RUBRIC.items():
        print(f"\nDimension {dim_id}: {dim['name']}")
        print(f"  {dim['description']}")
        for score, criteria in dim["criteria"].items():
            print(f"  [{score}] {criteria}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Print the scoring rubric or scaffold a golden set template."
    )
    parser.add_argument(
        "--print-rubric", action="store_true", help="Print the full rubric to stdout."
    )
    parser.add_argument(
        "--scaffold",
        metavar="OUTPUT",
        help="Write an empty annotation template JSON to OUTPUT.",
    )
    parser.add_argument(
        "--vendors",
        nargs="+",
        default=[
            "Microsoft",
            "Sentinel Records",
            "Archive NI",
            "BoxVault",
            "Heritage",
        ],
        help="Vendor names to include in the scaffold.",
    )
    args = parser.parse_args()

    if args.print_rubric:
        _print_rubric()

    if args.scaffold:
        out = Path(args.scaffold)
        template = build_scaffold(args.vendors)
        out.write_text(json.dumps(template, indent=2))
        print(f"Scaffold written to {out}")

    if not args.print_rubric and not args.scaffold:
        parser.print_help()
        sys.exit(1)
