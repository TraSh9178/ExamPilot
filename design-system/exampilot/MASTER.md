# ExamPilot — shared study interface

Stack: Streamlit 1.55, Python, Altair, existing custom browser components. Keep the focused-page structure and current paper stationery identity. Do not introduce a new frontend framework or font/network dependency.

## Heuristic review

| Severity | Location | Finding | Change |
| --- | --- | --- | --- |
| 3 | Cross-page learning | An unfinished question lacks a consistent return action outside Practice. | Course context offers return to the same session/question on primary learning pages. |
| 2 | Pause | The small timer/button alone does not explain the paused state or reassure about answers. | Inline status beneath progress; paused clock gets a distinct border. No reset or hidden answers. |
| 3 | Mobile navigation | Fixed avatar can overlap the sidebar collapse control. | Hide competing floating controls while the mobile navigation is open; keep 44px navigation targets. |
| 2 | Pilot | Bright blue robot, gradients and chat surfaces differ from the paper app and plane identity. | Shared stationery palette, same plane asset, consistent 44px controls and focus treatment. |
| 2 | Practice progress | Platform emoji plane differs from sidebar branding. | Use the existing vector brand plane. |

Review scope: Home → Study Plan → Practice → Progress/Map/Lab/Flashcards, focused return pages, and floating Pilot. Review is one expert pass, not a claim of user-study validation.

## Tokens

`assets/ui_tokens.css` is the shared token entry point, loaded by both the app stylesheet and Pilot's isolated shadow root. Primitive cream/navy/slate/blue values feed semantic surface/text/action/border roles and component aliases. Existing page tokens remain supported. Use 4/8px spacing, 44px minimum controls, 10px control and 16px panel radii, restrained motion and visible focus.

Preserve functional colors in graphs and scoring; color must not be the only signal. White text on the primary action and muted text on paper must meet 4.5:1. Borders of form controls need 3:1. Reduced-motion disables decorative movement. Mobile actions wrap rather than push content horizontally.

## Source fit and evidence

UI/UX Pro Max searches: `education learning dashboard` suggested a child-oriented clay style; the single retry `university analytics dashboard` suggested enterprise marketing structure. Neither is accepted as a product-level template. Visual direction therefore uses the existing paper identity plus the skill's general accessibility/interaction defaults. Verified focused UX matches: predictable back navigation, fixed navigation offsets, and focus-not-obscured guidance. No Streamlit-specific database guidance was available; implementation follows this repository's existing components.

Design Token provides primitive → semantic → component architecture. Heuristic Evaluation provides task walkthroughs and severity prioritization. The changes apply to all users; grades, drafts and personal conversations remain account-scoped.

## Verification

## Content and motion refinement

The next heuristic pass prioritizes an uninterrupted demo (severity 3), explicit example selection (3), oversized chart labels (2), competing Lab actions (2), and redundant persistent explanations (2). All 15 Calculus topics now have offline bilingual reasoning steps, a worked example and a common mistake. Other demo topics retain their own course examples and explanation. No sample history is written into personal results.

Optional instructions use a small question-mark tooltip with a native focus target and associated tooltip text. Hover/focus reveals it; leaving the target or focusing elsewhere hides it. Counts, errors, selected-course context and sample-data attribution remain visible. Topic examples start unselected, hide their picker after choosing, and offer Change example beneath the familiar question card.

Practice progress follows a winding dotted route using the shared SVG plane. A single central loading layer replaces the header flight, with a blurred backdrop, operation text and a parked-plane reduced-motion fallback. The transparent practice margin fades while retaining its grid space, so the question and fixed landscape do not stretch or jump. Lab practice appears after self-assessment, before a left/right Back/Start again row. Home orders My courses, totals, course cards, Create course; Learning DNA remains available through Progress.

Validation for this pass: 1574 passed, 20 skipped on Python 3.12. Browser checks covered example selection, offline teaching, self-check gating, tooltip focus/show/hide, 375px portrait and 812px landscape bounds, and both login/study loading states with a controlled local delay. Practice panel measurements before/after hiding were identical (x, y, width and background position). No real account database or AI calls were made. The app keeps its light paper theme; OS reduced-motion switching and system text enlargement were not emulated. Reduced-motion rules were reviewed in source.

Skill search fit: the focused loading-feedback/reduced-motion results matched this work. The progressive-disclosure search was too broad; disclosure decisions use the user's explicit instructions and the general recognition/minimalism heuristics rather than an unrelated result.

Follow-up section review: topic details now open a dedicated teaching page with offline course examples and optional AI explanation; the map focus survives the return. Learning DNA cards use a paper surface, a top rule and wider gutters. Concept Lab prediction choices have a bordered panel, followed by a separated primary action. Learning Radar uses a 2:1 chart/picker layout and a keyboard-focusable ranking region below; five 8rem rows fit its 40rem viewport. Counts, privacy thresholds and sample-data labelling are unchanged. Desktop and 375px browser checks confirmed the layout, five-row geometry and no horizontal overflow.

Full Python 3.12 suite after integrating main: 1560 passed, 20 skipped. Browser walkthroughs cover desktop, 375px portrait and 812px landscape, including pause/return, retained answers, retained Pilot draft, mobile navigation, panel bounds and focused controls. Reduced-motion rules were inspected in source; OS preference switching was not emulated. No live AI request or production account data was used.

## Result review and Home consistency

Home uses the shared slate primary and cream secondary pills, semantic type/color tokens and 44px minimum controls. Remove the old oversized Create course treatment rather than maintaining a second button system. Results group stacked score/accuracy at left, a larger primary Review answers action in the middle, and next-topic actions at right; narrow screens stack these groups. Reflection and explanation actions align to the right. Optional functional instructions use the existing hover/focus help control; feedback, errors, learning content and sample-data attribution remain visible.

The ranking uses five 120px cards plus four 8px gaps in a 632px scrolling region. Rank, topic, count and reason chips have distinct visual roles. The landscape belongs to the fixed app backdrop, with transparent desktop navigation and no duplicate sidebar mountain; mobile navigation retains an opaque surface for legibility. Summary and offline lesson notation uses native Streamlit LaTeX rendering via reviewed literal mappings, preserving saved content, existing math and code spans.

Reviewed 33 existing draft demo questions for publication: 27 calculus, 3 economics and 3 Python. This supplies a distinct same-topic practice structure for each currently available question in a one-question session. Availability still respects review status, confirmed scope, unused question families and distinct stems. Legacy copies receive approval metadata only when their built-in question content is unchanged; explicit learner rejections, edits and saved question payloads are preserved. Labels missing in old snapshots are resolved for matching only, without changing those snapshots.

Verification: Python 3.12 full suite 1580 passed, 20 skipped. Browser checks covered the result/review/transfer flow, right-aligned controls, tooltip keyboard disclosure, native mathematical fractions/limits in summaries and worked examples, five-card ranking geometry, Home button computed styles, fixed background before/after navigation collapse, and 375px/812px responsive bounds. All previews used synthetic local state without live AI or production database writes; these checks do not establish public deployment status. UI/UX Pro Max heading-scale guidance, Design Token shared roles and Heuristic Evaluation task grouping informed this pass.
