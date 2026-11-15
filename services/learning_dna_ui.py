"""Render evidence dimensions alongside the existing Progress statistics."""

from services.i18n import tr
import streamlit as st

from components.progress_charts import dna_rows, render_bar_chart
from services.learning_dna import DIMENSIONS, comparison, evidence_profile


def render_learning_dna(course, attempts, sessions, questions, mode, *, example=False):
    """Two labelled bars per topic, shown without a click.

    With ``example`` the numbers are sample data: the heading says so and the
    per-question evidence tables are left out.
    """
    title = f"{tr('Example')} · {tr('Learning DNA')}" if example else tr("Learning DNA")
    st.subheader(title)
    st.caption(tr("See computation and conceptual understanding separately, with the answers behind each pattern."))
    st.caption(tr("How to read this profile") + " · " + tr("These are question-based observations, not a validated cognitive diagnosis. Multiple-choice answers do not demonstrate that you can explain an idea in your own words."))
    try:
        profile, _excluded = evidence_profile(attempts, sessions, questions, mode)
    except ValueError:
        st.warning(tr("Learning DNA couldn't read this practice history."))
        return
    st.caption(tr("Uses your latest answer to each question. Fewer than 3 different questions shows as insufficient evidence."))
    by_key = {(p.topic_id, p.dimension): p for p in profile}
    insights = course.learning_state.get("practice_insights", {})
    for topic in course.topics:
        pair = {dimension: by_key.get((topic.id, dimension)) for dimension in DIMENSIONS}
        with st.container(border=True, key=f"learning_dna_{topic.id}"):
            render_bar_chart(title, dna_rows(pair, tr), kind="dna", heading=topic.name)
            if all(pair.values()):
                st.write(tr(comparison(*pair.values())))
            else:
                st.write(tr("Answer more different questions in both dimensions before comparing them."))
            if example:
                continue
            evidence = []
            for item in pair.values():
                for row in item.evidence if item else []:
                    saved = insights.get(row['session_id'], {}).get(row['question_id'], {})
                    hints = saved.get("hints_used")
                    evidence.append({
                        tr("Dimension"): tr(DIMENSIONS[item.dimension]), tr("Question"): row['question'],
                        tr("Latest answer"): tr("Correct") if row['correct'] else tr("Incorrect"),
                        # A saved "not recorded" (None) reads the same as a missing entry.
                        tr("In-app hints shown"): tr("Not recorded") if hints is None else hints,
                        tr("Confidence"): tr({"sure": "Sure", "unsure": "Unsure", "guessed": "Guessed"}.get(saved.get("confidence"), "Not recorded")),
                    })
            if evidence:
                with st.expander(tr("View evidence") + f": {topic.name}"):
                    st.dataframe(evidence, hide_index=True, width="stretch")
