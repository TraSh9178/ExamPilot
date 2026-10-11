from html import escape

import streamlit as st

from services.account_sync import render_last_save_status, save_exam_to_account
from services.exam_engine import create_exam, grade_exam
from services.ui_style import apply_app_styles

apply_app_styles()

st.title("📝 Practice")
st.caption("Choose a mode, then focus on one question at a time.")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("pages/0_Dashboard.py", label="Back to Dashboard")
    st.stop()

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    st.warning("Confirm your exam scope in Study Plan first.")
    if st.button("Choose exam scope", type="primary"):
        st.switch_page("pages/1_Study_Hub.py")
    st.stop()

# Validate the confirmed scope before offering practice settings.
topic_names = {topic.id: topic.name for topic in course.topics}

if (
    len(confirmed_topic_ids) != len(set(confirmed_topic_ids))
    or not set(confirmed_topic_ids).issubset(topic_names)
):
    st.error("The confirmed scope is invalid. Confirm it again in Study Plan.")
    st.page_link("pages/1_Study_Hub.py", label="Go to Study Plan")
    st.stop()

practice_key = f"active_practice_{course.course_id}"
active_practice = st.session_state.get(practice_key)

with st.expander(
    "Change settings" if active_practice else "Practice settings",
    expanded=active_practice is None,
):
    with st.container(border=True):
        st.caption(
            "Confirmed topics: "
            + " · ".join(topic_names[value] for value in confirmed_topic_ids)
        )
        mode_label = st.radio(
            "Practice mode",
            options=["Mock Exam", "Topic Practice"],
            key=f"practice_mode_{course.course_id}",
            horizontal=True,
        )

        mode = "mock" if mode_label == "Mock Exam" else "topic"
        topic_id = None

        settings_columns = st.columns([2, 1])
        if mode == "topic":
            topic_id = settings_columns[0].selectbox(
                "Knowledge point",
                options=confirmed_topic_ids,
                format_func=lambda value: topic_names[value],
                key=f"practice_topic_{course.course_id}",
            )
            count_column = settings_columns[1]
        else:
            count_column = settings_columns[0]

        requested_count = count_column.number_input(
            "Number of questions",
            min_value=1,
            max_value=50,
            value=10,
            step=1,
            key=f"practice_count_{course.course_id}",
        )

    practice_settings = {
        "mode": mode,
        "requested_count": int(requested_count),
        "confirmed_topic_ids": sorted(confirmed_topic_ids),
        "topic_id": topic_id,
    }

    start_label = (
        "Start new practice"
        if active_practice is not None
        else "Start practice"
    )
    if st.button(start_label, type="primary"):
        try:
            exam = create_exam(
                package=course,
                mode=mode,
                requested_count=int(requested_count),
                confirmed_topic_ids=list(confirmed_topic_ids),
                topic_id=topic_id,
            )
        except ValueError as error:
            st.error(f"Could not create practice: {error}")
        else:
            st.session_state[practice_key] = {
                "settings": practice_settings,
                "session": exam["session"],
                "questions": exam["questions"],
                "warning": exam["warning"],
            }
            st.rerun()

active_practice = st.session_state.get(practice_key)

if active_practice is not None:
    session = active_practice["session"]
    questions = active_practice["questions"]
    mode_name = "Mock Exam" if session.mode == "mock" else "Topic Practice"

    st.subheader("Practice session")
    with st.container(border=True, key="practice_overview"):
        overview = st.columns([3, 1.25, 0.7])
        with overview[0]:
            st.caption("Course")
            with st.container(key="practice_course_heading"):
                st.markdown(f"**{escape(course.course_name)}**")
        with overview[1]:
            st.caption("Mode")
            st.markdown(f"**{mode_name}**")
        with overview[2]:
            st.caption("Questions")
            st.markdown(f"**{len(questions)}**")

    if active_practice["warning"]:
        st.warning(active_practice["warning"])

    submitted = "result" in active_practice

    if not submitted:
        st.subheader("Questions")

        for question_number, question in enumerate(questions, start=1):
            with st.container(
                border=True,
                key=f"practice_question_{question.id}",
            ):
                st.caption(f"QUESTION {question_number} OF {len(questions)}")
                st.markdown(f"### {question.question}")

                st.radio(
                    "Choose an answer",
                    options=list(range(len(question.options))),
                    format_func=lambda index, options=question.options: (
                        options[index]
                    ),
                    index=None,
                    key=f"answer_{session.session_id}_{question.id}",
                )

        if st.button("Submit answers", type="primary"):
            selected_answers = {
                question.id: st.session_state.get(
                    f"answer_{session.session_id}_{question.id}"
                )
                for question in questions
            }

            try:
                result = grade_exam(
                    session,
                    questions,
                    selected_answers,
                )
            except ValueError as error:
                st.error(f"Could not grade practice: {error}")
            else:
                active_practice["result"] = result
                st.session_state[practice_key] = active_practice

                # Store each graded session once, separately by course.
                history_key = f"practice_history_{course.course_id}"
                history = st.session_state.setdefault(history_key, {})

                history[session.session_id] = {
                    "session": session,
                    "questions": questions.copy(),
                    "attempts": result["attempts"].copy(),
                    "result": result,
                }

                save_exam_to_account(
                    st.session_state,
                    course,
                    session,
                    result["attempts"],
                )

                st.rerun()

    if "result" in active_practice:
        result = active_practice["result"]
        render_last_save_status()

        st.subheader("Your result")
        with st.container(key="practice_result_overview"):
            score_columns = st.columns(2)
            with score_columns[0].container(border=True):
                st.metric(
                    "Score",
                    f"{result['correct_count']} / {result['total_count']}",
                )
            with score_columns[1].container(border=True):
                st.metric("Accuracy", f"{result['accuracy']:.2f}%")

        questions_by_id = {
            question.id: question for question in questions
        }

        for question_number, review in enumerate(
            result["question_results"], start=1
        ):
            question = questions_by_id[review["question_id"]]

            with st.container(
                border=True,
                key=f"practice_review_{question.id}",
            ):
                st.caption(f"QUESTION {question_number}")
                st.markdown(f"### {question.question}")

                selected_index = review["selected_index"]
                correct_answer = question.options[
                    review["correct_index"]
                ]

                if selected_index is None:
                    st.warning("Unanswered")
                    st.success(f"✓ Correct answer: {correct_answer}")
                else:
                    selected_answer = question.options[selected_index]
                    if review["is_correct"]:
                        st.success(f"✓ Your answer: {selected_answer}")
                    else:
                        st.error(f"✕ Your answer: {selected_answer}")
                        st.success(f"✓ Correct answer: {correct_answer}")

                with st.container(border=True):
                    st.subheader("Explanation")
                    st.write(review["explanation"])
# Show the number of graded sessions saved for this course.
history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

st.caption(f"Saved practice sessions: {len(history)}")
