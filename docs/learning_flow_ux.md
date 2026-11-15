# Learning flow UX

The dashboard now leads with the current course and a practice action. Secondary totals, question editing, metadata, time explanations and export instructions are collapsed. Progress separates Overview, Learning DNA and Practice details; practice results show next steps directly, with the per-question answer review on a page of its own (Review answers).

Topic actions carry their context: Knowledge Map opens the matching Concept Lab experiment, and topic practice opens new-session settings rather than an old result. Previous graded history remains accessible. Replacing unfinished practice archives a resumable draft, including answers, confidence and hints. Drafts live in the current Streamlit session; they are not durable across logout/server restart. Leaving practice pauses focus timing.

Validation: 957 passed, 20 skipped in the existing Python 3.12 Conda environment. New tests cover topic intents, draft restoration after registered-page navigation, default experiment selection and explicit new-session creation. Local Chrome preview uses synthetic sample data with database/API access disabled; verified the experiment-to-topic-practice flow and new question creation. This does not verify production deployment or live AI calls.

No dependencies, database schemas, grading rules or question approval rules changed.
