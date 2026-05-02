"""
Load and save scorecards from JSON.

The on-disk format is the same shape as the dataclasses in schemas.py.
Keeping load/save logic in one place means rubric/schema migrations have one
place to live, not scattered across the codebase.
"""

import json
from pathlib import Path

from schemas import (
    DimensionScore, VendorScorecard, GoldenSet, ModelRun,
    DIMENSION_NAMES, RUBRIC_VERSION, SCHEMA_VERSION,
)


# -----------------------------------------------------------------------------
# Load
# -----------------------------------------------------------------------------

def _load_scorecard(d: dict) -> VendorScorecard:
    scores = [
        DimensionScore(
            dimension_id=s["dimension_id"],
            dimension_name=s.get("dimension_name", DIMENSION_NAMES[s["dimension_id"]]),
            score=s["score"],
            evidence_quote=s.get("evidence_quote", ""),
            evidence_location=s.get("evidence_location", "no evidence found"),
            confidence=s.get("confidence", "medium"),
            scoring_rationale=s.get("scoring_rationale", ""),
        )
        for s in d["scores"]
    ]

    return VendorScorecard(
        vendor_id=d["vendor_id"],
        vendor_name=d["vendor_name"],
        document_filename=d["document_filename"],
        document_type=d["document_type"],
        reporting_period=d["reporting_period"],
        scores=scores,
        overall_notes=d.get("overall_notes", ""),
        evidence_quality_flag=d.get("evidence_quality_flag", "mixed"),
        scorer=d.get("scorer", "unknown"),
        scoring_date=d.get("scoring_date", ""),
        rubric_version=d.get("rubric_version", RUBRIC_VERSION),
        schema_version=d.get("schema_version", SCHEMA_VERSION),
    )


def load_golden_set(path: Path | str) -> GoldenSet:
    raw = json.loads(Path(path).read_text())
    return GoldenSet(
        name=raw["name"],
        description=raw.get("description", ""),
        rubric_version=raw["rubric_version"],
        scorecards=[_load_scorecard(c) for c in raw["scorecards"]],
    )


def load_model_run(path: Path | str) -> ModelRun:
    raw = json.loads(Path(path).read_text())
    return ModelRun(
        run_id=raw["run_id"],
        pipeline_version=raw["pipeline_version"],
        model=raw["model"],
        prompt_version=raw["prompt_version"],
        run_date=raw["run_date"],
        rubric_version=raw["rubric_version"],
        scorecards=[_load_scorecard(c) for c in raw["scorecards"]],
        notes=raw.get("notes", ""),
    )


# -----------------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------------

def _scorecard_to_dict(card: VendorScorecard) -> dict:
    return {
        "vendor_id": card.vendor_id,
        "vendor_name": card.vendor_name,
        "document_filename": card.document_filename,
        "document_type": card.document_type,
        "reporting_period": card.reporting_period,
        "total_score": card.total_score,
        "max_score": card.max_score,
        "scorer": card.scorer,
        "scoring_date": card.scoring_date,
        "rubric_version": card.rubric_version,
        "schema_version": card.schema_version,
        "evidence_quality_flag": card.evidence_quality_flag,
        "overall_notes": card.overall_notes,
        "scores": [
            {
                "dimension_id": s.dimension_id,
                "dimension_name": s.dimension_name,
                "score": s.score,
                "evidence_quote": s.evidence_quote,
                "evidence_location": s.evidence_location,
                "confidence": s.confidence,
                "scoring_rationale": s.scoring_rationale,
            }
            for s in card.scores
        ],
    }


def save_golden_set(golden: GoldenSet, path: Path | str) -> None:
    data = {
        "name": golden.name,
        "description": golden.description,
        "rubric_version": golden.rubric_version,
        "scorecards": [_scorecard_to_dict(c) for c in golden.scorecards],
    }
    Path(path).write_text(json.dumps(data, indent=2))


def save_model_run(run: ModelRun, path: Path | str) -> None:
    data = {
        "run_id": run.run_id,
        "pipeline_version": run.pipeline_version,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "run_date": run.run_date,
        "rubric_version": run.rubric_version,
        "notes": run.notes,
        "scorecards": [_scorecard_to_dict(c) for c in run.scorecards],
    }
    Path(path).write_text(json.dumps(data, indent=2))


# -----------------------------------------------------------------------------
# Convenience: ingest the per-vendor JSON blobs ChatGPT will produce
# -----------------------------------------------------------------------------

def ingest_chatgpt_scores(
    json_files: list[Path | str],
    scorer_label: str,
    scoring_date: str,
    name: str = "Golden set v1.0",
    description: str = "Five vendors, ChatGPT-scored, human spot-check on 20% of dimensions",
) -> GoldenSet:
    """
    Take the individual JSON blobs ChatGPT returns (one per vendor) and assemble
    them into a single GoldenSet. The ChatGPT prompt outputs a per-vendor object;
    this just stitches them together and stamps provenance.
    """
    cards = []
    for f in json_files:
        raw = json.loads(Path(f).read_text())
        # Stamp scorer + date + versions if ChatGPT didn't include them
        raw.setdefault("scorer", scorer_label)
        raw.setdefault("scoring_date", scoring_date)
        raw.setdefault("rubric_version", RUBRIC_VERSION)
        raw.setdefault("schema_version", SCHEMA_VERSION)
        cards.append(_load_scorecard(raw))

    return GoldenSet(
        name=name,
        description=description,
        rubric_version=RUBRIC_VERSION,
        scorecards=cards,
    )
