# Floating AI Tutor

Branch: `feature/floating-ai-tutor`, based on UI-4 `c8d03dac06629efa14f11da1839c457c4836478a`.

The floating Tutor is mounted by `app.py` before the selected page runs. It is available on Dashboard, Study Plan, Practice, Progress, Knowledge Map and Anki, including pages without a selected course. Open a course before asking a question.

## Interaction

- Drag the robot button with a mouse or touch. Clicking it opens the question panel. Dragging does not send a request.
- Use the focused robot button's arrow keys to move it; Shift moves it farther. Enter or Space opens it. Escape closes the panel.
- Type a question and send it. Each question uses the current course's summaries and relationships through the existing `services.gemini_service.ask_tutor()` function.
- Recent question/answer records are separate for each course. They are kept in the Streamlit session only. Each question is an independent Tutor request; earlier chat messages are not sent as conversation context.
- Clearing removes this course's local conversation. Closing the panel preserves its conversation.
- Position and draft survive page reruns in browser memory. Questions and answers are not stored in browser localStorage or sessionStorage.

## Runtime configuration

Install the existing pinned `requirements.txt` dependencies; no new frontend build or dependency is required. This component uses Streamlit 1.55's components v2 API.

The existing Gemini service reads `GEMINI_API_KEY` from the server process environment. `GEMINI_MODEL` is optional; its existing default is `gemini-3.8-flash`. Configure credentials locally before starting Streamlit. This branch does not add a `.env` loader. Do not send credentials to collaborators or enter them in the Tutor chat.

Example for zsh, entering the key privately in your own terminal:

```sh
read -s 'GEMINI_API_KEY?Gemini API key: '
export GEMINI_API_KEY
streamlit run app.py --server.port 8505
```

Restart the server after changing its environment. Missing configuration, service errors, empty answers and failed requests produce explicit unavailable/error feedback, without an invented answer.

## Code and integration boundaries

- `assets/tutor_assistant.{html,css,js}`: isolated floating UI, pointer/keyboard controls, viewport bounds and submission events.
- `services/tutor_assistant_ui.py`: components v2 registration and server callbacks.
- `services/tutor_assistant_state.py`: authoritative current-course validation, bounded local histories, request deduplication and safe error mapping.
- `tests/test_tutor_assistant_state.py`: controller validation, request handling and course isolation.
- `tests/test_floating_tutor_course_creation.py`: successful topic generation immediately refreshes the global Tutor to the new course.

Dashboard topic generation now reruns after saving the new course, keeping its success notice for that rerun. This refreshes the sidebar and Tutor's selected course together.

Only a submitted question calls Gemini. Opening, closing, dragging, resizing, page navigation and clearing history do not call it. Client events never supply a course package or credentials; the callback reads the selected course from the server session. Text is rendered without interpreting HTML.

This branch does not integrate Auth PR #21 or PostgreSQL PR #20, persist Tutor history to a database, or merge changes into main/UI-4. Future Auth integration must clear the existing Streamlit session on logout, including Tutor state, before another account uses it.

## Validation

Local interaction checks and mock response tests are distinct from a live Gemini response test. At implementation start, this machine had no `GEMINI_API_KEY` in the current process and no project `.env`. Live AI answers therefore remain pending local configuration and a real service test.

Final automated regression: **336 passed, 5 existing SWIG deprecation warnings, 0 failed**. This includes 41 controller tests and the new-course integration regression. The test fixture supplies Streamlit's real components v2 manager because Streamlit 1.55 AppTest's mock runtime omits that registry; it does not hide or replace the floating component.

Browser acceptance evidence is kept separately in `/tmp/exampilot-ai-tutor-acceptance/artifacts/`. The normal preview is `http://127.0.0.1:8505`; successful-response fixtures run only in a separate temporary test process, never in the normal app.

- Actual app: **12/12 passed** in Chromium on macOS, covering drag/click, keyboard controls, missing-configuration feedback, inert question text, three Demo courses, page navigation, course separation, clearing, an independent browser session, mobile layout, a short keyboard-style viewport and touch drag followed by a tap.
- Separate synthetic-service browser tests: **8/8 passed**, covering visible replies, waiting and minimizing, double-click request deduplication, multiline input, safe answer text, per-course history, failure/retry, and course navigation during a delayed reply. Exactly five intended test requests were recorded; drag/open/close/navigation/resize/clear made no extra requests. These fixtures are not live AI responses.
- Independent frontend checks: **15/15 passed**, including repeated v2 renderer lifecycle calls and touch/keyboard activation after a drag.

The browser checks use desktop and simulated mobile/keyboard viewports in Chromium; they do not claim physical iPhone/Safari acceptance. A live Gemini response remains unverified because the local runtime configuration is absent. No database test or schema change is part of this feature.
