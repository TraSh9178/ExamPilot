# Shared built-in examples

Feature, UI and built-in catalog changes are product-wide. Each account receives the same shipped examples; only personal progress, review decisions and uploaded content remain account-specific.

After restoring account records, app.py synchronizes missing built-in demo content before rendering any page. Dashboard also applies the same helper for standalone entry. New accounts receive all three examples; legacy accounts receive new questions and the expanded Calculus graph even if an old demo-seeding marker is present. The common Calculus baseline is 15 topics, 20 relationships and 66 questions. Manual catalog-update controls and deletion of built-in examples are removed. User-created courses remain deletable.

Synchronization is append-only and idempotent. Existing questions, saved edits, reviews, historical answer snapshots, confirmed scopes, current selection and unfinished practice remain intact. No content is sent between accounts. Historical answers are not retroactively retagged. Existing question-review requirements still apply. The catalog is available locally on every login even before it is next saved through the ordinary account save flow; no bulk database migration or production credentials are required.

Validation: 987 passed, 20 skipped. Tests cover independent new-account catalogs, legacy updates, direct entry to Knowledge Map, stale course-list preservation, unchanged private history/scope/drafts and the absence of manual-update/delete actions for built-in examples. Deployment must run this version for the global behavior to take effect.
