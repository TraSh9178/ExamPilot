"""Dedicated teaching page, preserving the map's selected topic on return."""
import streamlit as st
from components.page_links import back_button
from components.topic_explanation import render_topic_explanation
from services.i18n import tr
from services.ui_style import apply_app_styles

apply_app_styles()
course = st.session_state.get("current_course")
back_button(tr("Back to Knowledge Map"), "pages/4_Knowledge_Graph.py", key="topic_details_back")
st.title(tr("Detailed explanation & examples"))
if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.stop()
topic_id = st.session_state.get(f"topic_details_{course.course_id}")
topic = next((item for item in course.topics if item.id == topic_id), None)
if topic is None:
    st.info(tr("Click a knowledge point to see its details."))
    st.stop()
st.session_state[f"graph_pending_focus_{course.course_id}"] = topic.id
with st.container(border=True, key="topic_detail_overview"):
    st.subheader(topic.name)
    from services.math_text import write_summary
    write_summary(topic.summary)
with st.container(border=True, key="topic_detail_lesson"):
    render_topic_explanation(course, topic.id)
