# Shared UI typography

`assets/ui_typography.css` owns the text-size variables. Both the Streamlit
application and the isolated Pilot component load this file. Change the shared
tokens instead of adding a page-specific font size.

| Role | Desktop | Tablet, 481–768px | Phone, up to 480px |
| --- | --- | --- | --- |
| Page title / Dashboard hero | 48px | 48px | 36px |
| Section title / current course / course card title | 32px | 32px | 28px |
| Topic title | 28px | 26px | 26px |
| Practice question / explanation title | 24.8px | 24.8px | 24px |
| Anki question title | 24px | 24px | 24px |
| Body / button / form label and input | 16px | 16px | 16px |
| Caption / supporting text | 14px | 14px | 14px |
| Metric value | 44px | 44px | 40px |
| Compact Pilot panel title | 20px | 20px | 20px |

Sizes use rem units so browser text-size preferences still apply. Material
icons, avatar initials, the sidebar wordmark and graph zoom scaling are visual
elements with their own sizing. Long headings wrap rather than shrink.

Course headings have dedicated container keys in Study Plan, Practice,
Progress, Knowledge Map and Anki. Questions use separate tokens to preserve
their original size before the heading enlargement. Practice question and
explanation titles keep their original 680 weight and 1.4 line height; Anki
question titles keep 600 weight and 1.2 line height. Explanation body text
remains 16px. Practice's other metadata stays at body size. The login layout stacks
on narrow screens to leave room for the larger headings and form controls.
Practice's course value spans the full row on small screens. Metric cards
wrap when space is tight so full scores and percentages remain visible.

Pilot keeps its original robot artwork and 64px launcher hit area, with a
48px image and 16px label box. Supporting text inside the panel now uses the
same 14px minimum as page captions.

Validation uses the isolated local preview with synthetic accounts, without
database or Gemini calls. It does not establish real Auth, Gemini responses,
cloud Save/Restore or compatibility with the final main branch.

After restoring the question styles, targeted Chromium checks passed 12/12
at widths 1440, 768, 390 and 320px: Practice questions, submitted results
and explanations, and Anki questions/answers. Computed sizes, font weights,
line heights, explanation body text and text bounds were checked, together
with preserved page, course and topic headings. Full pytest was not repeated
for this CSS-only correction; the full-suite result below is earlier evidence.

Before the question-size restoration, typography and layout checks on
`bf4ec71d6c3abf5d491c4c8e4c4c3801071853b7` passed 36/36 in Chromium at viewport widths
1440, 768, 390 and 320px, including answering and submitting a Demo practice,
results and Progress, all main pages, account and login layouts, and the Pilot
panel. A separate rendered-text audit found no meaningful text below 14px
on Dashboard, Anki, account, login and registration; Anki options and avatar
upload text use 16px. Complete pytest: 498 passed, with five existing upstream
SWIG deprecation warnings.
