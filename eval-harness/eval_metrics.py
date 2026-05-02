"""
Eval metrics for vendor scorecards.

Two distinct metric families, deliberately kept separate:

1. SCORE METRICS — does the model score agree with ground truth?
   - exact_match_rate: model.score == ground_truth.score
   - within_one_rate:  abs(model.score - ground_truth.score) <= 1
   - mae:              mean absolute error on the 0-3 ordinal scale
   - directional_bias: signed mean error (positive = model over-scores)

2. EVIDENCE METRICS — is the model's reasoning trustworthy?
   - unsupported_claim_rate: model gave a non-zero score but no evidence
   - hallucinated_zero_rate: model said "no evidence" but ground truth had evidence
   - evidence_present_when_scored: % of non-zero scores that include evidence

   Note: evidence VALIDITY (does the quote actually support the score?) requires
   human spot-check and lives in eval_evidence_validity_spotcheck.py — it's not
   automatable from the JSON alone.

Why split them? Because for procurement use cases, a confidently-wrong citation
is the actual product failure mode, not a wrong score. A model that scores
correctly but hallucinates evidence is dangerous; a model that scores slightly
off but cites accurately is recoverable. The metrics need to surface that
distinction, not collapse it.
"""

from dataclasses import dataclass
from collections import defaultdict
from typing import Optional

from schemas import VendorScorecard, DimensionScore, DIMENSION_NAMES


# -----------------------------------------------------------------------------
# Per-dimension comparison primitive
# -----------------------------------------------------------------------------

@dataclass
class DimensionComparison:
    """One model dimension scored against one ground-truth dimension."""

    vendor_id: str
    dimension_id: int
    dimension_name: str
    truth_score: int
    model_score: int
    truth_has_evidence: bool
    model_has_evidence: bool

    @property
    def exact_match(self) -> bool:
        return self.model_score == self.truth_score

    @property
    def within_one(self) -> bool:
        return abs(self.model_score - self.truth_score) <= 1

    @property
    def absolute_error(self) -> int:
        return abs(self.model_score - self.truth_score)

    @property
    def signed_error(self) -> int:
        # Positive => model over-scored relative to ground truth
        return self.model_score - self.truth_score

    @property
    def unsupported_claim(self) -> bool:
        # Model gave a non-zero score with no supporting evidence — the
        # most product-relevant failure mode for a procurement reviewer.
        return self.model_score > 0 and not self.model_has_evidence

    @property
    def hallucinated_zero(self) -> bool:
        # Model said "no evidence" but ground truth found evidence and scored > 0.
        # This is the model failing to find what's there.
        return (
            self.model_score == 0
            and not self.model_has_evidence
            and self.truth_score > 0
            and self.truth_has_evidence
        )


def compare_dimensions(
    truth_card: VendorScorecard,
    model_card: VendorScorecard,
) -> list[DimensionComparison]:
    """Pair up dimensions from two scorecards for the same vendor."""

    if truth_card.vendor_id != model_card.vendor_id:
        raise ValueError(
            f"Vendor mismatch: {truth_card.vendor_id} vs {model_card.vendor_id}"
        )

    truth_by_dim = {s.dimension_id: s for s in truth_card.scores}
    model_by_dim = {s.dimension_id: s for s in model_card.scores}

    comparisons = []
    for dim_id in sorted(truth_by_dim.keys()):
        if dim_id not in model_by_dim:
            raise ValueError(
                f"Model output missing dimension {dim_id} for {truth_card.vendor_id}"
            )

        t = truth_by_dim[dim_id]
        m = model_by_dim[dim_id]

        comparisons.append(DimensionComparison(
            vendor_id=truth_card.vendor_id,
            dimension_id=dim_id,
            dimension_name=DIMENSION_NAMES.get(dim_id, t.dimension_name),
            truth_score=t.score,
            model_score=m.score,
            truth_has_evidence=t.has_evidence(),
            model_has_evidence=m.has_evidence(),
        ))

    return comparisons


# -----------------------------------------------------------------------------
# Aggregate metrics
# -----------------------------------------------------------------------------

@dataclass
class MetricsSummary:
    """Aggregate metrics over a set of dimension comparisons."""

    n: int

    # Score-level
    exact_match_rate: float
    within_one_rate: float
    mae: float
    directional_bias: float       # signed mean error; >0 = model over-scores

    # Evidence-level
    unsupported_claim_rate: float
    hallucinated_zero_rate: float
    evidence_present_when_scored: float  # of non-zero scores, % with evidence

    def __str__(self) -> str:
        return (
            f"n={self.n}\n"
            f"  exact_match:                 {self.exact_match_rate:.1%}\n"
            f"  within_one:                  {self.within_one_rate:.1%}\n"
            f"  mae:                         {self.mae:.2f}\n"
            f"  directional_bias:            {self.directional_bias:+.2f}\n"
            f"  unsupported_claim_rate:      {self.unsupported_claim_rate:.1%}\n"
            f"  hallucinated_zero_rate:      {self.hallucinated_zero_rate:.1%}\n"
            f"  evidence_present_when_scored:{self.evidence_present_when_scored:.1%}"
        )


def summarise(comparisons: list[DimensionComparison]) -> MetricsSummary:
    if not comparisons:
        raise ValueError("No comparisons to summarise.")

    n = len(comparisons)

    exact = sum(c.exact_match for c in comparisons) / n
    within_one = sum(c.within_one for c in comparisons) / n
    mae = sum(c.absolute_error for c in comparisons) / n
    bias = sum(c.signed_error for c in comparisons) / n

    unsupported = sum(c.unsupported_claim for c in comparisons) / n
    halluc_zero = sum(c.hallucinated_zero for c in comparisons) / n

    non_zero_model = [c for c in comparisons if c.model_score > 0]
    if non_zero_model:
        ev_present = sum(c.model_has_evidence for c in non_zero_model) / len(non_zero_model)
    else:
        ev_present = 1.0  # no positive scores claimed, vacuously fine

    return MetricsSummary(
        n=n,
        exact_match_rate=exact,
        within_one_rate=within_one,
        mae=mae,
        directional_bias=bias,
        unsupported_claim_rate=unsupported,
        hallucinated_zero_rate=halluc_zero,
        evidence_present_when_scored=ev_present,
    )


def summarise_by_dimension(
    comparisons: list[DimensionComparison],
) -> dict[int, MetricsSummary]:
    """Per-dimension breakdown — this is where you find which dimensions the model struggles on."""
    by_dim: dict[int, list[DimensionComparison]] = defaultdict(list)
    for c in comparisons:
        by_dim[c.dimension_id].append(c)
    return {dim_id: summarise(cs) for dim_id, cs in sorted(by_dim.items())}


def summarise_by_vendor(
    comparisons: list[DimensionComparison],
) -> dict[str, MetricsSummary]:
    """Per-vendor breakdown — useful for spotting whether failures cluster on specific vendors."""
    by_vendor: dict[str, list[DimensionComparison]] = defaultdict(list)
    for c in comparisons:
        by_vendor[c.vendor_id].append(c)
    return {v: summarise(cs) for v, cs in sorted(by_vendor.items())}


# -----------------------------------------------------------------------------
# Confusion matrix (4x4 over scores 0-3)
# -----------------------------------------------------------------------------

def confusion_matrix(comparisons: list[DimensionComparison]) -> list[list[int]]:
    """
    Returns a 4x4 matrix where matrix[truth][model] = count.
    Rows are ground truth scores, columns are model scores.
    Off-diagonal = errors. Above-diagonal = model over-scored.
    """
    matrix = [[0] * 4 for _ in range(4)]
    for c in comparisons:
        matrix[c.truth_score][c.model_score] += 1
    return matrix


def render_confusion_matrix(matrix: list[list[int]]) -> str:
    """Pretty-print the confusion matrix for the README."""
    lines = ["         model→  0    1    2    3"]
    lines.append("truth ↓")
    for truth_score, row in enumerate(matrix):
        cells = "  ".join(f"{v:3d}" for v in row)
        lines.append(f"   {truth_score}            {cells}")
    return "\n".join(lines)
