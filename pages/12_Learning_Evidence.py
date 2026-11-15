"""Answers behind Learning DNA: the evidence tables, on a page of their own.

Opened from a topic's "View answers" button on Progress. Real practice only:
the example report on the demo courses has no answers to show.
"""
import streamlit as st

from components.page_links import back_button
from services.i18n import tr
from services.learning_dna_ui import evidence_tables, evidence_topic_key
from services.ui_style import apply_app_styles

apply_app_styles()

course = st.session_state.get("current_course")

# Progress uses the same mode key, so the way back keeps the mode chosen here.
back_button(
    tr("Back to Progress"), "pages/3_Performance.py", key="learning_evidence_back",
    keep=(f"performance_mode_{course.course_id}",) if course is not None else (),
)
st.title(tr("Answers behind Learning DNA"))

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

st.caption(tr("Your latest answer to each question behind your Learning DNA, topic by topic."))

# The same widget key as on Progress, so the chosen mode carries over: the
# "View answers" button keeps that key's value for this page as it switches.
mode_label = st.radio(
    tr("Performance mode"),
    options=[tr("Mock Exam"), tr("Topic Practice")],
    key=f"performance_mode_{course.course_id}",
    horizontal=True,
    width="stretch",
)
mode = "mock" if mode_label == tr("Mock Exam") else "topic"

history = st.session_state.get(f"practice_history_{course.course_id}", {})
try:
    tables = evidence_tables(course, history, mode)
except ValueError:
    st.warning(tr("Learning DNA couldn't read this practice history."))
    st.stop()

if not tables:
    st.info(tr("No answers behind Learning DNA in this mode yet."))
    st.stop()

# The topic whose button was clicked comes first; the rest keep the course order.
requested = st.session_state.get(evidence_topic_key(course.course_id))
tables.sort(key=lambda pair: pair[0].id != requested)

for topic, rows in tables:
    with st.container(key=f"learning_evidence_{topic.id}"):
        st.subheader(topic.name)
        st.dataframe(rows, hide_index=True, width="stretch")
