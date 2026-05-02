# vendor-sustainability-review-assistant

An AI-assisted tool for reviewing and scoring vendor sustainability reports against a structured evaluation framework.

> Documentation will be updated as the project develops.

----
v0 naive pipeline achieves 100% within-one accuracy but shows consistent positive bias (+0.32) driven by dimensions 2 and 3 (Scope 1&2 and Scope 3, both +0.60). The model reliably finds evidence but over-reads it — scoring a disclosed trend as a demonstrated reduction, and scoring supplier engagement as demonstrated Scope 3 reduction. No unsupported claims or hallucinated zeros. Agentic second pass targets dims 2 and 3 with stricter evidence criteria
