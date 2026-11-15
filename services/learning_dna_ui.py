"""Render evidence dimensions alongside the existing Progress statistics."""

from services.i18n import tr
import streamlit as st

from services.learning_dna import DIMENSIONS, comparison, evidence_profile


def render_learning_dna(course, attempts, sessions, questions, mode):
    st.subheader(tr("Learning DNA"))
    st.caption(tr("See computation and conceptual understanding separately, with the answers behind each pattern."))
    with st.expander(tr("How to read this profile")):
        st.caption(tr("These are question-based observations, not a validated cognitive diagnosis. Multiple-choice answers do not demonstrate that you can explain an idea in your own words."))
    try:
        profile, _excluded = evidence_profile(attempts, sessions, questions, mode)
    except ValueError:
        st.warning(tr("Learning DNA couldn't read this practice history."))
        return
    st.caption(tr("Uses your latest answer to each question. Fewer than 3 different questions shows as insufficient evidence."))
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    for topic in course.topics:
        with st.container(border=True, key=f"learning_dna_{topic.id}"):
            st.markdown(f"**{topic.name}**")
            pair = []
            for column, (dimension, label) in zip(st.columns(2), DIMENSIONS.items()):
                item = by_key.get((topic.id, dimension))
                with column:
                    st.metric(tr(label), "—" if item is None or item.accuracy is None else f"{item.accuracy:.0f}%")
                    st.caption(tr(f"{item.count if item else 0} different questions · {tr(item.status if item else 'Insufficient evidence')}"))
                pair.append(item)
            if all(pair):
                st.write(tr(comparison(*pair)))
            else:
                st.write(tr("Answer more different questions in both dimensions before comparing them."))
            evidence = [
                {tr("Dimension"): tr(DIMENSIONS[item.dimension]), tr("Question"): row['question'],
                 tr("Latest answer"): tr("Correct") if row['correct'] else tr("Incorrect"),
                 tr("In-app hints shown"): course.learning_state.get("practice_insights", {}).get(row['session_id'], {}).get(row['question_id'], {}).get("hints_used", tr("Not recorded")),
                 tr("Confidence"): tr({"sure": "Sure", "unsure": "Unsure", "guessed": "Guessed"}.get(course.learning_state.get("practice_insights", {}).get(row['session_id'], {}).get(row['question_id'], {}).get("confidence"), "Not recorded"))}
                for item in pair if item for row in item.evidence
            ]
            if evidence:
                with st.expander(tr("View evidence") + f": {topic.name}"):
                    st.dataframe(evidence, hide_index=True, width="stretch")
