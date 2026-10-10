# ExamPilot — Interface Contract v1.1

**Status:** Agreed for MVP implementation; integration testing pending
**Owner:** D — Architecture & Integration
**Applies to:** A (UI), B (Gemini), C (Exam & Mastery), D (Graph)

## 1. Shared Data Contract

The source of truth is `models/schemas.py`.

All modules must reuse the existing models:

- `Topic`
- `Relationship`
- `Question`
- `StudyPackage`
- `ExamSession`
- `AttemptResult`
- `TopicStats`

Do not modify shared Schema fields without team approval.

`data/sample_course.json` is the shared integration fixture. AI-generated questions must be validated and reviewed before being used in an exam.

## 2. Confirmed Exam Scope

The shared parameter is:

`confirmed_topic_ids: list[str]`

Rules:

- A collects user-confirmed topic IDs.
- B uses the confirmed scope when generating questions.
- C uses the same scope when assembling exams.
- D retains the full knowledge graph, including topics outside the current exam scope.
- Missing confirmation, empty lists, duplicate IDs, and unknown IDs must be rejected.
- Never assume all topics are confirmed unless the user explicitly selects all.

## 3. Gemini Service — B

Question generation interface:

`generate_questions(document, package, confirmed_topic_ids)`

B must validate confirmed topic IDs against the course topics.

Generated question `topic_id` values must belong to the confirmed scope.

AI-generated content remains pending human review. Successful Pydantic validation does not establish factual correctness.

The UI must validate a package dictionary using `StudyPackage.model_validate()` before passing it to a service requiring a `StudyPackage` object.

## 4. Exam Engine — C

### 4.1 Exam Creation

Interface:

`create_exam(package, mode, requested_count, confirmed_topic_ids, topic_id=None)`

Input constraints:

- `package`: `StudyPackage`
- `mode`: `"mock"` or `"topic"`
- `requested_count`: positive integer, excluding booleans
- `confirmed_topic_ids`: nonempty, unique, existing topic IDs
- For `"mock"`, `topic_id` must be `None`.
- For `"topic"`, `topic_id` must exist in `confirmed_topic_ids`.

Successful return:

```python
{
    "session": ExamSession,
    "questions": list[Question],
    "warning": str | None,
}
```

Rules:

- Only eligible questions may be selected.
- Questions must not be repeated within one session.
- `session.question_ids` must match the returned questions in order.
- If fewer questions are available than requested, use the available questions and return a warning.
- If zero questions are eligible, raise a clear `ValueError`.
- Invalid inputs must produce explicit errors.

### 4.2 Exam Grading

Interface:

`grade_exam(session, questions, selected_answers)`

Answer mapping:

```python
{
    "q001": 1,
    "q002": None,
    "q003": 0,
}
```

The key is a question ID. The value is an option index from 0 to 3, or `None` for unanswered.

A missing question key is also treated as unanswered.

Unknown question IDs, invalid option indices, booleans, and incompatible question/session references must be rejected.

Successful return:

```python
{
    "session_id": str,
    "correct_count": int,
    "total_count": int,
    "accuracy": float,
    "attempts": list[AttemptResult],
    "question_results": list[dict],
}
```

Each `question_results` entry contains:

- `question_id: str`
- `selected_index: int | None`
- `is_correct: bool`
- `correct_index: int`
- `explanation: str`

All `AttemptResult.session_id` values must equal the graded session ID.

Unanswered questions count toward `total_count` and are incorrect. Empty sessions must be rejected.

Accuracy is expressed as a percentage from 0 to 100, rounded to two decimal places for the MVP.

Correct answers and explanations must not be shown to the learner before exam submission.

## 5. Mastery Engine — C

Interface:

`calculate_topic_stats(attempts, sessions, questions) -> list[TopicStats]`

Statistics are grouped by `(topic_id, mode)`.

The modes `"mock"` and `"topic"` must be tracked separately.

For the MVP, `attempted` counts graded question records, including unanswered questions.

The service must validate session/question references and reject duplicate attempts for the same session and question.

A missing topic/mode combination represents no recorded attempts, not 0% accuracy.

Mastery status interface:

`get_mastery_status(stats) -> str`

| Condition | Status |
|---|---|
| 0 attempts | `unattempted` |
| 1–2 attempts | `insufficient_evidence` |
| 3+ attempts, accuracy below 60% | `weak` |
| 3+ attempts, accuracy 60% to below 80% | `developing` |
| 3+ attempts, accuracy 80% or above | `mastered` |

These thresholds are provisional MVP feedback rules, not a validated measure of educational mastery.

The shared `TopicStats` Schema does not receive a new `status` field.

## 6. Frontend — A

A is responsible for:

- Loading and validating a `StudyPackage`.
- Collecting explicit exam-scope confirmation.
- Passing confirmed topic IDs to B and C.
- Displaying available-question warnings.
- Using `session` and `questions` returned by C.
- Providing `selected_answers` keyed by question ID.
- Displaying scores, corrections, and explanations only after submission.
- Displaying all five mastery statuses.

Pydantic objects may be accessed using attributes or serialized with `.model_dump()` when necessary.

## 7. Knowledge Graph — D

The graph engine uses:

- `StudyPackage.topics` for nodes.
- `StudyPackage.relationships` for edges.
- `TopicStats` and mastery status for learning feedback.

The graph retains all course topics, even when the confirmed exam scope includes only some of them.

Graph transformations must not mutate the shared Pydantic models.

The MVP graph must support missing mastery records and all five status values.

## 8. Development Environments

| Member | OS | Branch |
|---|---|---|
| A | macOS | `feature/ui` |
| B | macOS | `feature/gemini` |
| C | Windows | `feature/exam` |
| D | Windows | `feature/graph` |

Use `requirements.txt` for shared Python dependencies.

macOS virtual environment Python: `.venv/bin/python`

Windows PowerShell virtual environment Python: `.\.venv\Scripts\python.exe`

Never commit API keys, `.env`, `.venv`, or private course materials.

## 9. Version Control and Handoff

Develop only on assigned feature branches.

Commit messages must follow:

`<type>(<scope>): <concise English description>`

Every pushed change must include a handoff report containing:

- Owner
- Branch
- Commit
- Completed
- Files changed
- How to test
- Result
- Known issues
- Needs integration

Only report a Push or Merge as successful after it has actually succeeded.

## 10. Integration Acceptance

Before declaring the interfaces integrated, verify:

1. The sample `StudyPackage` validates.
2. Confirmed exam scope is enforced by B and C.
3. Insufficient question counts return a warning without duplicated questions.
4. Exam grading handles unanswered and invalid answers.
5. Mastery statistics distinguish mock and topic modes.
6. The UI does not reveal answers before submission.
7. The graph handles absent mastery records and all five statuses.
8. Tests run successfully in the relevant environments.

**Current limitation:** This document specifies agreed interfaces. It does not claim all functions are implemented or end-to-end integration is complete.