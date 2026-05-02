"""
Evidence-validity spot-check sampler.

Why this exists separately from eval.py:

The automated metrics in eval.py answer "does the model score agree, and is
it citing *something*?" but they cannot answer "does the cited quote actually
support the score?" — that requires human judgement.

This script picks a representative sample (default 20% of dimension scores,
stratified across vendors) and produces a CSV the reviewer fills in by hand.
The reviewer marks each cited quote as:
    - VALID:    the quote genuinely supports the assigned score
    - PARTIAL:  the quote is on-topic but doesn't fully support the score
    - INVALID:  the quote is irrelevant, misleading, or fabricated

The resulting CSV is the human-validation layer that sits *on top of* the
automated metrics. Together they answer the two product questions:

    1. Does the model score correctly? (eval.py)
    2. When the model is right, is it right for the right reasons? (this)

That second question is the one a procurement reviewer cares about most.
"""

import argparse
import csv
import random
from pathlib import Path

from io_scorecards import load_model_run


def sample_for_review(
    run_path: str,
    sample_fraction: float = 0.2,
    seed: int = 42,
) -> list[dict]:
    """Stratified sample across vendors so no vendor dominates the spot-check."""
    rng = random.Random(seed)
    run = load_model_run(run_path)

    rows = []
    for card in run.scorecards:
        # sample within this vendor's dimensions
        n_to_sample = max(1, round(len(card.scores) * sample_fraction))
        sampled = rng.sample(card.scores, n_to_sample)
        for s in sampled:
            rows.append({
                "vendor_id": card.vendor_id,
                "vendor_name": card.vendor_name,
                "document_filename": card.document_filename,
                "dimension_id": s.dimension_id,
                "dimension_name": s.dimension_name,
                "model_score": s.score,
                "evidence_quote": s.evidence_quote,
                "evidence_location": s.evidence_location,
                "scoring_rationale": s.scoring_rationale,
                "human_verdict": "",          # to fill: VALID / PARTIAL / INVALID
                "human_notes": "",
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Sample dimensions for human evidence-validity review.")
    parser.add_argument("--run", required=True, help="Path to model run JSON")
    parser.add_argument("--fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="outputs/evidence_spotcheck.csv")
    args = parser.parse_args()

    rows = sample_for_review(args.run, args.fraction, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows for review to {out}")
    print("Fill in the 'human_verdict' column with VALID / PARTIAL / INVALID and 'human_notes' as needed.")


if __name__ == "__main__":
    main()
