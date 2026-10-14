# Question quality and mistake review

Branch: feature/question-quality-review, based on committed knowledge-map work 0622aa7.

Generation keeps existing quantity, schema, confirmed-topic and citation checks. It now also rejects repeated question stems and normalized duplicate options (Unicode, case and whitespace). Mathematical operators are preserved. Changed reuse of an existing question ID and repeated stems from the current bank are also rejected before applying generated content. These checks do not prove factual correctness, equivalence of differently worded questions, or semantic agreement between answers and explanations; generated questions still require human review.

After grading, Review missed questions includes incorrect and unanswered questions and supports a topic filter. Starting review creates a fresh session ID with blank answers, preserving the previous score and question snapshot. Review answers count as further practice evidence in the selected mode, not an independent assessment of mastery.

Cited page numbers appear with feedback. Source material shows only real extracted text retained in the current session. Missing pages or documents are reported honestly; no evidence is invented. Uploaded documents are not newly persisted by this change, so source excerpts may be unavailable after login restore.

Review: submit one wrong or unanswered response, start a mistake review, check blank answers and an unchanged original result, then submit again and verify the session count increases by one.

No database schema migration or GitHub synchronization is performed.
