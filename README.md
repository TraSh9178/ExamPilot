# ExamPilot

AI-powered exam preparation platform for any subject.

For the current account UI and fresh book-captain Pilot candidate, see
[testing on another computer](docs/other_computer_testing.md). This branch is
for UI/Auth testing; learning-record Save/Restore UI integration is pending.

## Accounts and login

The website requires an account before opening the learning pages. Users can
register with a username and password, log in, and log out from the sidebar.
Accounts use the existing PostgreSQL / Supabase database configuration.

See [account setup](docs/account_setup.md) for database configuration, schema
initialization, and local startup commands.

## Shared Data Contract — v1.0

ExamPilot uses a shared Pydantic data contract.

Source of truth:
- models/schemas.py

Example data:
- data/sample_course.json

Rules:
1. All members must use the shared schema.
2. Topic IDs must be unique.
3. Question IDs must be unique.
4. Every question must reference an existing topic.
5. Graph relationships must reference existing topics.
6. Schema changes require team approval.

Module ownership:
- A: Streamlit UI
- B: Gemini and document processing
- C: Exam and mastery engine
- D: Schema, knowledge graph, integration

Status: v1.0 candidate — pending team confirmation.
