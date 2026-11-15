# Guided Concept Lab

Limits and Derivatives now follow an optional predict → explore → explain flow. Prediction feedback is local formative feedback and never creates an exam attempt, changes a grade or adds mastery evidence. Changing a prediction hides stale feedback until checked again.

Both experiments have a deterministic step-closer action, stopping at the smallest nonzero distance, and a scoped reset that clears only that experiment's controls and prediction. Limits shows the original rational function and preserves the open circle at the undefined point. Derivatives supports left/right approach (signed h), a local/global view, consistent curve/secant/tangent color and dash encoding, an x₀ label and a numerical slope gap. Longer explanations and the value table remain collapsed. Existing topic-practice navigation and review gating remain unchanged. New controls support the existing Chinese UI setting.

Validation: 1004 passed, 20 skipped in the existing environment. Added tests cover optional prediction feedback, no exam-history writes, stepping/reset, signed left-hand convergence at several x₀ values, reset isolation and translation. Existing mathematical and registered navigation checks pass. Local browser preview verified left approach, slope-gap reduction and warning-free reset. Database/API access was disabled; this does not assert production deployment.

No dependencies, schemas or additional experiment topics were added in this iteration.

## Comparison and corner follow-up

The desktop layout places controls beside the graph; prediction prompts are optional collapsed panels. Wrong predictions now receive misconception-specific feedback with another attempt available. Derivatives can freeze one secant at a fixed x₀ for comparison as h changes; the saved line is hidden when x₀ changes, and reset clears it. A third |x| experiment demonstrates continuity with unequal left/right secant slopes at zero. It reuses the Derivatives practice route without writing grades. Chinese graph colors and dash legends share the same translated category domain.

Follow-up validation: 1018 passed, 20 skipped; local browser confirmed the corner layout and saved h = 0.5 secant remaining fixed when current h changed to 0.1. Independent corner reset, finite-distance validation, targeted feedback, comparison lifetime and Chinese labels are covered by tests. No new dependencies or persistence schemas. Production deployment still requires the deployment-source synchronization.
