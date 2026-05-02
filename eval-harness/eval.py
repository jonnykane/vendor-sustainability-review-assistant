"""
Run the eval: model run vs golden set.

Usage:
    python eval.py --golden golden/golden_set.json --run runs/2026-05-02_v0_naive.json

Output:
    - prints summary tables to stdout
    - writes a structured report JSON to outputs/eval_<run_id>.json
    - writes a markdown report to outputs/eval_<run_id>.md (for the README)

What this script does NOT do:
    - judge whether evidence quotes actually support the score (that's a human
      spot-check task — see eval_evidence_validity_spotcheck.py)
    - re-score anything; it only compares two existing scorecards
"""

import argparse
import json
from datetime import date
from pathlib import Path

from schemas import VendorScorecard, GoldenSet, ModelRun, DIMENSION_NAMES
from io_scorecards import load_golden_set, load_model_run
from eval_metrics import (
    compare_dimensions, summarise, summarise_by_dimension, summarise_by_vendor,
    confusion_matrix, render_confusion_matrix, MetricsSummary,
)


def run_eval(golden: GoldenSet, model_run: ModelRun) -> dict:
    """
    Compare a model run against ground truth.

    Returns a structured dict ready to serialise — this is the single object
    that drives both the JSON report and the markdown summary, so they
    can never drift apart.
    """

    # Sanity check: rubric versions match
    if golden.rubric_version != model_run.rubric_version:
        raise ValueError(
            f"Rubric mismatch: golden={golden.rubric_version}, run={model_run.rubric_version}. "
            "Re-score one side before comparing."
        )

    # Index both sides by vendor for pairing
    golden_by_vendor = {c.vendor_id: c for c in golden.scorecards}
    model_by_vendor = {c.vendor_id: c for c in model_run.scorecards}

    missing = set(golden_by_vendor) - set(model_by_vendor)
    extra = set(model_by_vendor) - set(golden_by_vendor)
    if missing:
        raise ValueError(f"Model run missing vendors present in golden set: {missing}")
    if extra:
        # Not fatal — just a warning, model may have scored extras
        print(f"WARNING: model scored vendors not in golden set: {extra}")

    # Build per-dimension comparison list across all paired vendors
    all_comparisons = []
    for vendor_id, truth_card in golden_by_vendor.items():
        model_card = model_by_vendor[vendor_id]
        all_comparisons.extend(compare_dimensions(truth_card, model_card))

    # Aggregate
    overall = summarise(all_comparisons)
    by_dim = summarise_by_dimension(all_comparisons)
    by_vendor = summarise_by_vendor(all_comparisons)
    cm = confusion_matrix(all_comparisons)

    # Failure taxonomy: surface the worst individual dimension comparisons.
    # These are the cases worth eyeballing manually for failure-mode patterns.
    worst_cases = sorted(
        all_comparisons,
        key=lambda c: (c.absolute_error, c.unsupported_claim, c.hallucinated_zero),
        reverse=True,
    )[:10]

    return {
        "run_id": model_run.run_id,
        "pipeline_version": model_run.pipeline_version,
        "model": model_run.model,
        "prompt_version": model_run.prompt_version,
        "rubric_version": model_run.rubric_version,
        "golden_set": golden.name,
        "n_vendors": len(golden.scorecards),
        "n_dimension_comparisons": len(all_comparisons),
        "overall": _summary_to_dict(overall),
        "by_dimension": {
            dim_id: {
                "name": DIMENSION_NAMES[dim_id],
                **_summary_to_dict(s),
            }
            for dim_id, s in by_dim.items()
        },
        "by_vendor": {v: _summary_to_dict(s) for v, s in by_vendor.items()},
        "confusion_matrix": cm,
        "worst_cases": [
            {
                "vendor_id": c.vendor_id,
                "dimension_id": c.dimension_id,
                "dimension_name": c.dimension_name,
                "truth_score": c.truth_score,
                "model_score": c.model_score,
                "absolute_error": c.absolute_error,
                "signed_error": c.signed_error,
                "unsupported_claim": c.unsupported_claim,
                "hallucinated_zero": c.hallucinated_zero,
            }
            for c in worst_cases
        ],
    }


def _summary_to_dict(s: MetricsSummary) -> dict:
    return {
        "n": s.n,
        "exact_match_rate": round(s.exact_match_rate, 3),
        "within_one_rate": round(s.within_one_rate, 3),
        "mae": round(s.mae, 3),
        "directional_bias": round(s.directional_bias, 3),
        "unsupported_claim_rate": round(s.unsupported_claim_rate, 3),
        "hallucinated_zero_rate": round(s.hallucinated_zero_rate, 3),
        "evidence_present_when_scored": round(s.evidence_present_when_scored, 3),
    }


# -----------------------------------------------------------------------------
# Markdown report — this is what goes into the README
# -----------------------------------------------------------------------------

def render_markdown_report(report: dict) -> str:
    lines = []
    lines.append(f"# Eval Report: `{report['run_id']}`")
    lines.append("")
    lines.append(f"- Pipeline: `{report['pipeline_version']}`")
    lines.append(f"- Model: `{report['model']}`")
    lines.append(f"- Prompt version: `{report['prompt_version']}`")
    lines.append(f"- Rubric version: `{report['rubric_version']}`")
    lines.append(f"- Golden set: {report['golden_set']}")
    lines.append(f"- Vendors compared: {report['n_vendors']} ({report['n_dimension_comparisons']} dimension comparisons)")
    lines.append("")

    lines.append("## Overall metrics")
    lines.append("")
    o = report["overall"]
    lines.append(f"| Metric | Value |")
    lines.append(f"| --- | --- |")
    lines.append(f"| Exact match | {o['exact_match_rate']:.1%} |")
    lines.append(f"| Within-one match | {o['within_one_rate']:.1%} |")
    lines.append(f"| Mean absolute error | {o['mae']:.2f} |")
    lines.append(f"| Directional bias | {o['directional_bias']:+.2f} |")
    lines.append(f"| Unsupported claim rate | {o['unsupported_claim_rate']:.1%} |")
    lines.append(f"| Hallucinated-zero rate | {o['hallucinated_zero_rate']:.1%} |")
    lines.append(f"| Evidence present when scored | {o['evidence_present_when_scored']:.1%} |")
    lines.append("")

    lines.append("## By dimension")
    lines.append("")
    lines.append("| # | Dimension | Exact | Within-1 | MAE | Bias | Unsupp. |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for dim_id, s in report["by_dimension"].items():
        lines.append(
            f"| {dim_id} | {s['name']} | {s['exact_match_rate']:.0%} | "
            f"{s['within_one_rate']:.0%} | {s['mae']:.2f} | {s['directional_bias']:+.2f} | "
            f"{s['unsupported_claim_rate']:.0%} |"
        )
    lines.append("")

    lines.append("## By vendor")
    lines.append("")
    lines.append("| Vendor | Exact | Within-1 | MAE | Bias |")
    lines.append("| --- | --- | --- | --- | --- |")
    for vendor, s in report["by_vendor"].items():
        lines.append(
            f"| {vendor} | {s['exact_match_rate']:.0%} | {s['within_one_rate']:.0%} | "
            f"{s['mae']:.2f} | {s['directional_bias']:+.2f} |"
        )
    lines.append("")

    lines.append("## Confusion matrix (truth rows × model cols, scores 0-3)")
    lines.append("")
    lines.append("```")
    lines.append(render_confusion_matrix(report["confusion_matrix"]))
    lines.append("```")
    lines.append("")

    lines.append("## Worst cases (top 10 by absolute error)")
    lines.append("")
    lines.append("| Vendor | Dim | Name | Truth | Model | Abs err | Unsupported? | Hallucinated zero? |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for c in report["worst_cases"]:
        lines.append(
            f"| {c['vendor_id']} | {c['dimension_id']} | {c['dimension_name']} | "
            f"{c['truth_score']} | {c['model_score']} | {c['absolute_error']} | "
            f"{'yes' if c['unsupported_claim'] else 'no'} | "
            f"{'yes' if c['hallucinated_zero'] else 'no'} |"
        )
    lines.append("")

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run scorecard eval against golden set.")
    parser.add_argument("--golden", required=True, help="Path to golden set JSON")
    parser.add_argument("--run", required=True, help="Path to model run JSON")
    parser.add_argument("--out-dir", default="outputs", help="Where to write reports")
    args = parser.parse_args()

    golden = load_golden_set(args.golden)
    model_run = load_model_run(args.run)
    report = run_eval(golden, model_run)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"eval_{report['run_id']}.json"
    md_path = out_dir / f"eval_{report['run_id']}.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown_report(report))

    # stdout summary
    print(render_markdown_report(report))
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
