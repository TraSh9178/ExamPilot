# UI Handoff Summary

## Current integration follow-up

- **Owner:** A — UI
- **Branch:** `feature/ui-tutor-pptx`
- **Baseline:** `origin/main` `5b7e92af42a6246ef4f5faafff63c6faf861bd75` (includes PR #15 / `5440f17`)
- **State:** Independent Tutor/PPTX UI branch; does not include the Anki page (PR #14) or database persistence.
- **Tutor:** Connected the existing `ask_tutor(package, question, topic_id=None)` service through an explicit form submit. Course context, result state, and displayed responses are scoped by course; failures are shown without an automatic retry.
- **PPTX:** Enabled `.pptx` upload through the existing `extract_document` entry point and display its returned slide sources. Text extraction only; slide notes and image OCR remain unsupported.
- **Save / Restore:** Still disabled. PostgreSQL persistence is not present in this baseline. Waiting for C/D to confirm the persistence scope, branch/commit to integrate, and demo-user identity semantics.
- **Validation:** On this branch, `PYTHONPATH=. pytest -q` — 267 passed (the earlier 275 included eight Anki page tests that are not on this branch), with five upstream SWIG deprecation warnings. Tutor success/failure and per-course state use mocked service responses; the Tutor `package` argument is a `model_dump()` dict. A browser smoke without `GEMINI_API_KEY` showed the service message `请配置 GEMINI_API_KEY`. A real browser upload of a locally generated text-only PPTX (title, body, table) → Extract text showed the text, table, and Slide 1 / Slide 2 sources; a corrupt PPTX showed the failure message and removing the file cleared the old result. No real Gemini, AI generation, or database request was made.
- **Not integrated here:** Database persistence is intentionally excluded pending independent approval of candidate `17aaf9f44988feee06cd3970c0463319b0530e78`; the older `575df8e` must not be integrated on its own. Agreed later contract: save/restore the full `StudyPackage`, `ExamSession`, and `AttemptResult`; recompute TopicStats/Mastery after restore; results are objects with `success`/`message`, not `ok` dicts; `load_course_history` returns package, sessions, attempts, topic_stats, and mastery_statuses; `demo_user_id` is a stable demo partition label, not authentication; real TigerData is unverified.

- **Owner:** A — UI
- **Branch:** `feature/ui`
- **Commit:** `50e8322` (`feat(ui): polish study workflow pages`)
- **Completed:** Refined the Study Plan, Practice, Progress, and Knowledge Map presentation while retaining existing course, scope, grading, and mastery flows.
- **Files changed:**
  - `components/knowledge_graph.py`
  - `pages/1_Study_Hub.py`
  - `pages/2_Practice_Center.py`
  - `pages/3_Performance.py`
  - `pages/4_Knowledge_Graph.py`
  - `services/ui_style.py`
  - `tests/test_knowledge_graph.py`
- **How to test:** `PYTHONPATH=. .venv/bin/pytest -q`
- **Result:** 176 tests passed. The test run reports five upstream SWIG deprecation warnings.
- **Known issues:** No known UI regressions. Visual behavior may vary with viewport size and Streamlit version.
- **Needs integration:** Yes. Please review the updated pages and confirm the presentation before merging into the integration branch.

## Frontend follow-up

- **Document parsing:** The dashboard uses B's unified `extract_document(file_bytes, filename)` implementation. The current uploader accepts UTF-8 TXT, text-based PDF, and text-based PPTX; it lists returned `sources` and displays PDF pages or PPTX slides. Failed extraction messages remain visible and invalidate the previous result; changing or removing a file also invalidates it. Gemini was not called during UI validation.
- **Earlier pending UI state:** At the time of the initial validation, Tutor sending, Anki download, and database actions were disabled. The current follow-up above supersedes the Tutor and PPTX portions; Anki and Save / Restore remain pending.
- **Practice:** The existing hidden-after-start settings, grading display, explanation grouping, and page styling are covered by the Practice UI regression tests.
- **Validation:** `PYTHONPATH=. .venv/bin/pytest -q` — 189 passed (five upstream SWIG deprecation warnings). Browser-checked real TXT upload/extraction, source and length display, clearing after removal, and all three pending sections and disabled controls. Local AppTest fixtures cover PDF extraction, failures, file replacement/removal, and per-course Tutor state. No Gemini request was made.
