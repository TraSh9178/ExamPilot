# Student-facing detail audit

Routine study pages should show decisions and learning evidence, while course maintenance stays behind an explicit entry.

- Study Plan groups question review/editing, account backup/recovery and source material under one collapsed Course tools panel. Pending-review actions remain discoverable. Question classification fields have an additional advanced expander. Source text can be read on demand.
- Learning DNA evidence retains the question, dimension, correctness, hint count and readable confidence label. Internal question IDs and session UUIDs are omitted from presentation; evidence computation and stored references are unchanged.
- Saved and unfinished practice choices show ordinal, mode, question count and result instead of session identifiers. Underlying widget values still select the original session.
- My account no longer displays its internal account ID.

Review requirements, save failures, AI disclosure, evidence limitations and material provenance remain available because they affect learner decisions. This is presentation cleanup, not a change to authentication or authorization.

Validation: 979 passed, 20 skipped; local Chrome sample-data preview confirmed Course tools is collapsed by default and expands to the three maintenance areas. Tests verify readable session selection still opens the correct result and evidence tables omit internal identifiers. No production credentials or live AI used.
