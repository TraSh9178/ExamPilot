from html import escape

import streamlit as st

from services.account_sync import render_last_save_status, save_exam_to_account
from services.accessibility import display_question, display_text
from services.question_editor import available_questions
from services.exam_engine import create_exam, grade_exam
from services.hints import hint_state_key, hints_for
from services.question_review import create_mistake_review, mistake_questions, question_sources
from services.practice_insights_ui import (
    start_focus_controls, answer_controls, checklist, capture_submission,
    result_overview, reflection_controls,
)
from services.practice_insights import session_insights
from services.learning_flow import install_practice, resume_draft, remember_widget, hydrate_widgets
from services.ui_style import apply_app_styles

def practice_label(records, sid, *, unfinished=False):
    """Human-readable choices; stable session IDs remain internal widget values."""
    record = records[sid]
    number = list(records).index(sid) + 1
    if "session" not in record:
        return f"{number} · Saved practice"
    mode = "Topic practice" if record["session"].mode == "topic" else "Mock exam"
    label = f"{number} · {mode} · {len(record['questions'])} questions"
    result = record.get("result")
    if result is not None:
        label += f" · {result['correct_count']}/{result['total_count']} correct"
    elif unfinished:
        label += " · Unfinished"
    return label


def submit_practice(course, practice_key):
    active = st.session_state[practice_key]
    session, questions = active["session"], active["questions"]
    if "result" in active:
        return
    answers = {q.id: st.session_state.get(f"answer_{session.session_id}_{q.id}") for q in questions}
    try:
        result = grade_exam(session, questions, answers)
    except ValueError as error:
        st.session_state["practice_submit_error"] = str(error)
        return
    updated = capture_submission(course, active)
    active["result"] = result
    history = st.session_state.setdefault(f"practice_history_{course.course_id}", {})
    history[session.session_id] = {
        "session": session, "questions": questions.copy(),
        "attempts": result["attempts"].copy(), "result": result,
    }
    save_exam_to_account(st.session_state, updated, session, result["attempts"])


def begin_mistake_review(practice_key, course, session, questions, confirmed_ids, topic_id):
    try:
        install_practice(st.session_state, course.course_id, create_mistake_review(
            session, questions, st.session_state[practice_key]["result"]["attempts"],
            confirmed_ids, topic_id, approved_ids={q.id for q in available_questions(course)},
        ))
    except ValueError as error:
        st.session_state["practice_launch_error"] = str(error)


apply_app_styles()

st.title("Practice")
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

unavailable_count = len(course.questions) - len(available_questions(course))
if unavailable_count:
    with st.expander("Question availability"):
        st.caption(f"{unavailable_count} pending, flagged or older-version questions are excluded from new practice.")
        st.page_link("pages/1_Study_Hub.py", label="Review questions in Study Plan")

practice_key = f"active_practice_{course.course_id}"
active_practice = st.session_state.get(practice_key)
entry_key = f"practice_entry_{course.course_id}"
pending_entry = st.session_state.get(entry_key)
if pending_entry is not None:
    target = pending_entry.get("topic_id")
    st.info("Set up a new practice" + (": " + topic_names[target] if target else " for your confirmed topics") + ". Your previous session is kept.")
    if active_practice and st.button("Return to previous session", key="practice_return_previous"):
        st.session_state.pop(entry_key, None)
        st.rerun()
st.session_state.pop("priority_ready", None)
drafts = st.session_state.get(f"practice_drafts_{course.course_id}", {})
if drafts:
    with st.expander(f"Unfinished sessions ({len(drafts)})"):
        draft_id = st.selectbox("Unfinished session", list(drafts), format_func=lambda sid: practice_label(drafts, sid, unfinished=True), key=f"draft_choice_{course.course_id}")
        st.button("Resume unfinished session", key=f"resume_draft_{course.course_id}",
            on_click=resume_draft, args=(st.session_state, course.course_id, draft_id))

with st.expander(
    "Change settings" if active_practice and pending_entry is None else "Practice settings",
    expanded=active_practice is None or pending_entry is not None,
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
            width="stretch",
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
            install_practice(st.session_state, course.course_id, {
                "settings": practice_settings,
                "session": exam["session"],
                "questions": exam["questions"],
                "warning": exam["warning"],
            })
            st.rerun()

active_practice = None if entry_key in st.session_state else st.session_state.get(practice_key)

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
        hydrate_widgets(st.session_state, active_practice, force=st.session_state.pop(f"rehydrate_practice_{course.course_id}", False))
        start_focus_controls(active_practice)

        for question_number, question in enumerate(questions, start=1):
            display = display_question(course.course_id, question, st.session_state)
            with st.container(
                border=True,
                key=f"practice_question_{question.id}",
            ):
                st.caption(f"QUESTION {question_number} OF {len(questions)}")
                st.markdown(f"### {display.question}")
                if display.simplified:
                    st.caption("Simplified wording")
                    with st.expander("Show original wording"):
                        st.write(question.question)
                        for option in question.options:
                            st.write(option)

                st.radio(
                    "Choose an answer",
                    options=list(range(len(question.options))),
                    format_func=lambda index, options=display.options: (
                        options[index]
                    ),
                    index=None,
                    width="stretch",
                    key=f"answer_{session.session_id}_{question.id}",
                    on_change=remember_widget,
                    args=(st.session_state, course.course_id, session.session_id, f"answer_{session.session_id}_{question.id}"),
                )

                answer_controls(active_practice, question, course.course_id)

                if session.mode == "topic" and (hints := hints_for(question)):
                    state_key = hint_state_key(session.session_id, question.id)
                    shown = st.session_state.get(state_key, 0)
                    for number, hint in enumerate(hints[:shown], start=1):
                        st.info(f"Hint {number} of {len(hints)}: {display_text(hint, st.session_state)}")
                    if shown < len(hints) and st.button(
                        "Show a hint" if shown == 0 else "Show next hint",
                        key=f"hint_button_{session.session_id}_{question.id}",
                    ):
                        st.session_state[state_key] = shown + 1
                        remember_widget(st.session_state, course.course_id, session.session_id, state_key)
                        st.rerun()

        checklist(active_practice)
        st.button("Submit answers", type="primary", on_click=submit_practice, args=(course, practice_key))
        if error := st.session_state.pop("practice_submit_error", None):
            st.error(f"Could not grade practice: {error}")

    if "result" in active_practice:
        result = active_practice["result"]
        render_last_save_status()

        st.subheader("Your result")
        if st.session_state.get(f"course_stage_{course.course_id}") == "questions_generated":
            st.caption("AI-generated questions: verify the answer and explanation against your material.")
        with st.container(key="practice_result_overview"):
            score_columns = st.columns(2)
            with score_columns[0].container(border=True):
                st.metric(
                    "Score",
                    f"{result['correct_count']} / {result['total_count']}",
                )
            with score_columns[1].container(border=True):
                st.metric("Accuracy", f"{result['accuracy']:.2f}%")

        summary_tab, answers_tab = st.tabs(["Summary & next steps", "Review answers"])
        with summary_tab:
            result_overview(course, session, questions, result)

        questions_by_id = {
            question.id: question for question in questions
        }

        with summary_tab:
            with st.container(border=True, key="practice_mistake_review"):
                try:
                    missed = mistake_questions(session, questions, result["attempts"])
                except ValueError:
                    missed = []
                    st.warning("This result could not be prepared for mistake review.")
                if missed:
                    st.markdown("**Review missed questions**")
                    st.caption(f"{len(missed)} incorrect or unanswered questions. A review creates a new graded session; your original score is preserved.")
                    missed_topics = list(dict.fromkeys(q.topic_id for q in missed if q.topic_id in confirmed_topic_ids))
                    review_topic = st.selectbox(
                        "Review topic", [None, *missed_topics],
                        format_func=lambda value: "All missed topics" if value is None else topic_names[value],
                        key=f"mistake_topic_{course.course_id}_{session.session_id}",
                    )
                    st.button(
                        "Practise missed questions", type="primary", key=f"review_mistakes_{session.session_id}",
                        on_click=begin_mistake_review,
                        args=(practice_key, course, session, questions, confirmed_topic_ids, review_topic),
                    )
                    if error := st.session_state.pop("practice_launch_error", None):
                        st.error(error)
                else:
                    st.caption("No missed questions to review in this session.")

        with answers_tab:
            for question_number, review in enumerate(
                result["question_results"], start=1
            ):
                question = questions_by_id[review["question_id"]]
                display = display_question(course.course_id, question, st.session_state)

                with st.container(
                    border=True,
                    key=f"practice_review_{question.id}",
                ):
                    st.caption(f"QUESTION {question_number}")
                    st.markdown(f"### {display.question}")
                    if display.simplified:
                        st.caption("Simplified wording")
                        with st.expander("Show original wording"):
                            st.write(question.question)
                            for option in question.options:
                                st.write(option)

                    selected_index = review["selected_index"]
                    correct_answer = display.options[
                        review["correct_index"]
                    ]

                    if selected_index is None:
                        st.warning("Unanswered")
                        st.success(f"✓ Correct answer: {correct_answer}")
                    else:
                        selected_answer = display.options[selected_index]
                        if review["is_correct"]:
                            st.success(f"✓ Your answer: {selected_answer}")
                        else:
                            st.error(f"✕ Your answer: {selected_answer}")
                            st.success(f"✓ Correct answer: {correct_answer}")

                    if session.mode == "topic" and (hints := hints_for(question)):
                        shown = session_insights(course, session.session_id).get(question.id, {}).get("hints_used")
                        if shown is not None:
                            st.caption(f"Hints used: {shown} of {len(hints)}")

                    with st.container(border=True):
                        st.subheader("Explanation")
                        st.write(display.explanation)
                    reflection_controls(course, session, question, review, confirmed_topic_ids, practice_key)
                    if question.source_pages:
                        st.caption("Cited pages: " + ", ".join(map(str, question.source_pages)))
                        sources = question_sources(question, st.session_state.get(f"course_document_{course.course_id}"))
                        if sources:
                            with st.expander("Check source material"):
                                for page, text in sources:
                                    st.caption(f"Page / slide {page}")
                                    st.text(text, width="stretch")
                        else:
                            st.caption("Source text is not available in this session; check the original material.")
                    else:
                        st.caption("No source page was provided for this question.")

# Show the number of graded sessions saved for this course.
history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

st.caption(f"Saved practice sessions: {len(history)}")
if history:
    with st.expander("Review a saved session"):
        saved_sid = st.selectbox("Saved session", list(history), format_func=lambda sid: practice_label(history, sid), key=f"saved_session_{course.course_id}")
        if st.button("Open saved result", key=f"open_saved_result_{course.course_id}"):
            record = history[saved_sid]
            saved_session = record["session"]
            st.session_state[practice_key] = {
                "session": saved_session, "questions": record["questions"], "result": record["result"],
                "warning": None, "settings": {},
            }
            st.rerun()
