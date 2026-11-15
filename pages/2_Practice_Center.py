from services.i18n import tr
from html import escape
import time

import streamlit as st

from services.account_sync import render_last_save_status, save_exam_to_account
from services.accessibility import display_question, display_text
from services.question_editor import available_questions
from services.exam_engine import create_exam, grade_exam
from services.guided_limits_ui import render_guided_review
from services.hints import hint_state_key, hints_for
from services.question_review import create_mistake_review, mistake_questions, question_sources
from services.practice_insights_ui import (
    start_focus_controls, answer_controls, checklist, capture_submission,
    result_overview, reflection_controls,
)
from services.practice_insights import focus_question, session_insights
from services.auth_session import current_user
from services import learning_radar
from components.knowledge_graph import load_course_radar, render_topic_radar
from services.learning_flow import install_practice, resume_draft, remember_widget, hydrate_widgets, open_lab
from services.ui_style import apply_app_styles

try:
    from components import radar_chart
except ImportError:  # merged later
    radar_chart = None

# "All missed topics" choice of the review-topic pills; it means no topic filter.
ALL_MISSED_TOPICS = "__all_missed_topics__"


def question_count(count):
    return tr("1 question") if count == 1 else tr(f"{count} questions")


def practice_label(records, sid, *, unfinished=False):
    """Human-readable choices; stable session IDs remain internal widget values."""
    record = records[sid]
    number = list(records).index(sid) + 1
    if "session" not in record:
        return f"{number} · {tr('Saved practice')}"
    mode = tr("Topic practice") if record["session"].mode == "topic" else tr("Mock exam")
    label = f"{number} · {mode} · {question_count(len(record['questions']))}"
    result = record.get("result")
    if result is not None:
        label += " · " + tr(f"{result['correct_count']}/{result['total_count']} correct")
    elif unfinished:
        label += " · " + tr("Unfinished")
    return label


def render_question_heading(number, text):
    """Paper question card: a two-digit badge beside the question text."""
    body = "<br>".join(escape(line, quote=False) for line in text.splitlines())
    st.markdown(
        f'<div class="paper-question"><span class="paper-question-badge">{escape(tr(f"Q{number:02}"))}</span>'
        f'<div class="paper-question-text">{body}</div></div>',
        unsafe_allow_html=True,
    )


def submit_practice(course, practice_key):
    active = st.session_state[practice_key]
    session, questions = active["session"], active["questions"]
    if "result" in active:
        return
    hydrate_widgets(st.session_state, active)
    answers = {q.id: st.session_state.get(f"answer_{session.session_id}_{q.id}") for q in questions}
    try:
        result = grade_exam(session, questions, answers)
    except ValueError:
        st.session_state["practice_submit_error"] = True
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

st.title(tr("Practice"))
st.caption(tr("Choose a mode, then focus on one question at a time."))

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    st.warning(tr("Confirm your exam scope in Study Plan first."))
    if st.button(tr("Choose exam scope"), type="primary"):
        st.switch_page("pages/1_Study_Hub.py")
    st.stop()

# Validate the confirmed scope before offering practice settings.
topic_names = {topic.id: topic.name for topic in course.topics}

if (
    len(confirmed_topic_ids) != len(set(confirmed_topic_ids))
    or not set(confirmed_topic_ids).issubset(topic_names)
):
    st.error(tr("The confirmed scope is invalid. Confirm it again in Study Plan."))
    st.page_link("pages/1_Study_Hub.py", label=tr("Go to Study Plan"))
    st.stop()

practice_key = f"active_practice_{course.course_id}"
active_practice = st.session_state.get(practice_key)
entry_key = f"practice_entry_{course.course_id}"
pending_entry = st.session_state.get(entry_key)
if pending_entry is not None:
    target = pending_entry.get("topic_id")
    st.info(
        (tr("New practice: ") + topic_names[target]) if target
        else tr("New practice for your confirmed topics.")
    )
    if active_practice and st.button(tr("Return to previous session"), key="practice_return_previous"):
        st.session_state.pop(entry_key, None)
        st.rerun()
st.session_state.pop("priority_ready", None)
drafts = st.session_state.get(f"practice_drafts_{course.course_id}", {})
if drafts:
    with st.expander(tr(f"Unfinished sessions ({len(drafts)})")):
        draft_id = st.selectbox(tr("Unfinished session"), list(drafts), format_func=lambda sid: practice_label(drafts, sid, unfinished=True), key=f"draft_choice_{course.course_id}")
        st.button(tr("Resume unfinished session"), key=f"resume_draft_{course.course_id}",
            on_click=resume_draft, args=(st.session_state, course.course_id, draft_id))

with st.expander(
    tr("Change settings") if active_practice and pending_entry is None else tr("Practice settings"),
    expanded=active_practice is None or pending_entry is not None,
):
    with st.container(border=True):
        st.caption(
            tr("Confirmed topics") + ": "
            + " · ".join(topic_names[value] for value in confirmed_topic_ids)
        )
        mode_label = st.radio(
            tr("Practice mode"),
            options=[tr("Mock Exam"), tr("Topic Practice")],
            key=f"practice_mode_{course.course_id}",
            horizontal=True,
            width="stretch",
        )

        mode = "mock" if mode_label == tr("Mock Exam") else "topic"
        topic_id = None

        settings_columns = st.columns([2, 1])
        if mode == "topic":
            topic_id = settings_columns[0].selectbox(
                tr("Knowledge point"),
                options=confirmed_topic_ids,
                format_func=lambda value: topic_names[value],
                key=f"practice_topic_{course.course_id}",
            )
            count_column = settings_columns[1]
        else:
            count_column = settings_columns[0]

        requested_count = count_column.number_input(
            tr("Number of questions"),
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
    if st.button(tr(start_label), type="primary"):
        try:
            exam = create_exam(
                package=course,
                mode=mode,
                requested_count=int(requested_count),
                confirmed_topic_ids=list(confirmed_topic_ids),
                topic_id=topic_id,
            )
        except ValueError:
            st.error(tr("Could not create practice. Try another topic or check your exam scope in Study Plan."))
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

    st.subheader(tr("Practice session"))
    with st.container(border=True, key="practice_overview"):
        overview = st.columns([3, 1.25, 0.7])
        with overview[0]:
            st.caption(tr("Course"))
            with st.container(key="practice_course_heading"):
                st.markdown(f"**{escape(course.course_name)}**")
        with overview[1]:
            st.caption(tr("Mode"))
            st.markdown(f"**{tr(mode_name)}**")
        with overview[2]:
            st.caption(tr("Questions"))
            st.markdown(f"**{len(questions)}**")

    if active_practice["warning"]:
        st.warning(tr(active_practice["warning"]))

    submitted = "result" in active_practice

    if not submitted:
        hydrate_widgets(st.session_state, active_practice, force=st.session_state.pop(f"rehydrate_practice_{course.course_id}", False))
        question_index = min(active_practice.get("worksheet_index", 0), len(questions) - 1)
        selected_question = questions[question_index]
        answered = sum(
            st.session_state.get(f"answer_{session.session_id}_{question.id}") is not None
            for question in questions
        )
        radar_on = learning_radar.radar_enabled(course.course_id)
        user = current_user(st.session_state) if radar_on else None
        # The "I'm stuck" choices are only offered to signed-in users of demo courses.
        offer_stuck = radar_chart is not None and user is not None
        if session.mode == "topic":
            paper, margin = st.columns([3, 1], gap="large")
            visible_questions = [(question_index + 1, selected_question)]
        else:
            paper = st.container()
            margin = None
            visible_questions = list(enumerate(questions, start=1))
        with paper, st.container(key="flight_worksheet"):
            with st.container(key="flight_practice_progress"):
                st.caption(tr("Question") + f" {question_index + 1:02} / {len(questions):02}" if margin is not None else tr("Questions"))
                if margin is not None:
                    stops = min(len(questions), 12)
                    current_stop = question_index * (stops - 1) // max(1, len(questions) - 1)
                    markers = "".join(
                        '<span class="flight-waypoint is-current">✈</span>' if step == current_stop
                        else '<span class="flight-waypoint"></span>'
                        for step in range(stops)
                    )
                    st.markdown(
                        f'<div class="flight-waypoints" aria-hidden="true">{markers}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.progress(answered / len(questions))
                st.caption(tr("Answered") + f" · {answered} / {len(questions)}")
            with st.expander(tr("Focus controls")):
                start_focus_controls(active_practice)

            paging = margin is not None and len(questions) > 1
            movement = 0
            for question_number, question in visible_questions:
                display = display_question(course.course_id, question, st.session_state)
                with st.container(
                    border=session.mode == "mock",
                    key=f"practice_question_{question.id}",
                ):
                    render_question_heading(question_number, display.question)
                    if display.simplified:
                        st.caption(tr("Simplified wording"))
                        with st.expander(tr("Show original wording")):
                            st.write(question.question)
                            for option in question.options:
                                st.write(option)

                    st.radio(
                        tr("Choose an answer"),
                        options=list(range(len(question.options))),
                        format_func=lambda index, options=display.options: (
                            f"{chr(ord('A') + index)}. {options[index]}"
                        ),
                        index=None,
                        width="stretch",
                        key=f"answer_{session.session_id}_{question.id}",
                        on_change=remember_widget,
                        args=(st.session_state, course.course_id, session.session_id, f"answer_{session.session_id}_{question.id}"),
                    )

                    answer_controls(active_practice, question, course.course_id)

                    hints = hints_for(question) if session.mode == "topic" else []
                    state_key = hint_state_key(session.session_id, question.id)
                    shown = st.session_state.get(state_key, 0) if hints else 0
                    for number, hint in enumerate(hints[:shown], start=1):
                        st.info(tr(f"Hint {number} of {len(hints)}: {display_text(hint, st.session_state)}"))

                    # Actions under the question: Previous · Hint · Learning Radar · Next.
                    if paging or shown < len(hints) or offer_stuck:
                        with st.container(
                            horizontal=True, horizontal_alignment="distribute",
                            vertical_alignment="center", key=f"paper_actions_{question.id}",
                        ):
                            if paging and st.button(
                                tr("Previous"), icon=":material/arrow_back:", disabled=question_index == 0,
                                key=f"worksheet_previous_{session.session_id}",
                            ):
                                movement = -1
                            if shown < len(hints) and st.button(
                                tr("Hint") if shown == 0 else tr("Next hint"), icon=":material/lightbulb:",
                                key=f"hint_button_{session.session_id}_{question.id}",
                            ):
                                st.session_state[state_key] = shown + 1
                                remember_widget(st.session_state, course.course_id, session.session_id, state_key)
                                st.rerun()
                            if offer_stuck:
                                with st.popover(
                                    tr("Learning Radar"), icon=":material/radar:",
                                    key=f"practice_radar_menu_{session.session_id}_{question.id}",
                                ):
                                    radar_chart.render_stuck_buttons(
                                        st.session_state, course.course_id, question.topic_id, user.user_id,
                                        key=f"practice_stuck_{session.session_id}_{question.id}",
                                    )
                            if paging and st.button(
                                tr("Next"), icon=":material/arrow_forward:", disabled=question_index == len(questions) - 1,
                                key=f"worksheet_next_{session.session_id}",
                            ):
                                movement = 1

            if movement:
                new_index = question_index + movement
                active_practice["worksheet_index"] = new_index
                timer = active_practice.get("focus_timer", {})
                if timer.get("since") is not None:
                    focus_question(active_practice, questions[new_index].id, time.monotonic())
                elif timer:
                    timer["question_id"] = questions[new_index].id
                st.rerun()

        if margin is not None:
            with margin, st.container(key="flight_worksheet_margin"):
                if radar_on:
                    st.subheader(tr("Learning Radar"))
                    radar, _ = load_course_radar(st.session_state, course.course_id, user.user_id if user else None)
                    if radar_chart is not None:
                        radar_chart.render_course_radar_chart(
                            course, radar, focus_topic_id=selected_question.topic_id, key="practice_radar",
                        )
                    render_topic_radar(radar.topics.get(selected_question.topic_id))
                    if st.button(tr("Explore this topic"), key=f"worksheet_radar_{session.session_id}"):
                        st.session_state[f"graph_pending_focus_{course.course_id}"] = selected_question.topic_id
                        st.switch_page("pages/4_Knowledge_Graph.py")
                    st.divider()
                topic = next((topic for topic in course.topics if topic.id == selected_question.topic_id), None)
                if topic is not None:
                    st.subheader(tr("Quick Notes"))
                    st.caption(topic.name)
                    st.write(display_text(topic.summary, st.session_state))

        checklist(active_practice)
        st.button(tr("Submit answers"), type="primary", on_click=submit_practice, args=(course, practice_key))
        if st.session_state.pop("practice_submit_error", None):
            st.error(tr("Could not grade this practice. Please try again."))

    if "result" in active_practice:
        result = active_practice["result"]
        render_last_save_status()

        st.subheader(tr("Your result"))
        if st.session_state.get(f"course_stage_{course.course_id}") == "questions_generated":
            st.caption(tr("AI-generated questions: verify the answer and explanation against your material."))
        with st.container(key="practice_result_overview"):
            score_columns = st.columns(2)
            with score_columns[0].container(border=True):
                st.metric(
                    tr("Score"),
                    f"{result['correct_count']} / {result['total_count']}",
                )
            with score_columns[1].container(border=True):
                st.metric(tr("Accuracy"), f"{result['accuracy']:.2f}%")

        summary_tab, answers_tab = st.tabs([tr("Summary & next steps"), tr("Review answers")])
        with summary_tab:
            missed_ids = {
                attempt.question_id for attempt in result["attempts"] if not attempt.is_correct
            }
            next_question = next((q for q in questions if q.id in missed_ids), questions[0])
            with st.container(border=True, key="flight_next_topic"):
                st.caption(tr("Take the next step"))
                st.markdown(f"**{escape(topic_names.get(next_question.topic_id, tr('Topic')))}**")
                if next_question.topic_id in topic_names and st.button(
                    tr("Open this topic in Knowledge Map"), key=f"flight_map_{session.session_id}",
                    icon=":material/hub:",
                ):
                    st.session_state[f"graph_pending_focus_{course.course_id}"] = next_question.topic_id
                    st.switch_page("pages/4_Knowledge_Graph.py")
                if course.course_id == "calculus-i-demo" and next_question.topic_id in {"calc_limits", "calc_derivatives"}:
                    if st.button(tr("Explore this topic in Concept Lab"), key=f"flight_lab_{session.session_id}"):
                        open_lab(st.session_state, course.course_id, next_question.topic_id)
                        st.switch_page("pages/6_Concept_Lab.py")
            guided_review_available = render_guided_review(course, session, questions, result)
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
                    st.warning(tr("This result could not be prepared for mistake review."))
                if missed:
                    st.markdown(tr("**Review missed questions**"))
                    st.caption(
                        tr("1 missed question to practise; your score stays the same.") if len(missed) == 1
                        else tr(f"{len(missed)} missed questions to practise; your score stays the same.")
                    )
                    missed_topics = list(dict.fromkeys(q.topic_id for q in missed if q.topic_id in confirmed_topic_ids))
                    review_choice = st.pills(
                        tr("Review topic"), [ALL_MISSED_TOPICS, *missed_topics], default=ALL_MISSED_TOPICS,
                        format_func=lambda value: tr("All missed topics") if value == ALL_MISSED_TOPICS else topic_names[value],
                        key=f"mistake_topic_{course.course_id}_{session.session_id}",
                    )
                    # No pill, or the "All missed topics" pill, keeps every missed topic.
                    review_topic = None if review_choice in (None, ALL_MISSED_TOPICS) else review_choice
                    st.button(
                        tr("Practise missed questions"), type="secondary" if guided_review_available else "primary",
                        key=f"review_mistakes_{session.session_id}",
                        on_click=begin_mistake_review,
                        args=(practice_key, course, session, questions, confirmed_topic_ids, review_topic),
                    )
                    if error := st.session_state.pop("practice_launch_error", None):
                        st.error(tr(error))
                else:
                    st.caption(tr("No missed questions to review in this session."))

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
                    render_question_heading(question_number, display.question)
                    if display.simplified:
                        st.caption(tr("Simplified wording"))
                        with st.expander(tr("Show original wording")):
                            st.write(question.question)
                            for option in question.options:
                                st.write(option)

                    selected_index = review["selected_index"]
                    correct_answer = display.options[
                        review["correct_index"]
                    ]

                    if selected_index is None:
                        st.warning(tr("Unanswered"))
                        st.success(tr(f"✓ Correct answer: {correct_answer}"))
                    else:
                        selected_answer = display.options[selected_index]
                        if review["is_correct"]:
                            st.success(tr(f"✓ Your answer: {selected_answer}"))
                        else:
                            st.error(tr(f"✕ Your answer: {selected_answer}"))
                            st.success(tr(f"✓ Correct answer: {correct_answer}"))

                    if session.mode == "topic" and (hints := hints_for(question)):
                        shown = session_insights(course, session.session_id).get(question.id, {}).get("hints_used")
                        if shown is not None:
                            st.caption(tr(f"Hints used: {shown} of {len(hints)}"))

                    with st.container(border=True):
                        st.subheader(tr("Explanation"))
                        st.write(display.explanation)
                    reflection_controls(course, session, question, review, confirmed_topic_ids, practice_key)
                    if question.source_pages:
                        st.caption(tr("Cited pages: ") + ", ".join(map(str, question.source_pages)))
                        sources = question_sources(question, st.session_state.get(f"course_document_{course.course_id}"))
                        if sources:
                            with st.expander(tr("Check source material")):
                                for page, text in sources:
                                    st.caption(tr(f"Page / slide {page}"))
                                    st.text(text, width="stretch")

# Graded sessions saved for this course can be reopened.
history_key = f"practice_history_{course.course_id}"
history = st.session_state.get(history_key, {})

if history:
    with st.expander(tr("Review a saved session")):
        saved_sid = st.selectbox(tr("Saved session"), list(history), format_func=lambda sid: practice_label(history, sid), key=f"saved_session_{course.course_id}")
        if st.button(tr("Open saved result"), key=f"open_saved_result_{course.course_id}"):
            record = history[saved_sid]
            saved_session = record["session"]
            st.session_state[practice_key] = {
                "session": saved_session, "questions": record["questions"], "result": record["result"],
                "warning": None, "settings": {},
            }
            st.rerun()
