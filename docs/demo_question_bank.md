# Demo question bank expansion

Each demo now contains 30 questions, with 10 in each existing topic. Existing topic IDs, question IDs, answers and relationships are preserved. This adds 75 questions to the original 15.

| Course | Topics | Existing questions | Added questions |
| --- | --- | ---: | ---: |
| Calculus I | Limits; Derivatives; Applications of Derivatives | 3 | 27 |
| Introduction to Microeconomics | Supply and Demand; Price Elasticity of Demand; Price Controls | 3 | 27 |
| Python Basics | Variables and Expressions; Conditionals; Loops | 9 | 21 |

Calculus includes the Concept Lab functions, the distinction between a limit and a function value, one-sided limits, differentiation rules, tangent lines, extrema and optimization. Economics includes curve shifts, equilibrium, elasticity calculations and price controls with explicit model assumptions. Python includes short execution traces, expression precedence, conditionals, accumulation, nested loops, break and continue.

## Review before use

All added questions are AI-authored drafts marked `pending` in `learning_state.question_reviews`. They are excluded from practice until a person checks the answer, distractors and explanation and approves them in Study Plan → Review and edit questions. Automated checks and code execution do not substitute for human content review. The existing questions retain their previous availability.

The historical Python metadata approval covers only q1–q9; an expansion entry records q10–q30 as pending. No reviewer name or approval date has been invented for the new material. These demo questions have no supplied textbook or uploaded-document page sources, so `source_pages` stays empty.

Load the updated demo from the Dashboard to obtain its revised bank. Already saved account courses are not migrated automatically. Do not replace a saved course with valuable progress without checking the app's existing course-loading behavior.

## Validation

Tests check topic counts, normalized uniqueness, review gating, existing Study Plan approval, and generation and grading of ten-question topic sessions after simulated approval. All 21 new Python answers are checked with fixed executable examples; numerical calculus and economics cases are cross-checked against formulas. Conceptual correctness and distractor quality still require human review.

The original 15 questions keep their existing step hints. The 75 new drafts have explanations but no step hints yet; after approval the practice page uses its existing no-hints behavior.

No dependencies, database schema, generation services or practice-page code change.
