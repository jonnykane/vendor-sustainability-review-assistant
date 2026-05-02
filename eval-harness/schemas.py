"""
Schemas for vendor sustainability scoring.

Both ground-truth scores (from ChatGPT-as-judge with human spot-checks) and
model-generated scores (from your Claude pipeline) conform to the same shape.
This is what makes them comparable.

Versioning matters: when the rubric changes, bump RUBRIC_VERSION and re-score.
Old eval runs stay valid against their rubric version, new ones run against
the current version. Don't silently migrate scores across rubric versions.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
from datetime import date

RUBRIC_VERSION = "1.0"
SCHEMA_VERSION = "1.0"

DimensionId = Literal[1, 2, 3, 4, 5]
Score = Literal[0, 1, 2, 3]
Confidence = Literal["high", "medium", "low"]
EvidenceQualityFlag = Literal["strong", "mixed", "weak"]
DocumentType = Literal[
    "sustainability_report",
    "annual_report_extract",
    "web_statement",
    "microsite",
]

DIMENSION_NAMES = {
    1: "Net Zero commitment and transition plan",
    2: "Scope 1 & 2 emissions disclosure",
    3: "Scope 3 emissions disclosure",
    4: "Third-party verification and assurance",
    5: "Science-based targets validation",
}


@dataclass
class DimensionScore:
    """A single dimension's score with its supporting evidence."""

    dimension_id: DimensionId
    dimension_name: str
    score: Score
    evidence_quote: str          # direct quote, max ~25 words; empty if no evidence
    evidence_location: str       # e.g. "page 2, Section 1.1" or "no evidence found"
    confidence: Confidence
    scoring_rationale: str       # 1-2 sentences

    def has_evidence(self) -> bool:
        return self.evidence_location.lower() != "no evidence found" and bool(self.evidence_quote.strip())


@dataclass
class VendorScorecard:
    """All five dimension scores for a single vendor disclosure."""

    vendor_id: str
    vendor_name: str
    document_filename: str
    document_type: DocumentType
    reporting_period: str
    scores: list[DimensionScore]
    overall_notes: str
    evidence_quality_flag: EvidenceQualityFlag

    # Provenance — who/what produced this scorecard
    scorer: str                  # e.g. "gpt-4o", "claude-opus-4-7", "human:jonny"
    scoring_date: str            # ISO date
    rubric_version: str = RUBRIC_VERSION
    schema_version: str = SCHEMA_VERSION

    @property
    def total_score(self) -> int:
        return sum(s.score for s in self.scores)

    @property
    def max_score(self) -> int:
        return 3 * len(self.scores)


@dataclass
class GoldenSet:
    """The collection of ground-truth scorecards used as the eval target."""

    name: str                    # e.g. "v1.0 — 5 vendors, ChatGPT-scored, human-spot-checked"
    description: str
    rubric_version: str
    scorecards: list[VendorScorecard]


@dataclass
class ModelRun:
    """A single end-to-end run of the model pipeline against the golden set."""

    run_id: str                  # e.g. "2026-05-02_v0_naive_longcontext"
    pipeline_version: str        # e.g. "v0-naive" or "v1-agentic-secondpass"
    model: str                   # e.g. "claude-opus-4-7"
    prompt_version: str          # tag for the system prompt used
    run_date: str
    rubric_version: str
    scorecards: list[VendorScorecard]
    notes: str = ""              # anything noteworthy about this run
