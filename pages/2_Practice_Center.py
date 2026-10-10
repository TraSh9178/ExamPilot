import streamlit as st

from services.exam_engine import create_exam, grade_exam

st.set_page_config(
    page_title="Practice Center | ExamPilot",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Practice Center")

course = st.session_state.get("current_course")

if course is None:
    st.info("Load a course from the dashboard first.")
    st.page_link("app.py", label="Back to Dashboard")
    st.stop()

st.subheader(course.course_name)

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    st.warning("Confirm your exam scope in Study Hub first.")
    if st.button("Change exam scope", type="primary"):
        st.switch_page("pages/1_Study_Hub.py")
    st.stop()

# Validate the confirmed scope before offering practice settings.
topic_names = {topic.id: topic.name for topic in course.topics}

if (
    len(confirmed_topic_ids) != len(set(confirmed_topic_ids))
    or not set(confirmed_topic_ids).issubset(topic_names)
):
    st.error("The confirmed scope is invalid. Confirm it again in Study Hub.")
    st.page_link("pages/1_Study_Hub.py", label="Go to Study Hub")
    st.stop()

st.caption("Confirmed exam scope")

for confirmed_topic_id in confirmed_topic_ids:
    st.write(f"• {topic_names[confirmed_topic_id]}")

if st.button("Change exam scope", type="primary"):
    st.switch_page("pages/1_Study_Hub.py")

mode_label = st.radio(
    "Practice mode",
    options=["Mock Exam", "Topic Practice"],
    key=f"practice_mode_{course.course_id}",
)

mode = "mock" if mode_label == "Mock Exam" else "topic"
topic_id = None

if mode == "topic":
    topic_id = st.selectbox(
        "Choose a confirmed topic",
        options=confirmed_topic_ids,
        format_func=lambda value: topic_names[value],
        key=f"practice_topic_{course.course_id}",
    )

requested_count = st.number_input(
    "Number of questions",
    min_value=1,
    max_value=50,
    value=10,
    step=1,
    key=f"practice_count_{course.course_id}",
)

# Keep practice state separate for each course.
practice_key = f"active_practice_{course.course_id}"

# Changing settings invalidates the previous practice session.
practice_settings = {
    "mode": mode,
    "requested_count": int(requested_count),
    "confirmed_topic_ids": sorted(confirmed_topic_ids),
    "topic_id": topic_id,
}

active_practice = st.session_state.get(practice_key)

if (
    active_practice is not None
    and active_practice["settings"] != practice_settings
):
    st.session_state.pop(practice_key, None)

if st.button("Start practice", type="primary"):
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

active_practice = st.session_state.get(practice_key)

if active_practice is not None:
    if active_practice["warning"]:
        st.warning(active_practice["warning"])

    st.success(
        f"Practice created: {len(active_practice['questions'])} question(s)."
    )
    session = active_practice["session"]
    questions = active_practice["questions"]
    submitted = "result" in active_practice

    st.subheader("Your questions")

    for question_number, question in enumerate(questions, start=1):
        with st.container(border=True):
            st.write(f"Question {question_number}")
            st.write(question.question)

            st.radio(
                "Choose an answer",
                options=list(range(len(question.options))),
                format_func=lambda index, options=question.options: (
                    options[index]
                ),
                index=None,
                key=f"answer_{session.session_id}_{question.id}",
                disabled=submitted,
            )

    if not submitted:
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

                st.rerun()

    if "result" in active_practice:
        result = active_practice["result"]

        st.subheader("Your result")
        st.write(
            f"Score: {result['correct_count']} / "
            f"{result['total_count']}"
        )
        st.write(f"Accuracy: {result['accuracy']:.2f}%")

        questions_by_id = {
            question.id: question for question in questions
        }

        for review in result["question_results"]:
            question = questions_by_id[review["question_id"]]

            with st.container(border=True):
                st.write(question.question)

                selected_index = review["selected_index"]
                selected_answer = (
                    "Unanswered"
                    if selected_index is None
                    else question.options[selected_index]
                )
                st.write(f"Your answer: {selected_answer}")

                if review["is_correct"]:
                    st.success("Correct")
                else:
                    st.error("Incorrect")

                correct_answer = question.options[
                    review["correct_index"]
                ]
                st.write(f"Correct answer: {correct_answer}")
                st.write(review["explanation"])
# Show the number of graded sessions saved for this course.
history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

st.caption(f"Saved practice sessions: {len(history)}")