# UI Handoff Summary

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

- **Document parsing:** The dashboard uses B's `extract_document(file_bytes, filename)` implementation from commit `74d541b`. It accepts TXT and text-based PDF, presents the 5 MiB / 50,000-character limits, lists the returned `sources`, and shows the PDF page count and per-page text lengths. Failed extraction messages remain visible and invalidate the previous result; changing or removing a file also invalidates it. Gemini was not called during UI validation.
- **Pending UI:** Study Plan now contains independent Tutor, Anki, and Save / Restore sections. Tutor sending, Anki download, and database actions are disabled; no answer, card file, save, or restore operation is simulated. Tutor input uses a course-specific session-state key. Status copy and that key helper live in `services/ui_adapters.py`; no backend protocol or dependency is introduced.
- **Practice:** The existing hidden-after-start settings, grading display, explanation grouping, and page styling are covered by the Practice UI regression tests.
- **Validation:** `PYTHONPATH=. .venv/bin/pytest -q` — 189 passed (five upstream SWIG deprecation warnings). Browser-checked real TXT upload/extraction, source and length display, clearing after removal, and all three pending sections and disabled controls. Local AppTest fixtures cover PDF extraction, failures, file replacement/removal, and per-course Tutor state. No Gemini request was made.
