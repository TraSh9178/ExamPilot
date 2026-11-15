"""On-demand topic teaching, with existing course examples available offline."""
from services.ui_help import help_tip
import hashlib

import streamlit as st

from models.schemas import StudyPackage
from services.ai_service import ask_tutor
from services.i18n import LANGUAGE_KEY, tr


def render_topic_explanation(course: StudyPackage, topic_id: str) -> None:
    topic = next((item for item in course.topics if item.id == topic_id), None)
    if topic is None:
        return
    chinese = bool(st.session_state.get(LANGUAGE_KEY, False))
    # Include content, not just IDs: regenerated courses must not reuse old answers.
    fingerprint = hashlib.sha256(
        (course.model_dump_json() + topic_id + str(chinese)).encode()
    ).hexdigest()
    with st.container(key="topic_teaching_content"):
        from services.demo_teaching import calculus_lesson
        from services.demo_updates import FILES
        lesson = calculus_lesson(topic_id, chinese) if course.course_id == 'calculus-i-demo' else None
        if lesson:
            steps, worked, mistake = lesson
            st.subheader(tr("Step-by-step explanation"))
            for number, step in enumerate(steps, 1):
                st.write(f"{number}. {step}")
            with st.container(border=True, key="topic_worked_example"):
                st.markdown('**' + tr('Worked example') + '**')
                st.write(worked)
            st.caption(tr('Common mistake') + ': ' + mistake)
        elif course.course_id in FILES:
            st.subheader(tr("Step-by-step explanation"))
            st.write(topic.summary)
            first = next((q for q in course.questions if q.topic_id == topic_id), None)
            if first:
                st.markdown('**' + tr('Worked example') + '**')
                st.write(first.question)
                st.write(first.explanation)
        else:
            st.caption(tr("Go beyond the summary: understand the idea, then work through an example."))
            if st.button(tr("Explain step by step"), key=f"graph_explain_{fingerprint}"):
                language = "Simplified Chinese" if chinese else "English"
                prompt = (
                    f"Explain this selected topic in {language} for a student who found the summary too abstract. "
                    "Use short numbered sections: 1. Intuition in everyday language; "
                    "2. Key conditions or steps and why each matters; "
                    "3. One simple worked example with each reasoning step; "
                    "4. A common mistake and how to avoid it; 5. One self-check question. "
                    "Label any illustrative example as an example, not a quotation from the course. "
                    "Use only the supported concepts; explicitly acknowledge missing context. "
                    "Do not merely repeat the summary."
                )
                with st.spinner(tr("Preparing the explanation…")):
                    result = ask_tutor(course.model_dump(mode="json"), prompt, topic_id)
                if result.get("ok") and result.get("answer", "").strip():
                    st.session_state["graph_topic_explanation"] = {
                        "fingerprint": fingerprint, "answer": result["answer"]
                    }
                else:
                    st.warning(tr("The explanation is unavailable. You can still read the course example below, or try again."))
            saved = st.session_state.get("graph_topic_explanation", {})
            if saved.get("fingerprint") == fingerprint:
                st.caption(tr("AI explanation · check it against your course material."))
                st.write(saved["answer"])

        examples = [question for question in course.questions if question.topic_id == topic_id]
        st.subheader(tr("Example from this course"))
        if not examples:
            st.caption(tr("There is no example for this topic in the current course yet."))
            return
        by_id = {item.id: item for item in examples}
        selected_key = f'graph_selected_example_{fingerprint}'
        selected = st.session_state.get(selected_key)
        if selected not in by_id:
            def choose_example():
                st.session_state[selected_key] = st.session_state.get(f'graph_example_{fingerprint}')
            st.selectbox(
                tr("Choose an example"), list(by_id), index=None,
                format_func=lambda item: by_id[item].question,
                key=f"graph_example_{fingerprint}", on_change=choose_example,
                placeholder=tr('Choose an example'),
            )
            return
        example = by_id[selected]
        from services.practice_pages_ui import render_question_heading
        with st.container(border=True, key=f"topic_example_card_{fingerprint}"):
            render_question_heading(examples.index(example) + 1, example.question)
            st.radio(tr('Choose an answer'), list(range(len(example.options))), index=None,
                     format_func=lambda i: f"{chr(65+i)}. {example.options[i]}",
                     key=f'graph_example_answer_{fingerprint}_{example.id}')
            if st.checkbox(tr("Show answer and explanation"), key=f"graph_solution_{fingerprint}_{example.id}"):
                st.markdown(tr("**Answer**"))
                st.write(f"{chr(65 + example.correct_index)}. {example.options[example.correct_index]}")
                st.markdown(tr("**Why this answer**"))
                st.write(example.explanation)
            with st.container(key='example_footer'):
                help_tip(tr("Original course wording is preserved. Reading examples does not count as a graded attempt."))
        def change_example():
            st.session_state.pop(selected_key, None)
            st.session_state.pop(f'graph_example_{fingerprint}', None)
        st.button(tr('Change example'), key=f'graph_change_example_{fingerprint}', on_click=change_example)
