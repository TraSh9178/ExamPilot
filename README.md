# ExamPilot
AI-powered exam preparation platform for any subject
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