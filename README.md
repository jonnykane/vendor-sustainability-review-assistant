# Vendor Sustainability Review Assistant

A prototype AI assistant for reviewing vendor sustainability disclosures against a structured rubric. Built as a self-directed applied AI practice project.

# What it does
Drop in a vendor's public sustainability disclosure (PDF or HTML) and the tool extracts claims, scores them against a five-dimension rubric, and returns a structured scorecard with an evidence trail — source quotes, page references, confidence flags, and scoring rationale for every dimension.
The problem it solves: procurement teams currently spend 4–6 hours per vendor manually reviewing inconsistent ESG documents, with no audit trail and no way to scale review beyond their largest suppliers.

# How it works
Disclosure document (PDF / HTML)
        ↓
  Text extraction (pdfplumber / BeautifulSoup)
        ↓
  Claude API call — full document in context, structured output via tool use
        ↓
  VendorScorecard JSON (scores + evidence per dimension)
        ↓
  Agentic second pass (dims 2, 3, 5 only — triggered by score)
        ↓
  Final scorecard
Naive long-context, not RAG. All five disclosure documents fit within Claude's context window. Chunking was deliberately deferred — the eval showed full-context scoring performs well, and retrieval adds failure modes (split evidence across chunks) without clear benefit at this document scale.
Agentic second pass — bounded, not theatrical. After initial scoring, if dimension 2 (Scope 1&2), dimension 3 (Scope 3), or dimension 5 (SBTi) score 2 or 3, a targeted follow-up call applies stricter evidence criteria specific to that dimension's most common failure mode. Only three dimensions. Only when the score suggests a check is needed. Explainable to a procurement auditor.

# Rubric
Five dimensions, scored 0–3 (total 0–15). Every score requires a source quote (≤25 words), evidence location (page/section), confidence flag (high/medium/low), and scoring rationale.
#DimensionWhat distinguishes a 2 from a 31Net Zero commitment and transition planInterim 2030 target + annual progress reporting2Scope 1 & 2 emissions disclosure≥3 years of data showing absolute reduction trend3Scope 3 emissions disclosureEvidenced supplier programme reducing emissions (not just engaging)4Third-party verification and assuranceReasonable assurance (ISAE 3000) vs limited assurance5Science-based targets validationSBTi validated (not aligned, not methodology-only)
The distinction between adjacent scores is where the model earns its keep — and where greenwashing tends to hide. "SBTi-aligned" is not "SBTi-validated." "Offset-based carbon neutral" is not "Net Zero." "Supplier engagement programme" is not "demonstrated Scope 3 reduction." The rubric and prompt are both written to catch these.

# Evaluation
Golden set
Five vendors scored by GPT-4o against the rubric, with human spot-check on ~20% of dimensions. Cross-model scoring was used rather than self-scoring to avoid unconscious calibration toward expected model output.
VendorFormatScoreRole in eval setMicrosoftReal PDF (~90pp)10/15Real-world parsing, real evidence patternsSentinel RecordsSynthetic PDF (7pp)12/15Top-of-rubric discriminationArchive Northern IrelandSynthetic PDF (5pp)6/15Partial disclosure, missing-data detectionBoxVault StorageSynthetic HTML6/15Greenwashing detection — surface score vs evidence scoreHeritage Document ServicesSynthetic HTML0/15"No evidence found" failure mode
The four synthetic vendors were purpose-built to exercise specific failure modes. BoxVault is the most important: its marketing surface (badges reading "Carbon Neutral", "SBTi Aligned", "Independently Verified") scores 9–10 on a naive read; the actual evidence (offsets not reductions, internal not external assurance, SBTi methodology not validation) scores 6.
v0 — naive long-context pipeline
MetricValueExact match60.0%Within-one match100.0%Mean absolute error0.40Directional bias+0.32Unsupported claim rate0.0%Hallucinated-zero rate0.0%
The model was never badly wrong (100% within-one) but showed systematic positive bias. Every error was over-scoring, not under-scoring. The model found real evidence on every dimension but read it too generously — accepting a disclosed trend as a demonstrated reduction, and supplier engagement as demonstrated Scope 3 reduction.
v1 — agentic second pass
Metricv0v1ChangeExact match60.0%80.0%+20 ptsWithin-one match100.0%100.0%—Mean absolute error0.400.20halvedDirectional bias+0.32+0.04nearly eliminated
The second pass triggered on 5 of 25 dimension comparisons across the five vendors:

Archive NI dim 2: 2→1 (no reduction trend, market-based Scope 2 absent) ✓
BoxVault dim 2: 2→1 (same) ✓
BoxVault dim 5: 2→1 (SBTi aligned/methodology only, not validated) ✓
Microsoft dim 3: 3→2 (Scope 3 not reducing, only supplier engagement) ✓
Sentinel dim 3: 3→2 (same) ✓

BoxVault is now scored at exactly 6/15 — matching ground truth, all five dimensions correct.
Known issues and v2 targets
Microsoft dim 2 overcorrection (model=1, truth=2). The second pass is too binary on the reduction trend criterion — it drops to 1 when the trend is absent, but GHG Protocol methodology and dual Scope 2 disclosure are still present and worth a 2. Fix: add a floor rule — if methodology is present and both Scope 2 types are disclosed, minimum score is 2.
Sentinel dim 5 (model=3, truth=2). The model reads near-term SBTi validation as sufficient for a 3. The rubric requires both near-term and Net Zero validation plus published progress. Second-pass prompt tightening needed.
Archive NI dim 3 (model=2, truth=1). Partial Scope 3 (2 categories) is being upgraded to a 2. A category-count check would fix this — fewer than 5 categories cannot score 2.

# Eval harness
The eval harness (eval-harness/) compares model-generated scorecards against the golden set and produces both JSON and Markdown reports. Two metric families are deliberately kept separate:
Score metrics — does the model agree with ground truth?
exact_match_rate, within_one_rate, mae, directional_bias
Evidence metrics — is the model's reasoning trustworthy?
unsupported_claim_rate, hallucinated_zero_rate, overclaim_rate, underclaim_rate
overclaim_rate is sustainability-specific: it catches over-scoring while citing evidence — the procurement failure mode where the model finds a real quote but reads it as stronger than it is. This is distinct from hallucination (no evidence at all) and more dangerous for audit purposes.
Evidence validity (does the cited quote actually support the score?) is not automated — it requires human judgement. eval_evidence_validity_spotcheck.py samples 20% of dimensions for manual review.

# Project structure
vendor-sustainability-review-assistant/
  src/
    score_vendor.py          # scoring pipeline (v0 + v1 second pass)
    run_pipeline.py          # runs all vendors, saves ModelRun JSON
  eval-harness/
    schemas.py               # dataclasses for all data types
    io_scorecards.py         # JSON load/save
    eval_metrics.py          # all metrics
    eval.py                  # main eval entrypoint
    eval_evidence_validity_spotcheck.py
    smoke_test.py
    build_golden_set.py
  data/vendors/              # disclosure documents
  golden/                    # golden_set_v1.json
  scores/                    # per-vendor ChatGPT ground-truth JSONs
  runs/                      # pipeline run outputs
  outputs/                   # eval reports (JSON + Markdown)

Running it
bash# Install dependencies
pip install anthropic pdfplumber beautifulsoup4 lxml

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Score a single vendor
python src/score_vendor.py data/vendors/microsoft/2025-Microsoft-Environmental-Sustainability-Report.pdf

# Run full pipeline against all vendors
python src/run_pipeline.py

# Run eval against golden set
python eval-harness/eval.py \
  --golden golden/golden_set_v1.json \
  --run runs/<run-file>.json

# What I learned
The model was strongest on dimensions 1 (Net Zero commitment) and 4 (third-party assurance) — both have clear binary markers in disclosure documents. It was weakest on dimensions 2 and 3 (Scope 1&2 and Scope 3) where the distinction between disclosure and demonstrated reduction requires reading multiple data points together across a long document.
The most valuable single step in the project was building the golden dataset before writing any model code. It converted the rubric from a description of correct behaviour into a measurable specification, and it produced the failure taxonomy (dims 2, 3, 5 over-score; Heritage clean; BoxVault underweighted) before a line of pipeline code existed.
The agentic second pass was justified by the eval, not added speculatively. That ordering matters — adding agentic complexity before measuring where you need it produces systems that are hard to explain and harder to maintain.

# What I would do next

Fix the three known v1 scoring issues (Microsoft dim 2 floor rule, Sentinel dim 5 prompt tightening, Archive NI dim 3 category count)
Expand the golden set from 5 to 15 vendors
Add the evidence validity spot-check pass and report the human-validated rate alongside automated metrics
Build a reviewer UI: vendor selector, scorecard view, evidence drill-down, approve/edit/reject actions
Explore whether retrieval (RAG) improves Scope 3 scoring on very long reports where material evidence is deep in appendices
