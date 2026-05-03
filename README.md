# Vendor Sustainability Review Assistant

An AI-assisted procurement tool for reviewing vendor sustainability disclosures. Vendors are scored against a five-dimension rubric, with evidence-backed scores for human review.

**Live demo:** https://scorecard-spotlight-71.lovable.app

---

## The problem

Procurement teams assessing vendor sustainability disclosures face three compounding problems: reviews take 4–6 hours per vendor, scoring is inconsistent across reviewers, and there is no audit trail connecting scores to source evidence. As regulatory pressure increases (PPN 06/21, CSRD), this is becoming a compliance risk, not just an operational inconvenience.

---

## What this does

Drop in a vendor's public sustainability disclosure (PDF or HTML) and the tool:

1. Extracts the full document text
2. Calls Claude with a structured rubric prompt via tool use
3. Returns a scorecard with a 0–3 score per dimension, a supporting evidence quote, source location, confidence flag, and scoring rationale
4. Runs a targeted agentic second pass on dimensions where over-scoring is most likely
5. Produces a structured JSON scorecard ready for human review

The reviewer sees scores, evidence, and a source citation for every dimension. They approve, edit, or reject each score. The tool supports human review — it does not automate vendor approval.

---

## How it works

```
Disclosure document (PDF / HTML)
        ↓
  Text extraction (pdfplumber / BeautifulSoup)
        ↓
  Claude API — full document in context, structured output via tool use
        ↓
  VendorScorecard JSON (score + evidence quote + source + confidence per dimension)
        ↓
  Agentic second pass (dims 2, 3, 5 — triggered by score, not always active)
        ↓
  Final scorecard → human reviewer
```

**Why naive long-context, not RAG.** All test documents fit within Claude's context window (largest: ~90pp Microsoft PDF, ~58k tokens). Full-context scoring preserves connections between evidence spread across a long report — chunking would break these. Retrieval will be evaluated for larger document sets where full-context becomes impractical.

**Why an agentic second pass.** The v0 eval showed consistent over-scoring on three dimensions (+0.60 bias on dims 2 and 3, +0.40 on dim 5). The second pass adds a decision point: if dim 2 or 3 scored 2 or 3, or dim 5 scored 2, a targeted follow-up call applies stricter evidence criteria. This is bounded — three dimensions, three targeted checks — and explainable to a procurement auditor.

---

## Rubric

Five dimensions, scored 0–3 (total 0–15). Every score requires a source quote (≤25 words), evidence location (page/section), confidence flag (high/medium/low), and scoring rationale.

| # | Dimension | Score 2 requires | Score 3 also requires |
|---|---|---|---|
| 1 | Net Zero commitment and transition plan | Published plan with target year ≤2050 and baseline | Interim 2030 target + annual progress reporting |
| 2 | Scope 1 & 2 emissions disclosure | GHG Protocol, both location- and market-based Scope 2 | ≥3 years showing absolute reduction trend |
| 3 | Scope 3 emissions disclosure | All material categories with materiality assessment | Evidenced supplier programme *reducing* emissions |
| 4 | Third-party verification and assurance | External assurance to ISAE 3000 (limited) | Reasonable assurance or AA1000AS Type 2 |
| 5 | Science-based targets validation | SBTi-*validated* near-term targets | SBTi-validated near-term and Net Zero + progress |

The rubric is designed to surface greenwashing. "SBTi-aligned" is not "SBTi-validated." "Offset-based carbon neutral" is not "Net Zero." "Supplier engagement programme" is not "demonstrated Scope 3 reduction." These distinctions are explicit in both the rubric and the agentic second-pass prompts.

---

## Evaluation

### Golden set

Five vendors scored by GPT-4o against the rubric, with human spot-check on ~20% of dimensions. Cross-model scoring was used rather than self-scoring to avoid unconscious calibration toward expected pipeline output. Ground truth scores are displayed alongside model scores in the live demo.

| Vendor | Format | Ground truth | Role in eval set |
|---|---|---|---|
| Microsoft | Real PDF (~90pp) | 10/15 | Real-world parsing, real evidence patterns |
| Sentinel Records | Synthetic PDF (7pp) | 12/15 | Top-of-rubric discrimination |
| Archive Northern Ireland | Synthetic PDF (5pp) | 6/15 | Partial disclosure, missing-data detection |
| BoxVault Storage | Synthetic HTML | 6/15 | Greenwashing detection |
| Heritage Document Services | Synthetic HTML | 0/15 | No-evidence failure mode |

BoxVault is the most important test case. Its marketing surface (badges: "Carbon Neutral", "SBTi Aligned", "Independently Verified") would score 9–10 on a naive read. The actual evidence (offsets not reductions, internal not external assurance, SBTi methodology not validation) scores 6. The pipeline correctly identifies the gap and flags it in the overall notes.

### v0 — naive long-context pipeline

| Metric | Value |
|---|---|
| Exact match | 60.0% |
| Within-one match | 100.0% |
| Mean absolute error | 0.40 |
| Directional bias | +0.32 |
| Unsupported claim rate | 0.0% |
| Hallucinated-zero rate | 0.0% |

The model was never badly wrong (100% within-one) but showed systematic positive bias. Every error was over-scoring. The model found real evidence but read it too generously — accepting disclosed trends as demonstrated reductions, and supplier engagement as demonstrated Scope 3 reduction.

### v1 — agentic second pass

| Metric | v0 | v1 | Change |
|---|---|---|---|
| Exact match | 60.0% | **80.0%** | +20 pts |
| Within-one match | 100.0% | 100.0% | — |
| Mean absolute error | 0.40 | **0.20** | halved |
| Directional bias | +0.32 | **+0.04** | nearly eliminated |

Second-pass corrections across the five-vendor run:

| Vendor | Dimension | Correction | Reason |
|---|---|---|---|
| Archive NI | Scope 1 & 2 | 2 → 1 | No reduction trend; market-based Scope 2 absent |
| BoxVault | Scope 1 & 2 | 2 → 1 | Same |
| BoxVault | SBTi validation | 2 → 1 | SBTi aligned/methodology only, not validated |
| Microsoft | Scope 3 | 3 → 2 | Scope 3 not reducing; supplier engagement only |
| Sentinel Records | Scope 3 | 3 → 2 | Same |

BoxVault: 8/15 (v0) → 6/15 (v1), matching ground truth exactly. All five dimensions correct.

### Known issues and v2 targets

**Microsoft dim 2 overcorrection (model=1, truth=2).** The second pass drops to 1 when a reduction trend is absent, but GHG Protocol methodology and dual Scope 2 disclosure are still worth a 2. Fix: add a floor rule — if methodology is present and both Scope 2 types are disclosed, minimum score is 2 regardless of trend.

**Sentinel dim 5 (model=3, truth=2).** Near-term SBTi validation read as sufficient for a 3; the rubric requires both near-term and Net Zero validation plus published progress.

**Archive NI dim 3 (model=2, truth=1).** Partial Scope 3 (2 categories) upgraded to a 2. A category-count check would fix this.

---

## Eval harness

The eval harness (`eval-harness/`) compares model-generated scorecards against the golden set and produces JSON and Markdown reports.

**Two metric families, deliberately separate:**

*Score metrics* — does the model agree with ground truth?
`exact_match_rate`, `within_one_rate`, `mae`, `directional_bias`

*Evidence metrics* — is the model's reasoning trustworthy?
`unsupported_claim_rate`, `hallucinated_zero_rate`, `overclaim_rate`, `underclaim_rate`

`overclaim_rate` is sustainability-specific: it catches over-scoring *while citing evidence* — the procurement failure mode where the model finds a real quote but reads it as stronger than it is. This is distinct from hallucination (no evidence at all) and more dangerous for audit purposes, because it looks correct.

Evidence validity (does the cited quote actually support the score?) is not automated — it requires human judgement. `eval_evidence_validity_spotcheck.py` samples 20% of dimensions for manual review.

---

## Project structure

```
vendor-sustainability-review-assistant/
  src/
    score_vendor.py          # scoring pipeline — v0 extraction + v1 second pass
    run_pipeline.py          # runs all vendors, saves ModelRun JSON
    data/
      scorecards.json        # pipeline output consumed by the UI
  eval-harness/
    schemas.py               # dataclasses for all data types
    io_scorecards.py         # JSON load/save
    eval_metrics.py          # score + evidence metrics incl. overclaim_rate
    eval.py                  # main eval entrypoint — CLI, JSON + Markdown output
    eval_evidence_validity_spotcheck.py
    smoke_test.py
    build_golden_set.py
  data/vendors/              # disclosure documents (PDF + HTML)
  golden/
    golden_set_v1.json       # ground truth — 5 vendors, GPT-scored, human spot-checked
  scores/                    # per-vendor ChatGPT ground-truth JSONs
  runs/                      # pipeline run output JSONs
  outputs/                   # eval reports (JSON + Markdown)
```

---

## Running it

```bash
# Install dependencies
pip install anthropic pdfplumber beautifulsoup4 lxml

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Score a single vendor
python src/score_vendor.py data/vendors/microsoft/2025-Microsoft-Environmental-Sustainability-Report.pdf

# Run full pipeline (all vendors)
python src/run_pipeline.py

# Run eval against golden set
python eval-harness/eval.py \
  --golden golden/golden_set_v1.json \
  --run runs/<run-file>.json
```

---

## What I learned

**Build the golden set before writing model code.** The rubric becomes a measurable specification the moment you have ground truth to compare against. The failure taxonomy (dims 2 and 3 over-score; BoxVault greenwashing underweighted; Heritage correctly scored zero) emerged from the eval, not from speculation — and it determined exactly where the agentic second pass needed to go.

**The agentic second pass was justified by the eval, not added speculatively.** Adding agentic complexity before measuring where you need it produces systems that are hard to explain and harder to maintain. Measuring first, then targeting the intervention, is what makes the before/after story credible.

**Overclaiming is a different failure mode from hallucinating.** A model that scores correctly but fabricates citations is dangerous. A model that finds real evidence and over-reads it is more dangerous in a procurement context — because it looks correct. The eval harness separates these explicitly.

**Long-context before RAG.** For document-scale tasks where evidence is spread across a report, full-context scoring preserves connections that chunking would break. Retrieval is worth adding when documents exceed the context window or when you're querying across many documents simultaneously — not as a default.

---

## What I would do next

- Fix the three known v1 scoring issues (Microsoft dim 2 floor rule, Sentinel dim 5 prompt tightening, Archive NI dim 3 category count)
- Expand the golden set from 5 to 15 vendors with more real disclosures
- Add the evidence validity spot-check pass and surface the human-validated rate alongside automated metrics
- Test whether retrieval (RAG) improves Scope 3 scoring on very long reports where material evidence is deep in appendices
- Add a file upload endpoint wrapping the scoring pipeline so users can add vendors without developer access — the main engineering   consideration is handling 30–50 second scoring latency gracefully.
- Add reviewer feedback loop — approved/edited/rejected decisions feed back into prompt refinement

---

## UI

Live demo built in Lovable, deployed on Lovable's hosting.

**https://scorecard-spotlight-71.lovable.app**

Frontend repo: https://github.com/jonnykane/scorecard-spotlight-71

Three views: vendor list with score bars and evidence quality badges, vendor detail with expandable dimension cards showing score, rationale, evidence quote, source location, confidence badge, and human review actions (Approve / Edit / Reject), and a comparison table showing all five vendors across all five dimensions.

---

*Self-directed practice project. Built May 2026 using Claude, Claude Code, and Lovable. Not a real client engagement.*
