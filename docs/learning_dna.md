# Learning DNA

Dashboard now exposes a Learning DNA card. Open a course, select View Learning DNA, or visit Progress. The selected course's topics each show two dimensions: Computation and Conceptual understanding. The practice-mode selector separates mock exams from topic practice.

This is a descriptive evidence profile, not a validated cognitive model. A multiple-choice conceptual answer cannot establish whether a student can explain an idea independently. A procedural answer cannot establish broad mathematical or programming ability. Differences suggest what to practise next; they do not diagnose a learner.

## Evidence contract

Questions may have an optional `cognitive_dimension`: `computation`, `conceptual`, or null. The three demos include initial, editable labels; the existing 75 draft questions remain pending approval. Labels identify the demand of a question, not a student's traits. Computation includes procedural calculation and code tracing; conceptual questions ask about meaning, relationships or conditions. Mixed or uncertain items should remain untagged.

Study Plan → Review and edit questions → Learning DNA evidence type allows a reviewer to assign or correct a label. Saving a changed label uses the existing question-version mechanism. The label persists inside the course JSON using existing account storage; no database migration is required. Old payloads default to untagged. AI generation is not changed to infer labels automatically.

Each topic and practice mode uses the latest recorded response per question-version family. The session order stored with the course determines recency, with new local sessions appended. Repetition and revisions do not increase independent evidence. Historical snapshots keep the labels recorded when those questions were answered; changing a label does not retrospectively relabel earlier responses. A latest unanswered or untagged response contributes no dimension evidence and is reported as excluded.

Each dimension reports its distinct-family count, latest-answer accuracy and an evidence status. Below three different answered families it shows Insufficient evidence. With at least three, under 60% is Needs review, 60% to under 80% is Mixed answers, and 80% or above is Consistent answers. These are transparent product heuristics, not calibrated ability estimates or statistical confidence bounds. Comparison advice requires at least three families in both dimensions and uses a 20-percentage-point gap. The underlying questions, outcomes and session IDs are visible under View evidence.

## Verification and limitations

Tests cover unequal dimensions hidden by aggregate accuracy, recency independent of attempt order, question-version deduplication, mode and topic isolation, missing labels, unanswered responses, invalid history, saved chronology, JSON round trips, UI tagging, Dashboard navigation and Progress display. Existing mastery calculations and thresholds are unchanged.

Existing saved courses and old answers are not automatically retagged. Their profiles can show insufficient evidence until tagged questions are answered. Small samples, question difficulty and use of hints can affect observed results. Hint-assisted answers currently remain in topic-practice evidence; the profile does not claim independent or unaided assessment. In particular, no language-model analysis of written explanations or psychometric validation is implemented.

The baseline main branch had five accessibility test failures after combining its three-course wording fixtures with the expanded draft bank. Test fixtures now distinguish available original questions from pending drafts, retain the existing fallback contract, and stub navigation only in the standalone page test. Accessibility production behavior is unchanged.
