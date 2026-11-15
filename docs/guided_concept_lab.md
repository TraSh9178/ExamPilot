# Guided Concept Lab

Limits and Derivatives now follow an optional predict → explore → explain flow. Prediction feedback is local formative feedback and never creates an exam attempt, changes a grade or adds mastery evidence. Changing a prediction hides stale feedback until checked again.

Both experiments have a deterministic step-closer action, stopping at the smallest nonzero distance, and a scoped reset that clears only that experiment's controls and prediction. Limits shows the original rational function and preserves the open circle at the undefined point. Derivatives supports left/right approach (signed h), a local/global view, consistent curve/secant/tangent color and dash encoding, an x₀ label and a numerical slope gap. Longer explanations and the value table remain collapsed. Existing topic-practice navigation and review gating remain unchanged. New controls support the existing Chinese UI setting.

Validation: 1004 passed, 20 skipped in the existing environment. Added tests cover optional prediction feedback, no exam-history writes, stepping/reset, signed left-hand convergence at several x₀ values, reset isolation and translation. Existing mathematical and registered navigation checks pass. Local browser preview verified left approach, slope-gap reduction and warning-free reset. Database/API access was disabled; this does not assert production deployment.

No dependencies, schemas or additional experiment topics were added in this iteration.
