# Floating AI Tutor

Compatibility branch: `fix/floating-ai-tutor-auth`, based on the Auth + PostgreSQL reference `ef78a47d8906648d11b9f933129f87a848bc1437`.

Only the Tutor commit `850434a50c01b64cec213f323fb987b77160a4b0` was ported from `feature/floating-ai-tutor`; its UI-4 parent was not imported. The original delivery branch remains unchanged. This branch is a separate compatibility review candidate, not the team's final Save/Restore integration baseline.

The floating Tutor is mounted by `app.py` after the authentication guard and before the selected page runs. It is available to signed-in users on Dashboard, Study Plan, Practice, Progress, Knowledge Map and Anki, including pages without a selected course. Open a course before asking a question. The signed-out page runs a separate, JavaScript-only cleanup component without mounting the Tutor.

## Interaction

- Drag the robot button with a mouse or touch. Clicking it opens the question panel. Dragging does not send a request.
- Use the focused robot button's arrow keys to move it; Shift moves it farther. Enter or Space opens it. Escape closes the panel even when focus is on the underlying page.
- Type a question and send it. Each question uses the current course's summaries and relationships through the existing `services.gemini_service.ask_tutor()` function.
- Recent question/answer records are separate for each authenticated account and course. They are kept in the Streamlit session only. Each question is an independent Tutor request; earlier chat messages are not sent as conversation context.
- Clearing removes this course's local conversation. Closing the panel preserves its conversation.
- Position and draft survive page reruns in browser memory. Logout or session expiry clears the browser draft and server-side chat. Questions and answers are not stored in browser localStorage or sessionStorage.
- On narrow screens the default launcher position is near the upper right, below the header. Mobile pages also reserve bottom space so the default launcher does not cover Dashboard's Delete course button. Users can still drag it freely.

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
- `services/tutor_assistant_ui.py`: components v2 registration, authentication checks in rendering and callbacks, and a separate browser cleanup component.
- `services/tutor_assistant_state.py`: authoritative account and current-course validation, bounded local histories, request deduplication and safe error mapping.
- `tests/test_tutor_assistant_state.py`: controller validation, request handling and course isolation.
- `tests/test_floating_tutor_course_creation.py`: successful topic generation immediately refreshes the global Tutor to the new course.
- `tests/test_tutor_account_scope.py`: trusted account ownership, stale-event rejection, logout, delayed responses and same-account course replacement.
- `tests/test_tutor_auth_integration.py`: the real app authentication guard, expiry, logout and a second account opening the same Demo, using synthetic account fixtures.

Dashboard topic generation now reruns after saving the new course, keeping its success notice for that rerun. This refreshes the sidebar and Tutor's selected course together.

Only a submitted question calls Gemini. Opening, closing, dragging, resizing, page navigation and clearing history do not call it. Client events never supply a course package, account identity or credentials. The callback obtains the account from `current_user()` and the selected course from the server session. Both submit and clear events must match the server's assistant session UUID, so an old account's queued event cannot alter the next account's chat. Text is rendered without interpreting HTML.

The Auth core, PostgreSQL layer, SQL and existing `ask_tutor()` interface are unchanged. This branch adds no course-list API, Save/Restore UI wiring or AI conversation persistence. Replacing a course object with the same course ID for the same signed-in account preserves that session's existing chat; it does not restore AI history from a database or another device.

The reviewed main snapshot `3850c94a2c2cacf2b1054fb822be4a51b2c25285` does not yet include the Auth guard. This compatibility branch inherits Auth from the reference baseline; a clean merge simulation does not approve or replace Auth PR #21's separate integration review.

## Validation

Local interaction checks and synthetic Auth/Tutor fixtures are distinct from real TigerData registration/login and live Gemini response tests. Browser success replies run only in a separate temporary test process and are explicitly marked as mock results. The normal app contains no replacement Auth or Gemini implementation.

The AppTest fixture supplies Streamlit's real components v2 manager because Streamlit 1.55 AppTest's mock runtime omits that registry; it does not hide or replace the floating component. Browser evidence for this compatibility branch is kept separately in `/tmp/exampilot-ai-tutor-auth-acceptance/artifacts/`.

Automated regression: **473 passed, 5 existing SWIG deprecation warnings, 0 failed**. The 67 focused Tutor tests include 41 existing controller tests, 21 account-scope/cleanup tests, four app Auth integration tests and one new-course regression. Independent frontend checks: **18/18 passed**.

Browser acceptance: **15/15 passed** in Chromium on macOS. Three checks use the actual app without database/Gemini configuration: no assistant before login, protected URLs behind Auth, and explicit Auth-unavailable feedback. Twelve checks use isolated synthetic Auth/Tutor services: login/register, marked mock replies, same-account course-object replacement, Esc with page focus, logout browser cleanup, account B opening account A's Demo, account A logging in again, course separation, six-page navigation, dragging/clearing, 390×844 Delete course accessibility and an empty Practice page using `st.stop()`. An independent mobile/Esc browser check also passed **2/2**, with native Delete-button hit tests.

Test services and the course-object replacement helper live only under `/tmp`, outside the repository. No real database registration/login, database Save/Restore or live Gemini call was performed. The normal compatibility preview uses `http://127.0.0.1:8507`; the synthetic preview is stopped after acceptance.

Real TigerData account switching and live Gemini responses remain unverified. Simulated mobile Chromium checks do not claim physical iPhone/Safari acceptance. The original branch's 336-passed test report belongs to commit `850434a`, not this compatibility branch.
