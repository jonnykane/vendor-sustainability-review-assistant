# vendor-sustainability-review-assistant

An AI-assisted tool for reviewing and scoring vendor sustainability reports against a structured evaluation framework.

> Documentation will be updated as the project develops.

----
v0 naive pipeline achieves 100% within-one accuracy but shows consistent positive bias (+0.32) driven by dimensions 2 and 3 (Scope 1&2 and Scope 3, both +0.60). The model reliably finds evidence but over-reads it — scoring a disclosed trend as a demonstrated reduction, and scoring supplier engagement as demonstrated Scope 3 reduction. No unsupported claims or hallucinated zeros. Agentic second pass targets dims 2 and 3 with stricter evidence criteria

----
The v1 agentic second pass reduced exact match error from 40% to 20% (80% exact match) and directional bias from +0.32 to +0.04. The second pass triggers targeted follow-up calls on dimensions 2, 3, and 5 when initial scores are 2 or 3, applying stricter evidence criteria: demonstrated reduction trend vs disclosed trend (dim 2), actual Scope 3 reduction vs supplier engagement (dim 3), SBTi validated vs SBTi aligned (dim 5). BoxVault — the greenwashing test case — moved from 8/15 to 6/15 (exact match with ground truth). One overcorrection remains on Microsoft dim 2 where the second pass is too binary on the reduction trend criterion.
