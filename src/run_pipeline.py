#!/usr/bin/env python3
"""
Run the scoring pipeline across all vendors in data/vendors/.

Each vendor's scorecard is saved to scores/<vendor_id>.json.
A single ModelRun covering all vendors is saved to runs/<run_id>.json.

Usage:
    python src/run_pipeline.py
    python src/run_pipeline.py --model claude-sonnet-4-6
    python src/run_pipeline.py --run-id "2026-05-02_v0-naive_pilot"
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

# Resolve eval-harness imports
_EVAL_HARNESS = Path(__file__).resolve().parent.parent / "eval-harness"
sys.path.insert(0, str(_EVAL_HARNESS))

# Resolve src imports
_SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(_SRC))

from schemas import ModelRun  # noqa: E402
from build_golden_set import RUBRIC_VERSION  # noqa: E402
from io_scorecards import save_scorecard, save_model_run  # noqa: E402
from score_vendor import _score_full, DEFAULT_MODEL, PIPELINE_VERSION, PROMPT_VERSION  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDORS_DIR = PROJECT_ROOT / "data" / "vendors"
SCORES_DIR = PROJECT_ROOT / "scores"
RUNS_DIR = PROJECT_ROOT / "runs"

SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm"}


def _find_document(vendor_dir: Path) -> Path | None:
    for ext in SUPPORTED_EXTENSIONS:
        matches = sorted(vendor_dir.glob(f"*{ext}"))
        if matches:
            return matches[0]
    return None


def run_pipeline(
    vendors_dir: Path = VENDORS_DIR,
    scores_dir: Path = SCORES_DIR,
    runs_dir: Path = RUNS_DIR,
    model: str = DEFAULT_MODEL,
    run_id: str | None = None,
    pipeline_version: str = PIPELINE_VERSION,
    prompt_version: str = PROMPT_VERSION,
) -> ModelRun:
    runs_dir.mkdir(parents=True, exist_ok=True)

    vendor_dirs = sorted(d for d in vendors_dir.iterdir() if d.is_dir())
    print(
        f"Vendors found: {len(vendor_dirs)} "
        f"({', '.join(d.name for d in vendor_dirs)})"
    )
    print(f"Model: {model}\n")

    all_scorecards = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_duration = 0.0
    errors: list[str] = []

    for vendor_dir in vendor_dirs:
        vendor_id = vendor_dir.name
        vendor_name = vendor_id.replace("_", " ").title()
        doc_path = _find_document(vendor_dir)

        if doc_path is None:
            msg = f"[SKIP] {vendor_name}: no supported document in {vendor_dir}"
            print(msg)
            errors.append(msg)
            continue

        print(f"[{vendor_id}] Scoring {vendor_name} ({doc_path.name}) ...")
        try:
            result = _score_full(
                doc_path,
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                model=model,
            )
        except Exception as exc:
            msg = f"  ERROR scoring {vendor_name}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)
            continue

        sc = result.scorecard
        save_scorecard(sc, scores_dir / f"{vendor_id}.json")

        total_input_tokens += result.input_tokens
        total_output_tokens += result.output_tokens
        total_duration += result.duration_seconds
        all_scorecards.append(sc)

        print(
            f"  Score: {sc.total_score}/{sc.max_score}  |  "
            f"Evidence: {sc.evidence_quality_flag}  |  "
            f"Tokens: {result.input_tokens}in/{result.output_tokens}out  |  "
            f"{result.duration_seconds}s"
        )

    effective_run_id = run_id or (
        f"{date.today().isoformat()}_{pipeline_version}_{model}"
    )

    notes_parts = [
        f"Scored {len(all_scorecards)}/{len(vendor_dirs)} vendors.",
        f"Total tokens: {total_input_tokens}in / {total_output_tokens}out.",
        f"Total duration: {round(total_duration, 1)}s.",
    ]
    if errors:
        notes_parts.append(f"Errors: {'; '.join(errors)}")

    run = ModelRun(
        run_id=effective_run_id,
        pipeline_version=pipeline_version,
        model=model,
        prompt_version=prompt_version,
        run_date=date.today().isoformat(),
        rubric_version=RUBRIC_VERSION,
        scorecards=all_scorecards,
        notes=" ".join(notes_parts),
    )

    run_file = runs_dir / f"{effective_run_id}.json"
    save_model_run(run, run_file)

    print(f"\nModelRun saved → {run_file}")
    print(
        f"Summary: {len(all_scorecards)}/{len(vendor_dirs)} vendors scored, "
        f"{total_input_tokens + total_output_tokens:,} total tokens, "
        f"{round(total_duration, 1)}s"
    )
    return run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Score all vendors and save results as a ModelRun."
    )
    parser.add_argument(
        "--vendors-dir",
        type=Path,
        default=VENDORS_DIR,
        help=f"Directory containing per-vendor subdirectories (default: {VENDORS_DIR}).",
    )
    parser.add_argument(
        "--scores-dir",
        type=Path,
        default=SCORES_DIR,
        help=f"Directory for per-vendor scorecard JSON files (default: {SCORES_DIR}).",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        help=f"Directory for ModelRun JSON output (default: {RUNS_DIR}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit run identifier (auto-generated if omitted).",
    )
    args = parser.parse_args()

    run_pipeline(
        vendors_dir=args.vendors_dir,
        scores_dir=args.scores_dir,
        runs_dir=args.runs_dir,
        model=args.model,
        run_id=args.run_id,
    )
