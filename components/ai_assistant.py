import streamlit as st

from services.gemini_service import ask_tutor

ASSISTANT_CONTAINER_KEY = "ai_assistant_fab"


def assistant_question_key(course_id: str) -> str:
    return f"assistant_question_{course_id}"


def assistant_result_key(course_id: str) -> str:
    return f"assistant_result_{course_id}"


def _apply_assistant_style() -> None:
    st.markdown(
        f"""
        <style>
        .st-key-{ASSISTANT_CONTAINER_KEY} {{
            position: fixed;
            right: 1rem;
            bottom: 1rem;
            z-index: 999;
            width: auto;
        }}
        div[data-testid="stPopoverBody"] {{
            max-width: min(24rem, calc(100vw - 2rem));
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_ai_assistant() -> None:
    _apply_assistant_style()
    course = st.session_state.get("current_course")

    with st.container(key=ASSISTANT_CONTAINER_KEY):
        with st.popover("AI assistant", icon=":material/chat:"):
            if course is None:
                st.info("Open a course first to ask the assistant.")
                return

            st.caption(f"Course: {course.course_name}")
            with st.form(key=f"assistant_form_{course.course_id}"):
                st.text_area(
                    "Ask a question",
                    key=assistant_question_key(course.course_id),
                    placeholder="Ask about this course...",
                )
                submitted = st.form_submit_button("Ask")

            if submitted:
                question = st.session_state[
                    assistant_question_key(course.course_id)
                ]
                with st.spinner("Answering..."):
                    response = ask_tutor(course.model_dump(), question)
                st.session_state[assistant_result_key(course.course_id)] = {
                    "question": question,
                    "response": response,
                }

            result = st.session_state.get(
                assistant_result_key(course.course_id)
            )
            if result:
                st.caption(f"Question: {result['question']}")
                if result["response"]["ok"]:
                    st.markdown(result["response"]["answer"])
                else:
                    st.error(result["response"]["message"])
