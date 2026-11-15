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

Follow-up section review: topic details now open a dedicated teaching page with offline course examples and optional AI explanation; the map focus survives the return. Learning DNA cards use a paper surface, a top rule and wider gutters. Concept Lab prediction choices have a bordered panel, followed by a separated primary action. Learning Radar uses a 2:1 chart/picker layout and a keyboard-focusable ranking region below; five 8rem rows fit its 40rem viewport. Counts, privacy thresholds and sample-data labelling are unchanged. Desktop and 375px browser checks confirmed the layout, five-row geometry and no horizontal overflow.

Full Python 3.12 suite after integrating main: 1560 passed, 20 skipped. Browser walkthroughs cover desktop, 375px portrait and 812px landscape, including pause/return, retained answers, retained Pilot draft, mobile navigation, panel bounds and focused controls. Reduced-motion rules were inspected in source; OS preference switching was not emulated. No live AI request or production account data was used.
