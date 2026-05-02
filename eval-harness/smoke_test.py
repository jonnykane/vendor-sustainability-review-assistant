"""
Smoke test: fabricate two scorecards (truth + model) and run the full eval pipeline
to make sure schemas, IO, and metrics all hang together.

Run with: python smoke_test.py
"""

import json
import tempfile
from pathlib import Path
from datetime import date

from schemas import (
    DimensionScore, VendorScorecard, GoldenSet, ModelRun, DIMENSION_NAMES, RUBRIC_VERSION,
)
from io_scorecards import save_golden_set, save_model_run, load_golden_set, load_model_run
from eval import run_eval, render_markdown_report


def make_dim(dim_id: int, score: int, with_evidence: bool = True) -> DimensionScore:
    if with_evidence and score > 0:
        ev_quote = f"Synthetic supporting quote for dim {dim_id}"
        ev_loc = f"page {dim_id}"
    elif with_evidence and score == 0:
        ev_quote = ""
        ev_loc = "no evidence found"
    else:
        ev_quote = ""
        ev_loc = "no evidence found"
    return DimensionScore(
        dimension_id=dim_id,
        dimension_name=DIMENSION_NAMES[dim_id],
        score=score,
        evidence_quote=ev_quote,
        evidence_location=ev_loc,
        confidence="high",
        scoring_rationale=f"Synthetic rationale, dim {dim_id}, score {score}",
    )


def card(vendor_id, scores, scorer, with_evidence=True):
    return VendorScorecard(
        vendor_id=vendor_id,
        vendor_name=vendor_id.replace("_", " ").title(),
        document_filename=f"{vendor_id}.pdf",
        document_type="sustainability_report",
        reporting_period="FY2024",
        scores=[make_dim(i+1, s, with_evidence) for i, s in enumerate(scores)],
        overall_notes="smoke test",
        evidence_quality_flag="strong",
        scorer=scorer,
        scoring_date=str(date.today()),
    )


def main():
    # Truth scores: sentinel high, archive_ni mid, heritage low
    golden = GoldenSet(
        name="smoke-test golden",
        description="fabricated for smoke test",
        rubric_version=RUBRIC_VERSION,
        scorecards=[
            card("sentinel_records", [3, 3, 2, 2, 2], "gpt-test"),
            card("archive_ni", [2, 1, 1, 1, 2], "gpt-test"),
            card("heritage", [1, 0, 0, 0, 0], "gpt-test"),
        ],
    )

    # Model run: deliberately introduce some errors and one unsupported claim
    model_cards = [
        # sentinel: model over-scores dim 4 (limited→reasonable confusion)
        card("sentinel_records", [3, 3, 2, 3, 2], "claude-test"),
        # archive_ni: model misses scope 3 entirely (hallucinated zero)
        card("archive_ni", [2, 1, 0, 1, 2], "claude-test", with_evidence=False),
        # heritage: model over-claims scope 2 with no evidence (unsupported claim)
        VendorScorecard(
            vendor_id="heritage",
            vendor_name="Heritage",
            document_filename="heritage.pdf",
            document_type="web_statement",
            reporting_period="2023",
            scores=[
                make_dim(1, 1),
                # unsupported claim: score 2 but no evidence
                DimensionScore(
                    dimension_id=2, dimension_name=DIMENSION_NAMES[2],
                    score=2, evidence_quote="", evidence_location="no evidence found",
                    confidence="low", scoring_rationale="model inferred from intent language",
                ),
                make_dim(3, 0),
                make_dim(4, 0),
                make_dim(5, 0),
            ],
            overall_notes="smoke test",
            evidence_quality_flag="weak",
            scorer="claude-test",
            scoring_date=str(date.today()),
        ),
    ]

    model_run = ModelRun(
        run_id="smoke_test_001",
        pipeline_version="v0-naive",
        model="claude-test",
        prompt_version="p0",
        run_date=str(date.today()),
        rubric_version=RUBRIC_VERSION,
        scorecards=model_cards,
        notes="smoke test",
    )

    # Round-trip through disk to also test IO
    with tempfile.TemporaryDirectory() as tmp:
        gp = Path(tmp) / "golden.json"
        rp = Path(tmp) / "run.json"
        save_golden_set(golden, gp)
        save_model_run(model_run, rp)

        loaded_golden = load_golden_set(gp)
        loaded_run = load_model_run(rp)

        report = run_eval(loaded_golden, loaded_run)

    print(render_markdown_report(report))
    print("\n--- Sanity asserts ---")
    # Expected: 1 unsupported claim (heritage dim 2), 1 hallucinated zero (archive_ni dim 3)
    overall = report["overall"]
    assert overall["unsupported_claim_rate"] > 0, "Should have caught the heritage unsupported claim"
    assert overall["hallucinated_zero_rate"] > 0, "Should have caught the archive_ni hallucinated zero"
    print(f"unsupported_claim_rate: {overall['unsupported_claim_rate']:.1%} ✓")
    print(f"hallucinated_zero_rate: {overall['hallucinated_zero_rate']:.1%} ✓")
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
