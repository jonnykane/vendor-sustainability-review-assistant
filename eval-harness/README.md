# Eval Harness

Compare model-generated vendor scorecards against a ground-truth golden set.

## Files

- `schemas.py` — dataclasses for `DimensionScore`, `VendorScorecard`, `GoldenSet`, `ModelRun`. Source of truth for shape + versioning.
- `io_scorecards.py` — JSON load/save for scorecards. Includes `ingest_chatgpt_scores()` to assemble individual ChatGPT JSON outputs into a `GoldenSet`.
- `eval_metrics.py` — score-level metrics (exact match, within-one, MAE, bias) and evidence-level metrics (unsupported claim rate, hallucinated zero rate). Plus confusion matrix.
- `eval.py` — main entry point. Compares one model run to one golden set, writes JSON + Markdown reports.
- `eval_evidence_validity_spotcheck.py` — samples 20% of dimensions for human review of whether cited quotes actually support the score.
- `smoke_test.py` — fabricated end-to-end test. Run this first to confirm the harness works.

## Two metric families, deliberately separate

**Score metrics** answer: *does the model agree with ground truth?*
- `exact_match_rate`, `within_one_rate`, `mae`, `directional_bias`

**Evidence metrics** answer: *is the model's reasoning trustworthy?*
- `unsupported_claim_rate` — model gave a non-zero score with no evidence
- `hallucinated_zero_rate` — model said "no evidence" but ground truth had evidence
- `evidence_present_when_scored` — % of non-zero scores with citations

Evidence *validity* (does the cited quote actually support the score?) is **not automatable** — it requires human review. Use `eval_evidence_validity_spotcheck.py` to produce a CSV for that.

## Workflow

1. **Build the golden set.** Score each vendor with ChatGPT (or whoever) using the rubric prompt. Each vendor produces a JSON blob.
2. **Ingest into a golden set.** `ingest_chatgpt_scores([json files], scorer_label="gpt-4o", scoring_date="2026-05-01")` returns a `GoldenSet`. Save with `save_golden_set()`.
3. **Run your model pipeline.** Produces a `ModelRun` with the same shape. Save with `save_model_run()`.
4. **Compare.** `python eval.py --golden golden/golden_set.json --run runs/2026-05-02_v0_naive.json`

Outputs:
- `outputs/eval_<run_id>.json` — full structured report
- `outputs/eval_<run_id>.md` — markdown summary, drop into the README

5. **Spot-check evidence.** `python eval_evidence_validity_spotcheck.py --run runs/2026-05-02_v0_naive.json` writes a CSV; mark each `human_verdict` as VALID / PARTIAL / INVALID.

## Versioning

`RUBRIC_VERSION` and `SCHEMA_VERSION` live in `schemas.py`. Bump them when the rubric or schema changes. `eval.py` refuses to compare runs with different rubric versions — re-score one side first.

## Why this shape

The harness is built so you can run it many times as the model + prompt evolve. Each `ModelRun` records its `prompt_version` and `pipeline_version`, so comparing v0-naive vs v1-agentic-second-pass is just running `eval.py` twice and diffing the markdown.

The split between automated metrics (eval.py) and the evidence spot-check is deliberate: for a procurement use case, a confidently-wrong citation is the actual product failure mode. Surfacing that distinction in the metrics is the point.
