"""Learning Radar: where students of the built-in demo courses get stuck."""

from services.i18n import tr

import streamlit as st

from components.knowledge_graph import load_course_radar, render_radar_panel
from components.radar_chart import render_course_radar_chart, render_stuck_buttons
from services import learning_radar
from services.auth_session import current_user
from services.ui_style import apply_app_styles

# Up to this many topics are offered as one-click pills; more use a dropdown.
MAX_PILL_TOPICS = 8

apply_app_styles()

st.title(tr("Learning Radar"))
st.caption(tr("See where students get stuck, and mark the topics that stop you."))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

if not learning_radar.radar_enabled(course.course_id):
    st.info(tr("Learning Radar is available for the built-in demo courses."))
    st.stop()

user = current_user(st.session_state)
user_id = user.user_id if user is not None else None
# Shared with the Knowledge Map and Study Plan, so reruns reuse one read.
radar, _ = load_course_radar(st.session_state, course.course_id, user_id)
topic_names = {topic.id: topic.name for topic in course.topics}

picker_key = f"learning_radar_topic_{course.course_id}"
# The picker sits below the chart; its last choice is highlighted above.
picked = st.session_state.get(picker_key)
if picked not in topic_names:
    picked = None

chart_column, ranking_column = st.columns([1.15, 1], gap="large")
with chart_column:
    with st.container(border=True, key="learning_radar_chart_panel"):
        render_course_radar_chart(
            course,
            radar,
            focus_topic_id=picked,
            limit=8,
            key="learning_radar_page_chart",
        )
with ranking_column:
    with st.container(border=True, key="learning_radar_ranking_panel"):
        render_radar_panel(
            radar,
            learning_radar.top_hard_topics(radar, limit=len(course.topics)),
            topic_names,
            title="**Most flagged topics**",
        )

with st.container(border=True, key="learning_radar_mark_panel"):
    st.subheader(tr("Where are you stuck?"))
    if len(topic_names) <= MAX_PILL_TOPICS:
        picked = st.pills(
            tr("Pick a topic"),
            options=list(topic_names),
            format_func=lambda topic_id: topic_names[topic_id],
            key=picker_key,
            label_visibility="collapsed",
        )
    else:
        picked = st.selectbox(
            tr("Pick a topic"),
            options=list(topic_names),
            index=None,
            format_func=lambda topic_id: topic_names[topic_id],
            placeholder=tr("Pick a topic"),
            key=picker_key,
            label_visibility="collapsed",
        )

    if picked is None:
        st.caption(tr("Pick a topic above to mark it."))
    else:
        render_stuck_buttons(
            st.session_state,
            course.course_id,
            picked,
            user_id,
            key=f"learning_radar_stuck_{course.course_id}_{picked}",
        )
        if st.button(
            tr("Open this topic in Knowledge Map"),
            key=f"learning_radar_map_{course.course_id}_{picked}",
            icon=":material/hub:",
        ):
            # The Knowledge Map moves this into its topic picker on load.
            st.session_state[f"graph_pending_focus_{course.course_id}"] = picked
            st.switch_page("pages/4_Knowledge_Graph.py")
