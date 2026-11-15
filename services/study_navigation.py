"""Shared course context and a non-destructive return to unfinished practice."""
import streamlit as st
from services.i18n import tr
from services.practice_pages_ui import drop_pending_requests

STUDY_PATHS = {'Study_Hub', 'Performance', 'Knowledge_Graph', 'Learning_Radar', 'Concept_Lab', 'Export_Anki', 'Flashcards'}


def render_study_context(course, page_path, title):
    with st.container(key='flight_course_context', horizontal=True,
                      horizontal_alignment='distribute', vertical_alignment='center'):
        st.caption(f'{course.course_name}  /  {title}')
        active = st.session_state.get(f'active_practice_{course.course_id}')
        if page_path not in STUDY_PATHS or not active or 'result' in active:
            return
        questions = active.get('questions', [])
        if not questions:
            return
        number = max(1, min(active.get('worksheet_index', 0)+1, len(questions)))
        with st.container(key='study_return_action', width='content'):
            if st.button(tr('Return to practice') + f' · {number}/{len(questions)}',
                         icon=':material/arrow_forward:', key=f'study_return_{course.course_id}'):
                drop_pending_requests(st.session_state, course.course_id)
                st.switch_page('pages/2_Practice_Center.py')
