"""Topic summaries: every topic of the current course, in course order."""
from services.i18n import tr
import streamlit as st

from components.page_links import back_button
from services.ui_style import apply_app_styles

apply_app_styles()

back_button(tr("Back to Study Plan"), "pages/1_Study_Hub.py", key="topic_summaries_back")
st.title(tr("Topic summaries"))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard to start studying."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

if not course.topics:
    st.info(tr("This course has no topics yet."))

# One simple card per topic, in the order the course lists them.
for topic in course.topics:
    with st.container(border=True):
        st.markdown(f"**{topic.name}**")
        from services.math_text import write_summary
        write_summary(topic.summary)
        if topic.source_pages:
            st.caption(tr("Source pages: ") + ", ".join(map(str, topic.source_pages)))
