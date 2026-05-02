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

import dataclasses
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
PIPELINE_VERSION = "v1-agentic-secondpass"
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
# Second-pass targeted checks
# ---------------------------------------------------------------------------

class _SecondPassResult(NamedTuple):
    scorecard: VendorScorecard
    input_tokens: int
    output_tokens: int


_CHECK_SYSTEM = (
    "You are a strict sustainability disclosure auditor. "
    "Answer only based on what is explicitly stated in the document. "
    "Do not infer or assume — if the document does not explicitly state something, "
    "the answer is False."
)


def _run_check(
    client: anthropic.Anthropic,
    model: str,
    document_text: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    question: str,
) -> tuple[dict, int, int]:
    """Run one targeted yes/no check. Returns (tool_inputs, in_tokens, out_tokens)."""
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=_CHECK_SYSTEM,
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": tool_schema,
        }],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": document_text,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": question,
                },
            ],
        }],
    )
    tool_block = next(b for b in response.content if b.type == "tool_use")
    return tool_block.input, response.usage.input_tokens, response.usage.output_tokens


def _check_dim2(
    document_text: str,
    client: anthropic.Anthropic,
    model: str,
) -> tuple[bool, bool, int, int]:
    """
    Check two strict conditions for Dimension 2 (Scope 1 & 2).
    Returns (has_reduction_trend, has_both_scope2_types, in_tokens, out_tokens).
    has_reduction_trend required for score 3; has_both_scope2_types required for score 2.
    """
    inputs, in_toks, out_toks = _run_check(
        client, model, document_text,
        tool_name="check_scope_1_2",
        tool_description="Check two strict conditions for Scope 1 & 2 emissions scoring.",
        tool_schema={
            "type": "object",
            "properties": {
                "has_multi_year_reduction_trend": {
                    "type": "boolean",
                    "description": (
                        "True only if the document shows an absolute downward trend in "
                        "Scope 1 and/or Scope 2 emissions across at least two consecutive "
                        "years. Disclosing data without a reduction is False. "
                        "Having a reduction target is False."
                    ),
                },
                "trend_evidence": {
                    "type": "string",
                    "description": "The specific figures or passage supporting your answer, max 30 words.",
                },
                "has_both_scope2_types": {
                    "type": "boolean",
                    "description": (
                        "True only if the document explicitly reports BOTH "
                        "location-based AND market-based Scope 2 figures."
                    ),
                },
                "scope2_evidence": {
                    "type": "string",
                    "description": "The passage showing both Scope 2 types, max 30 words. 'Not found' if False.",
                },
            },
            "required": [
                "has_multi_year_reduction_trend",
                "trend_evidence",
                "has_both_scope2_types",
                "scope2_evidence",
            ],
        },
        question=(
            "Check two strict conditions about Scope 1 and Scope 2 emissions:\n\n"
            "1. Is there an absolute MULTI-YEAR REDUCTION TREND in Scope 1 and/or "
            "Scope 2 emissions? This requires actual falling numbers across at least "
            "two consecutive years. Merely disclosing data, having a reduction target, "
            "or showing year-on-year data without a reduction does NOT qualify.\n\n"
            "2. Are BOTH location-based AND market-based Scope 2 emissions figures "
            "explicitly reported?"
        ),
    )
    return (
        inputs["has_multi_year_reduction_trend"],
        inputs["has_both_scope2_types"],
        in_toks,
        out_toks,
    )


def _check_dim3(
    document_text: str,
    client: anthropic.Anthropic,
    model: str,
) -> tuple[bool, int, int]:
    """
    Check Dimension 3: whether Scope 3 emissions are actually reducing (not just disclosed).
    Returns (scope3_actually_reducing, in_tokens, out_tokens).
    """
    inputs, in_toks, out_toks = _run_check(
        client, model, document_text,
        tool_name="check_scope_3",
        tool_description="Check whether Scope 3 emissions show a genuine reducing trend.",
        tool_schema={
            "type": "object",
            "properties": {
                "scope3_actually_reducing": {
                    "type": "boolean",
                    "description": (
                        "True only if the document demonstrates a downward trend in "
                        "reported Scope 3 emissions figures across at least two years. "
                        "Disclosing Scope 3 figures, supplier engagement programmes, "
                        "or stating a Scope 3 reduction target does NOT qualify."
                    ),
                },
                "evidence": {
                    "type": "string",
                    "description": "The specific figures or passage supporting your answer, max 30 words.",
                },
            },
            "required": ["scope3_actually_reducing", "evidence"],
        },
        question=(
            "Does this document demonstrate that Scope 3 emissions are actually REDUCING? "
            "This requires a demonstrated downward trend in reported Scope 3 figures "
            "across at least two consecutive years. "
            "Supplier engagement programmes, Scope 3 targets, or disclosing Scope 3 data "
            "without a reduction trend does NOT count."
        ),
    )
    return inputs["scope3_actually_reducing"], in_toks, out_toks


def _check_dim5(
    document_text: str,
    client: anthropic.Anthropic,
    model: str,
) -> tuple[bool, int, int]:
    """
    Check Dimension 5: explicitly SBTi-validated vs merely SBTi-aligned.
    Returns (sbti_explicitly_validated, in_tokens, out_tokens).
    """
    inputs, in_toks, out_toks = _run_check(
        client, model, document_text,
        tool_name="check_sbti_validation",
        tool_description="Check whether targets are explicitly SBTi-validated, not merely aligned.",
        tool_schema={
            "type": "object",
            "properties": {
                "sbti_explicitly_validated": {
                    "type": "boolean",
                    "description": (
                        "True only if the document explicitly states the company's targets "
                        "have been validated or approved by SBTi. "
                        "'SBTi-aligned', 'consistent with SBTi methodology', "
                        "'using the SBTi framework', or 'committing to set SBTi targets' "
                        "do NOT count — only explicit validation or approval counts."
                    ),
                },
                "evidence": {
                    "type": "string",
                    "description": "The exact phrase supporting your answer, max 30 words.",
                },
            },
            "required": ["sbti_explicitly_validated", "evidence"],
        },
        question=(
            "Does this document explicitly state that the company's emissions reduction "
            "targets have been VALIDATED or APPROVED by the Science Based Targets "
            "initiative (SBTi)? Be strict: 'SBTi-aligned', 'consistent with SBTi', "
            "'SBTi methodology', or a commitment to set SBTi targets does NOT qualify. "
            "Only explicit validation or approval by SBTi counts."
        ),
    )
    return inputs["sbti_explicitly_validated"], in_toks, out_toks


def _apply_second_pass(
    document_text: str,
    scorecard: VendorScorecard,
    client: anthropic.Anthropic,
    model: str,
) -> _SecondPassResult:
    """
    Run targeted follow-up checks on dimensions prone to over-scoring.
    Caps scores where evidence doesn't meet the stricter bar.
    """
    score_map = {ds.dimension_id: ds for ds in scorecard.scores}
    corrections: dict[int, tuple[int, str]] = {}  # dim_id → (new_score, rationale_suffix)
    total_in = total_out = 0

    # --- Dimension 2: Scope 1 & 2 ---
    dim2 = score_map.get(2)
    if dim2 and dim2.score >= 2:
        has_trend, has_both_scope2, in_t, out_t = _check_dim2(document_text, client, model)
        total_in += in_t
        total_out += out_t
        new_score = dim2.score
        if new_score == 3 and not has_trend:
            new_score = 2
        if new_score >= 2 and not has_both_scope2:
            new_score = 1
        if new_score != dim2.score:
            corrections[2] = (
                new_score,
                f"[Second-pass correction: {dim2.score}→{new_score}; "
                f"reduction_trend={has_trend}, both_scope2_types={has_both_scope2}]",
            )

    # --- Dimension 3: Scope 3 ---
    dim3 = score_map.get(3)
    if dim3 and dim3.score >= 2:
        scope3_reducing, in_t, out_t = _check_dim3(document_text, client, model)
        total_in += in_t
        total_out += out_t
        if dim3.score == 3 and not scope3_reducing:
            corrections[3] = (
                2,
                f"[Second-pass correction: 3→2; scope3_reducing={scope3_reducing}]",
            )

    # --- Dimension 5: SBTi ---
    dim5 = score_map.get(5)
    if dim5 and dim5.score == 2:
        sbti_validated, in_t, out_t = _check_dim5(document_text, client, model)
        total_in += in_t
        total_out += out_t
        if not sbti_validated:
            corrections[5] = (
                1,
                "[Second-pass correction: 2→1; SBTi aligned/methodology only, not validated]",
            )

    if corrections:
        for dim_id, (new_score, reason) in corrections.items():
            print(f"  [second-pass] dim{dim_id}: {reason}")

    new_scores = [
        dataclasses.replace(
            ds,
            score=corrections[ds.dimension_id][0],
            scoring_rationale=ds.scoring_rationale + " " + corrections[ds.dimension_id][1],
        )
        if ds.dimension_id in corrections
        else ds
        for ds in scorecard.scores
    ]

    return _SecondPassResult(
        scorecard=dataclasses.replace(scorecard, scores=new_scores) if corrections else scorecard,
        input_tokens=total_in,
        output_tokens=total_out,
    )


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

    second = _apply_second_pass(document_text, scorecard, client, model)

    return ScoringResult(
        scorecard=second.scorecard,
        input_tokens=response.usage.input_tokens + second.input_tokens,
        output_tokens=response.usage.output_tokens + second.output_tokens,
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
