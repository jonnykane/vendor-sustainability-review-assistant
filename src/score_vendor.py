#!/usr/bin/env python3
"""
Score a vendor sustainability disclosure document using Claude.

Usage:
    python src/score_vendor.py data/vendors/microsoft/2025-Microsoft-Environmental-Sustainability-Report.pdf
    python src/score_vendor.py data/vendors/boxvault/boxvault_sustainability.html --vendor "BoxVault"
    python src/score_vendor.py <doc> --model claude-sonnet-4-6 --output scores/microsoft.json
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path
from typing import NamedTuple

import anthropic

# Resolve eval-harness imports (directory has a hyphen so can't use normal import)
_EVAL_HARNESS = Path(__file__).resolve().parent.parent / "eval-harness"
sys.path.insert(0, str(_EVAL_HARNESS))

from schemas import DimensionScore, VendorScorecard  # noqa: E402
from build_golden_set import RUBRIC, RUBRIC_VERSION  # noqa: E402

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment]


DEFAULT_MODEL = "claude-sonnet-4-6"
PIPELINE_VERSION = "v0-naive-longcontext"
PROMPT_VERSION = "v1"


class ScoringResult(NamedTuple):
    scorecard: VendorScorecard
    input_tokens: int
    output_tokens: int
    duration_seconds: float


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

def _extract_text_pdf(path: Path) -> str:
    if pdfplumber is None:
        raise ImportError(
            "pdfplumber is required for PDF extraction. "
            "Install it with: pip install pdfplumber"
        )
    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {i}]\n{text}")
    if not pages:
        raise ValueError(f"No extractable text found in {path.name}")
    return "\n\n".join(pages)


def _extract_text_html(path: Path) -> str:
    if BeautifulSoup is None:
        raise ImportError(
            "beautifulsoup4 is required for HTML extraction. "
            "Install it with: pip install beautifulsoup4 lxml"
        )
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _extract_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_pdf(path)
    if suffix in (".html", ".htm"):
        return _extract_text_html(path)
    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported formats: .pdf, .html, .htm"
    )


# ---------------------------------------------------------------------------
# Prompt and tool schema
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    lines = [
        "You are an expert sustainability analyst specialising in corporate climate disclosure.",
        "Review the vendor document provided and score it against the rubric below.",
        "Be precise and evidence-based. Score conservatively: when evidence is ambiguous "
        "between two adjacent scores, assign the lower score.",
        "",
        "## Scoring Scale",
        "  0 = No evidence — the topic is not mentioned anywhere in the document",
        "  1 = Aspiration only — vague commitment, no specific targets or measurable metrics",
        "  2 = Committed — specific time-bound target, quantified metric, or named programme",
        "  3 = Verified — third-party assured or certified, with quantified progress reported",
        "",
        "## Dimensions and Criteria",
        "",
    ]
    for dim_id, dim in RUBRIC.items():
        lines += [
            f"### Dimension {dim_id}: {dim['name']}",
            dim["description"],
            "",
        ]
        for score_val, criteria in dim["criteria"].items():
            lines.append(f"  [{score_val}] {criteria}")
        lines.append("")

    lines += [
        "## Field Instructions",
        "- `evidence_quote`: verbatim excerpt from the document, max 25 words.",
        "  Use 'No evidence found' if score is 0.",
        "- `evidence_location`: page number (e.g. 'p.12') or section name.",
        "  Use 'N/A' if score is 0.",
        "- `confidence`: high = direct unambiguous evidence; medium = inferred or",
        "  partially stated; low = weak or indirect signal.",
        "- `scoring_rationale`: 1–2 sentences explaining the score.",
        "- `reporting_period`: the year or fiscal period the document covers (e.g. '2024').",
        "- `evidence_quality_flag`: strong = consistent evidence across dimensions;",
        "  mixed = some dimensions well-evidenced and others not; weak = little evidence.",
    ]
    return "\n".join(lines)


def _build_tool_schema() -> dict:
    dim_score_schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 3,
                "description": "Score 0–3 per rubric.",
            },
            "evidence_quote": {
                "type": "string",
                "description": (
                    "Verbatim quote from the document, max 25 words. "
                    "'No evidence found' if score is 0."
                ),
            },
            "evidence_location": {
                "type": "string",
                "description": (
                    "Page number (e.g. 'p.12') or section name. 'N/A' if score is 0."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "scoring_rationale": {
                "type": "string",
                "description": "1–2 sentences explaining the score.",
            },
        },
        "required": [
            "score",
            "evidence_quote",
            "evidence_location",
            "confidence",
            "scoring_rationale",
        ],
    }

    dimension_properties = {
        f"dimension_{dim_id}": {
            **dim_score_schema,
            "description": f"Dimension {dim_id}: {RUBRIC[dim_id]['name']}",
        }
        for dim_id in RUBRIC
    }

    return {
        "type": "object",
        "properties": {
            "vendor_name": {
                "type": "string",
                "description": "Organisation name as it appears in the document.",
            },
            "document_type": {
                "type": "string",
                "enum": [
                    "sustainability_report",
                    "annual_report_extract",
                    "web_statement",
                    "microsite",
                ],
                "description": "Type of disclosure document.",
            },
            "reporting_period": {
                "type": "string",
                "description": "Year or fiscal period covered (e.g. '2024', 'FY2023/24').",
            },
            **dimension_properties,
            "overall_notes": {
                "type": "string",
                "description": "1–3 sentences summarising the overall quality of the disclosure.",
            },
            "evidence_quality_flag": {
                "type": "string",
                "enum": ["strong", "mixed", "weak"],
                "description": (
                    "strong = clear consistent evidence; "
                    "mixed = patchy; "
                    "weak = little substantive evidence."
                ),
            },
        },
        "required": [
            "vendor_name",
            "document_type",
            "reporting_period",
            *[f"dimension_{dim_id}" for dim_id in RUBRIC],
            "overall_notes",
            "evidence_quality_flag",
        ],
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_full(
    path: Path,
    vendor_id: str | None = None,
    vendor_name: str | None = None,
    model: str = DEFAULT_MODEL,
) -> ScoringResult:
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    t0 = time.perf_counter()
    document_text = _extract_document_text(path)

    client = anthropic.Anthropic()

    tool_def = {
        "name": "fill_vendor_scorecard",
        "description": (
            "Fill the sustainability scorecard for the vendor "
            "based on the disclosure document."
        ),
        "input_schema": _build_tool_schema(),
        "cache_control": {"type": "ephemeral"},
    }

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "fill_vendor_scorecard"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Score the following vendor sustainability document:\n\n"
                    + document_text
                ),
            }
        ],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    inputs: dict = tool_block.input

    effective_vendor_name = vendor_name or inputs["vendor_name"]
    effective_vendor_id = vendor_id or path.parent.name

    scores = [
        DimensionScore(
            dimension_id=dim_id,
            dimension_name=RUBRIC[dim_id]["name"],
            score=inputs[f"dimension_{dim_id}"]["score"],
            evidence_quote=inputs[f"dimension_{dim_id}"]["evidence_quote"],
            evidence_location=inputs[f"dimension_{dim_id}"]["evidence_location"],
            confidence=inputs[f"dimension_{dim_id}"]["confidence"],
            scoring_rationale=inputs[f"dimension_{dim_id}"]["scoring_rationale"],
        )
        for dim_id in RUBRIC
    ]

    scorecard = VendorScorecard(
        vendor_id=effective_vendor_id,
        vendor_name=effective_vendor_name,
        document_filename=path.name,
        document_type=inputs["document_type"],
        reporting_period=inputs["reporting_period"],
        scores=scores,
        overall_notes=inputs["overall_notes"],
        evidence_quality_flag=inputs["evidence_quality_flag"],
        scorer=model,
        scoring_date=date.today().isoformat(),
        rubric_version=RUBRIC_VERSION,
    )

    return ScoringResult(
        scorecard=scorecard,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        duration_seconds=round(time.perf_counter() - t0, 2),
    )


def score_vendor(
    document_path: str | Path,
    vendor_id: str | None = None,
    vendor_name: str | None = None,
    model: str = DEFAULT_MODEL,
) -> VendorScorecard:
    """Score a vendor disclosure document. Returns a VendorScorecard."""
    return _score_full(
        Path(document_path),
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        model=model,
    ).scorecard


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Score a vendor sustainability document using Claude."
    )
    parser.add_argument("document", help="Path to the vendor disclosure (PDF or HTML).")
    parser.add_argument(
        "--vendor-id", help="Stable vendor identifier (defaults to parent directory name)."
    )
    parser.add_argument(
        "--vendor", help="Vendor display name (inferred from document if omitted)."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write JSON scorecard to this path (prints to stdout if omitted).",
    )
    args = parser.parse_args()

    result = _score_full(
        Path(args.document),
        vendor_id=args.vendor_id,
        vendor_name=args.vendor,
        model=args.model,
    )
    sc = result.scorecard

    print(f"\nVendor:        {sc.vendor_name}")
    print(f"Document:      {sc.document_filename}  [{sc.document_type}]")
    print(f"Period:        {sc.reporting_period}")
    print(f"Model:         {sc.scorer}")
    print(f"Total score:   {sc.total_score}/{sc.max_score}")
    print(f"Evidence:      {sc.evidence_quality_flag}")
    print(
        f"Tokens:        {result.input_tokens} in / {result.output_tokens} out"
        f"  |  {result.duration_seconds}s"
    )
    print()

    for ds in sc.scores:
        print(f"  [{ds.score}/3] {ds.dimension_name}")
        print(f"        Quote:    {ds.evidence_quote[:80]}")
        print(f"        Location: {ds.evidence_location}  [{ds.confidence}]")
        print()

    import json
    from io_scorecards import _scorecard_to_dict  # noqa: E402

    json_output = json.dumps(_scorecard_to_dict(sc), indent=2)

    if args.output:
        Path(args.output).write_text(json_output)
        print(f"Scorecard written to {args.output}")
    else:
        print(json_output)
