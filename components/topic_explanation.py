"""On-demand topic teaching, with existing course examples available offline."""
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
    with st.expander(tr("Detailed explanation & examples")):
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
        st.markdown(tr("**Example from this course**"))
        st.caption(tr("Original course wording is preserved. Reading examples does not count as a graded attempt."))
        if not examples:
            st.caption(tr("There is no example for this topic in the current course yet."))
            return
        example = st.selectbox(
            tr("Choose an example"), examples,
            format_func=lambda item: item.question,
            key=f"graph_example_{fingerprint}",
        )
        st.write(example.question)
        for index, option in enumerate(example.options):
            st.write(f"{chr(65 + index)}. {option}")
        if st.checkbox(tr("Show answer and explanation"), key=f"graph_solution_{fingerprint}_{example.id}"):
            st.markdown(tr("**Answer**"))
            st.write(f"{chr(65 + example.correct_index)}. {example.options[example.correct_index]}")
            st.markdown(tr("**Why this answer**"))
            st.write(example.explanation)
