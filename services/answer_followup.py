"""Question-scoped follow-up, asked only after a student submits the form."""
import hashlib
from services.ui_help import help_heading

import streamlit as st

from models.schemas import Question, StudyPackage
from services.ai_service import MAX_TUTOR_QUESTION_CHARS, ask_tutor
from services.i18n import LANGUAGE_KEY, tr


def render_answer_followup(course: StudyPackage, question: Question) -> None:
    scope = hashlib.sha256(
        (course.model_dump_json() + question.model_dump_json()).encode('utf-8')
    ).hexdigest()
    history_key = f'answer_followup_history_{scope}'
    help_heading(tr('Ask about this explanation'), tr('Ask what you did not understand. This conversation stays in this session and does not change your score.'))
    for item in st.session_state.get(history_key, []):
        with st.chat_message('user'):
            st.write(item['question'])
        with st.chat_message('assistant'):
            st.write(item['answer'])
    with st.form(f'answer_followup_form_{scope}', clear_on_submit=True):
        question_text = st.text_area(
            tr('What part is unclear?'),
            placeholder=tr('For example: why is option B incorrect?'),
            max_chars=MAX_TUTOR_QUESTION_CHARS,
        )
        with st.container(horizontal=True, horizontal_alignment='right', key=f'followup_actions_{scope}'):
            submitted = st.form_submit_button(tr('Ask AI'), type='primary')
    if not submitted:
        return
    question_text = question_text.strip()
    if not question_text:
        st.warning(tr('Enter a question first.'))
        return
    language = 'Simplified Chinese' if st.session_state.get(LANGUAGE_KEY, False) else 'English'
    prompt = (
        f'Answer in {language}. The student is reviewing this exact question. '
        'Explain the unclear part step by step, using the selected answer and reference explanation as context. '
        'If the reference is insufficient, say so; do not invent course claims. '
        f'Question: {question.question}\n'
        f'Options: {question.options}\n'
        f'Correct option: {question.options[question.correct_index]}\n'
        f'Reference explanation: {question.explanation}\n'
        f'Student asks: {question_text}'
    )
    # Limit the assembled prompt as well as the text area: ask_tutor caps total question length.
    if len(prompt) > MAX_TUTOR_QUESTION_CHARS:
        st.warning(tr('Your question is too long for this explanation. Please shorten it.'))
        return
    with st.spinner(tr('Preparing the explanation…')):
        result = ask_tutor(course.model_dump(mode='json'), prompt, question.topic_id)
    if not result.get('ok') or not result.get('answer', '').strip():
        st.warning(tr('AI is unavailable right now. Your score and explanation are unchanged.'))
        return
    st.session_state.setdefault(history_key, []).append(
        {'question': question_text, 'answer': result['answer']}
    )
    with st.chat_message('user'):
        st.write(question_text)
    with st.chat_message('assistant'):
        st.write(result['answer'])
