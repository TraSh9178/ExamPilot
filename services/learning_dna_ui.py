"""Render evidence dimensions alongside the existing Progress statistics."""
import streamlit as st

from services.learning_dna import DIMENSIONS, comparison, evidence_profile


def render_learning_dna(course, attempts, sessions, questions, mode):
    st.subheader("Learning DNA")
    st.caption("See computation and conceptual understanding separately, with the answers behind each pattern.")
    with st.expander("How to read this profile"):
        st.caption("These are question-based observations, not a validated cognitive diagnosis. Multiple-choice answers do not demonstrate that you can explain an idea in your own words.")
    try:
        profile, excluded = evidence_profile(attempts, sessions, questions, mode)
    except ValueError as error:
        st.warning(f"Learning DNA could not read this history: {error}")
        return
    st.caption("Each question family counts once, using its latest response in this mode. Fewer than 3 different questions means insufficient evidence. Untagged and unanswered responses are excluded.")
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    if excluded:
        st.caption(f"{excluded} latest question-family response(s) excluded because they are untagged or unanswered.")
    for topic in course.topics:
        with st.container(border=True, key=f"learning_dna_{topic.id}"):
            st.markdown(f"**{topic.name}**")
            pair = []
            for column, (dimension, label) in zip(st.columns(2), DIMENSIONS.items()):
                item = by_key.get((topic.id, dimension))
                with column:
                    st.metric(label, "—" if item is None or item.accuracy is None else f"{item.accuracy:.0f}%")
                    st.caption(f"{item.count if item else 0} different questions · {item.status if item else 'Insufficient evidence'}")
                pair.append(item)
            if all(pair):
                st.write(comparison(*pair))
            else:
                st.write("Answer more different questions in both dimensions before comparing them.")
            evidence = [
                {"Dimension": DIMENSIONS[item.dimension], "Question": row['question'],
                 "Latest answer": "Correct" if row['correct'] else "Incorrect",
                 "Question ID": row['question_id'], "Session": row['session_id'],
                 "In-app hints shown": course.learning_state.get("practice_insights", {}).get(row['session_id'], {}).get(row['question_id'], {}).get("hints_used", "Not recorded"),
                 "Confidence": course.learning_state.get("practice_insights", {}).get(row['session_id'], {}).get(row['question_id'], {}).get("confidence") or "Not recorded"}
                for item in pair if item for row in item.evidence
            ]
            if evidence:
                with st.expander(f"View evidence: {topic.name}"):
                    st.dataframe(evidence, hide_index=True, width="stretch")
    with st.expander("Question labels and saved history"):
        st.caption("Tag a question's evidence type under Study Plan → Review and edit questions. Saved questions and graded history restore with your course; editing a tag creates a new question version and preserves earlier evidence.")
