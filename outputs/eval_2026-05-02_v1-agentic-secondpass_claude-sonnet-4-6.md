# Eval Report: `2026-05-02_v1-agentic-secondpass_claude-sonnet-4-6`

- Pipeline: `v1-agentic-secondpass`
- Model: `claude-sonnet-4-6`
- Prompt version: `v1`
- Rubric version: `1.0`
- Golden set: Golden set v1.0 — 5 vendors
- Vendors compared: 5 (25 dimension comparisons)

## Overall metrics

| Metric | Value |
| --- | --- |
| Exact match | 80.0% |
| Within-one match | 100.0% |
| Mean absolute error | 0.20 |
| Directional bias | +0.04 |
| Unsupported claim rate | 0.0% |
| Hallucinated-zero rate | 0.0% |
| Evidence present when scored | 100.0% |

## By dimension

| # | Dimension | Exact | Within-1 | MAE | Bias | Unsupp. |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Net Zero commitment and transition plan | 80% | 100% | 0.20 | +0.20 | 0% |
| 2 | Scope 1 & 2 emissions disclosure | 80% | 100% | 0.20 | -0.20 | 0% |
| 3 | Scope 3 emissions disclosure | 80% | 100% | 0.20 | +0.20 | 0% |
| 4 | Third-party verification and assurance | 80% | 100% | 0.20 | -0.20 | 0% |
| 5 | Science-based targets validation | 80% | 100% | 0.20 | +0.20 | 0% |

## By vendor

| Vendor | Exact | Within-1 | MAE | Bias |
| --- | --- | --- | --- | --- |
| archive_ni | 60% | 100% | 0.40 | +0.00 |
| boxvault | 100% | 100% | 0.00 | +0.00 |
| heritage | 80% | 100% | 0.20 | +0.20 |
| microsoft | 80% | 100% | 0.20 | -0.20 |
| sentinel_records | 80% | 100% | 0.20 | +0.20 |

## Confusion matrix (truth rows × model cols, scores 0-3)

```
         model→  0    1    2    3
truth ↓
   0              4    1    0    0
   1              1    7    1    0
   2              0    1    6    1
   3              0    0    0    3
```

## Worst cases (top 10 by absolute error)

| Vendor | Dim | Name | Truth | Model | Abs err | Unsupported? | Hallucinated zero? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| microsoft | 2 | Scope 1 & 2 emissions disclosure | 2 | 1 | 1 | no | no |
| sentinel_records | 5 | Science-based targets validation | 2 | 3 | 1 | no | no |
| archive_ni | 3 | Scope 3 emissions disclosure | 1 | 2 | 1 | no | no |
| archive_ni | 4 | Third-party verification and assurance | 1 | 0 | 1 | no | no |
| heritage | 1 | Net Zero commitment and transition plan | 0 | 1 | 1 | no | no |
| microsoft | 1 | Net Zero commitment and transition plan | 3 | 3 | 0 | no | no |
| microsoft | 3 | Scope 3 emissions disclosure | 2 | 2 | 0 | no | no |
| microsoft | 4 | Third-party verification and assurance | 2 | 2 | 0 | no | no |
| microsoft | 5 | Science-based targets validation | 1 | 1 | 0 | no | no |
| sentinel_records | 1 | Net Zero commitment and transition plan | 3 | 3 | 0 | no | no |
