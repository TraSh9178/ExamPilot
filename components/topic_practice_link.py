"""Navigation from a selected topic to its practice setup."""

import streamlit as st

from services.i18n import tr
from services.learning_flow import stage_topic_practice


def open_topic_practice(course, topic_id):
    if stage_topic_practice(st.session_state, course, topic_id):
        st.switch_page("pages/2_Practice_Center.py")
    else:
        st.info(tr("There are no approved practice questions for this topic yet."))
