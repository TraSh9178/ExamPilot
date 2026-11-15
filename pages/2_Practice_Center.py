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
# Up to this many confirmed topics, the knowledge point is a row of one-click pills.
TOPIC_PILLS_LIMIT = 6

# The page shows one screen at a time:
#   setup    - mode, knowledge point, number of questions, drafts and saved sessions;
#   question - one question of the session in progress, nothing else;
#   review   - the check before submitting (active["worksheet_step"] == "review");
#   result   - the graded session.
# practice_setup_<course> holds the id of the session for which the student asked
# for the setup screen; any other session (a new one, a resumed one) ignores it.


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
    else:
        st.session_state.pop(f"practice_setup_{course.course_id}", None)


# ---- Screen changes (button callbacks; they run before the page) -------------------

def open_setup(course_id, session_id):
    """Show the setup screen; the session itself stays exactly as it is."""
    st.session_state[f"practice_setup_{course_id}"] = session_id


def return_to_session(course_id):
    st.session_state.pop(f"practice_entry_{course_id}", None)
    st.session_state.pop(f"practice_setup_{course_id}", None)


def start_practice(course, confirmed_topic_ids):
    """Start button: a new session from the settings on screen.

    It reads the widgets' latest values (a changed count arrives with the click).
    """
    state = st.session_state
    course_id = course.course_id
    mode = "mock" if state.get(f"practice_mode_{course_id}") == tr("Mock Exam") else "topic"
    topic_id = None
    if mode == "topic":
        topic_id = state.get(f"practice_topic_{course_id}")
        if topic_id not in confirmed_topic_ids:
            # The chosen pill was clicked off again, or the mode changed with this click
            # and the choice was not on screen yet: what the page would show.
            topic_id = state.get(f"practice_topic_last_{course_id}")
            if topic_id not in confirmed_topic_ids:
                topic_id = confirmed_topic_ids[0]
    requested_count = int(state.get(f"practice_count_{course_id}", 10))
    try:
        exam = create_exam(
            package=course,
            mode=mode,
            requested_count=requested_count,
            confirmed_topic_ids=list(confirmed_topic_ids),
            topic_id=topic_id,
        )
    except ValueError:
        state["practice_create_error"] = True
        return
    install_practice(state, course_id, {
        "settings": {
            "mode": mode,
            "requested_count": requested_count,
            "confirmed_topic_ids": sorted(confirmed_topic_ids),
            "topic_id": topic_id,
        },
        "session": exam["session"],
        "questions": exam["questions"],
        "warning": exam["warning"],
    })
    state.pop(f"practice_setup_{course_id}", None)


def open_saved_result(course_id):
    history = st.session_state.get(f"practice_history_{course_id}", {})
    record = history.get(st.session_state.get(f"saved_session_{course_id}"))
    if record is None:
        return
    st.session_state[f"active_practice_{course_id}"] = {
        "session": record["session"], "questions": record["questions"], "result": record["result"],
        "warning": None, "settings": {},
    }
    st.session_state.pop(f"practice_setup_{course_id}", None)


def resume_session(course_id, session_id):
    """Resume an unfinished session on its question screen, where the student left it."""
    resume_draft(st.session_state, course_id, session_id)
    st.session_state[f"active_practice_{course_id}"].pop("worksheet_step", None)
    st.session_state.pop(f"practice_setup_{course_id}", None)


def move_question(practice_key, step):
    """Previous / Next: one question, never out of range (a late click changes nothing)."""
    active = st.session_state.get(practice_key)
    if not active or "result" in active:
        return
    questions = active["questions"]
    current = max(0, min(active.get("worksheet_index", 0), len(questions) - 1))
    target = max(0, min(len(questions) - 1, current + step))
    if target == current:
        return
    active["worksheet_index"] = target
    # Read once by the next render: it names the page-turn (see paper_practice.css).
    active["worksheet_move"] = "next" if step > 0 else "prev"
    active["worksheet_turns"] = active.get("worksheet_turns", 0) + 1
    timer = active.get("focus_timer", {})
    if timer.get("since") is not None:
        focus_question(active, questions[target].id, time.monotonic())
    elif timer:
        timer["question_id"] = questions[target].id


def open_review(practice_key):
    active = st.session_state.get(practice_key)
    if active and "result" not in active:
        active["worksheet_step"] = "review"


def close_review(practice_key):
    active = st.session_state.get(practice_key)
    if active:
        active.pop("worksheet_step", None)


def toggle_side_panel(course_id):
    key = f"practice_side_panel_{course_id}"
    st.session_state[key] = not st.session_state.get(key, True)


def follow_question(active, question_id):
    """The focus timer follows the question on screen; a paused timer stays paused."""
    timer = active.get("focus_timer")
    if timer is None or (timer.get("since") is not None and timer.get("question_id") != question_id):
        focus_question(active, question_id, time.monotonic())
    elif timer.get("question_id") != question_id:
        timer["question_id"] = question_id


# ---- Screens ------------------------------------------------------------------------

def setup_heading():
    st.title(tr("Practice"))
    st.caption(tr("Choose a mode, then focus on one question at a time."))


def choose_topic(course_id, confirmed_topic_ids, topic_names):
    key = f"practice_topic_{course_id}"
    if len(confirmed_topic_ids) > TOPIC_PILLS_LIMIT:
        return st.selectbox(
            tr("Knowledge point"),
            options=confirmed_topic_ids,
            format_func=lambda value: topic_names[value],
            key=key,
        )
    # Clicking the chosen pill again would clear it; keep the last choice instead.
    last_key = f"practice_topic_last_{course_id}"
    chosen = st.session_state.get(key)
    if chosen in confirmed_topic_ids:
        st.session_state[last_key] = chosen
    else:
        last = st.session_state.get(last_key)
        st.session_state[key] = last if last in confirmed_topic_ids else confirmed_topic_ids[0]
    return st.pills(
        tr("Knowledge point"),
        options=confirmed_topic_ids,
        format_func=lambda value: topic_names[value],
        selection_mode="single",
        key=key,
    )


def render_setup_screen(course, confirmed_topic_ids, topic_names, active_practice, pending_entry):
    in_progress = active_practice is not None and "result" not in active_practice
    setup_heading()
    if pending_entry is not None:
        target = pending_entry.get("topic_id")
        st.info(
            (tr("New practice: ") + topic_names[target]) if target
            else tr("New practice for your confirmed topics.")
        )
    if in_progress or (pending_entry is not None and active_practice is not None):
        st.button(
            tr("Return to your session") if in_progress else tr("Return to previous session"),
            icon=":material/arrow_back:", key="practice_return_previous",
            on_click=return_to_session, args=(course.course_id,),
        )

    with st.container(border=True, key="practice_setup"):
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
        if mode == "topic":
            choose_topic(course.course_id, confirmed_topic_ids, topic_names)

        st.number_input(
            tr("Number of questions"),
            min_value=1,
            max_value=50,
            value=10,
            step=1,
            key=f"practice_count_{course.course_id}",
            width=240,
        )

        start_label = (
            "Start new practice"
            if active_practice is not None
            else "Start practice"
        )
        # A callback, so the next run already draws the new session's question screen.
        st.button(
            tr(start_label), type="primary", key=f"practice_start_{course.course_id}",
            on_click=start_practice, args=(course, confirmed_topic_ids),
        )
        if st.session_state.pop("practice_create_error", None):
            st.error(tr("Could not create practice. Try another topic or check your exam scope in Study Plan."))

    drafts = st.session_state.get(f"practice_drafts_{course.course_id}", {})
    if drafts:
        with st.expander(tr(f"Unfinished sessions ({len(drafts)})")):
            draft_id = st.selectbox(tr("Unfinished session"), list(drafts), format_func=lambda sid: practice_label(drafts, sid, unfinished=True), key=f"draft_choice_{course.course_id}")
            st.button(tr("Resume unfinished session"), key=f"resume_draft_{course.course_id}",
                on_click=resume_session, args=(course.course_id, draft_id))

    # Graded sessions saved for this course can be reopened.
    history = st.session_state.get(f"practice_history_{course.course_id}", {})
    if history:
        with st.expander(tr("Review a saved session")):
            st.selectbox(tr("Saved session"), list(history), format_func=lambda sid: practice_label(history, sid), key=f"saved_session_{course.course_id}")
            st.button(tr("Open saved result"), key=f"open_saved_result_{course.course_id}",
                on_click=open_saved_result, args=(course.course_id,))


def practice_title(session, question, topic_names):
    if session.mode == "mock":
        return tr(f"Practice · {tr('Mock Exam')}")
    return tr(f"Practice · {topic_names.get(question.topic_id, tr('Topic'))}")


def render_question_screen(course, active, topic_names):
    """One question of the session in progress, and only what answering it needs."""
    practice_key = f"active_practice_{course.course_id}"
    session, questions = active["session"], active["questions"]
    sid = session.session_id
    index = max(0, min(active.get("worksheet_index", 0), len(questions) - 1))
    question = questions[index]
    follow_question(active, question.id)

    radar_on = learning_radar.radar_enabled(course.course_id)
    user = current_user(st.session_state) if radar_on else None
    # The "I'm stuck" choices are only offered to signed-in users of demo courses.
    offer_stuck = radar_chart is not None and user is not None
    topic = next((topic for topic in course.topics if topic.id == question.topic_id), None)
    # Mock Exam keeps exam conditions: no notes, as there are no hints.
    notes = session.mode == "topic" and topic is not None
    has_panel = radar_on or notes
    panel_shown = has_panel and st.session_state.get(f"practice_side_panel_{course.course_id}", True)

    if panel_shown:
        paper, margin = st.columns([3, 1], gap="large")
    else:
        paper, margin = st.container(key="practice_main_full"), None

    with paper:
        with st.container(key="practice_title_row", horizontal=True, vertical_alignment="center"):
            st.title(practice_title(session, question, topic_names))
            with st.container(
                key="practice_title_tools", horizontal=True, width="content",
                vertical_alignment="center", gap="small",
            ):
                with st.popover(
                    tr("This session"), icon=":material/more_horiz:", type="tertiary",
                    key=f"practice_session_menu_{sid}",
                ):
                    st.button(
                        tr("Review and submit"), icon=":material/fact_check:", width="stretch",
                        key=f"worksheet_review_{sid}", on_click=open_review, args=(practice_key,),
                    )
                    st.button(
                        tr("Change settings"), icon=":material/tune:", width="stretch",
                        key=f"practice_change_settings_{sid}", on_click=open_setup,
                        args=(course.course_id, sid),
                    )
                if has_panel:
                    st.button(
                        tr("Hide side panel") if panel_shown else tr("Show side panel"),
                        icon=":material/right_panel_close:" if panel_shown else ":material/right_panel_open:",
                        type="tertiary", key=f"practice_side_panel_toggle_{course.course_id}",
                        on_click=toggle_side_panel, args=(course.course_id,),
                    )

        with st.container(key="flight_worksheet"):
            # One row above the question: counter · flight path · session clock (wraps on phones).
            with st.container(key="flight_practice_progress", horizontal=True, vertical_alignment="center"):
                with st.container(key="flight_progress_count", width="content"):
                    st.caption(tr("Question") + f" {index + 1:02} / {len(questions):02}")
                with st.container(key="flight_progress_track"):
                    stops = min(len(questions), 12)
                    current_stop = index * (stops - 1) // max(1, len(questions) - 1)
                    markers = "".join(
                        '<span class="flight-waypoint is-current">✈</span>' if step == current_stop
                        else '<span class="flight-waypoint"></span>'
                        for step in range(stops)
                    )
                    st.markdown(
                        f'<div class="flight-waypoints" aria-hidden="true">{markers}</div>',
                        unsafe_allow_html=True,
                    )
                with st.container(
                    key="flight_progress_clock", horizontal=True, width="content", vertical_alignment="center",
                    gap="xsmall",
                ):
                    start_focus_controls(active)

            if active.get("warning") and index == 0:
                st.caption(tr(active["warning"]))

            # The key names the last move and alternates a/b, so the stylesheet replays the
            # page-turn only when the question changes; any other rerun renders "none".
            move = active.pop("worksheet_move", None)
            turn_key = (
                f"practice_turn_{move}_{'ab'[active.get('worksheet_turns', 0) % 2]}_{sid}"
                if move in ("next", "prev") else f"practice_turn_none_{sid}"
            )
            display = display_question(course.course_id, question, st.session_state)
            hints = hints_for(question) if session.mode == "topic" else []
            state_key = hint_state_key(sid, question.id)
            shown = st.session_state.get(state_key, 0) if hints else 0
            with st.container(key=turn_key), st.container(key=f"practice_question_{question.id}"):
                render_question_heading(index + 1, display.question)
                if display.simplified:
                    st.caption(tr("Simplified wording"))
                    with st.expander(tr("Show original wording")):
                        st.write(question.question)
                        for option in question.options:
                            st.write(option)

                st.radio(
                    tr("Choose an answer"),
                    options=list(range(len(question.options))),
                    format_func=lambda option, options=display.options: (
                        f"{chr(ord('A') + option)}. {options[option]}"
                    ),
                    index=None,
                    width="stretch",
                    key=f"answer_{sid}_{question.id}",
                    on_change=remember_widget,
                    args=(st.session_state, course.course_id, sid, f"answer_{sid}_{question.id}"),
                )

                answer_controls(active, question, course.course_id)

                for number, hint in enumerate(hints[:shown], start=1):
                    st.info(tr(f"Hint {number} of {len(hints)}: {display_text(hint, st.session_state)}"))

            # Actions under the question: Previous · Hint · Learning Radar · Next (or Finish).
            with st.container(
                horizontal=True, horizontal_alignment="distribute",
                vertical_alignment="center", key=f"paper_actions_{question.id}",
            ):
                st.button(
                    tr("Previous"), icon=":material/arrow_back:", disabled=index == 0,
                    key=f"worksheet_previous_{sid}", on_click=move_question, args=(practice_key, -1),
                )
                if shown < len(hints) and st.button(
                    tr("Hint") if shown == 0 else tr("Next hint"), icon=":material/lightbulb:",
                    key=f"hint_button_{sid}_{question.id}",
                ):
                    st.session_state[state_key] = shown + 1
                    remember_widget(st.session_state, course.course_id, sid, state_key)
                    st.rerun()
                if offer_stuck:
                    with st.popover(
                        tr("Learning Radar"), icon=":material/radar:",
                        key=f"practice_radar_menu_{sid}_{question.id}",
                    ):
                        radar_chart.render_stuck_buttons(
                            st.session_state, course.course_id, question.topic_id, user.user_id,
                            key=f"practice_stuck_{sid}_{question.id}",
                        )
                if index == len(questions) - 1:
                    st.button(
                        tr("Finish"), icon=":material/flag:", type="primary",
                        key=f"worksheet_finish_{sid}", on_click=open_review, args=(practice_key,),
                    )
                else:
                    st.button(
                        tr("Next"), icon=":material/arrow_forward:", icon_position="right", type="primary",
                        key=f"worksheet_next_{sid}", on_click=move_question, args=(practice_key, 1),
                    )

    if margin is not None:
        with margin, st.container(key="flight_worksheet_margin"):
            if radar_on:
                st.subheader(tr("Learning Radar"))
                radar, _ = load_course_radar(st.session_state, course.course_id, user.user_id if user else None)
                if radar_chart is not None:
                    # Chart only: the count below already says when sample data is included.
                    radar_chart.render_radar_figure(
                        course, radar, focus_topic_id=question.topic_id, key="practice_radar",
                    )
                render_topic_radar(radar.topics.get(question.topic_id))
                if st.button(tr("Explore this topic"), key=f"worksheet_radar_{sid}"):
                    st.session_state[f"graph_pending_focus_{course.course_id}"] = question.topic_id
                    st.switch_page("pages/4_Knowledge_Graph.py")
                if notes:
                    st.divider()
            if notes:
                st.subheader(tr("Quick Notes"))
                st.caption(topic.name)
                st.write(display_text(topic.summary, st.session_state))


def render_review_step(course, active):
    """The check before submitting: every question counts, not only the one last on screen."""
    practice_key = f"active_practice_{course.course_id}"
    session, questions = active["session"], active["questions"]
    sid = session.session_id
    st.title(tr("Practice · Review"))
    answered = sum(st.session_state.get(f"answer_{sid}_{question.id}") is not None for question in questions)
    st.markdown(tr(f"{answered} of {len(questions)} answered"))
    checklist(active)
    with st.container(
        horizontal=True, horizontal_alignment="distribute",
        vertical_alignment="center", key="practice_review_actions",
    ):
        st.button(
            tr("Back to questions"), icon=":material/arrow_back:",
            key=f"worksheet_back_{sid}", on_click=close_review, args=(practice_key,),
        )
        st.button(
            tr("Submit answers"), type="primary", key=f"practice_submit_{sid}",
            on_click=submit_practice, args=(course, practice_key),
        )
    if st.session_state.pop("practice_submit_error", None):
        st.error(tr("Could not grade this practice. Please try again."))


def render_result_screen(course, active_practice, confirmed_topic_ids, topic_names):
    practice_key = f"active_practice_{course.course_id}"
    session = active_practice["session"]
    questions = active_practice["questions"]
    mode_name = "Mock Exam" if session.mode == "mock" else "Topic Practice"

    with st.container(key="practice_title_row", horizontal=True, vertical_alignment="center"):
        st.title(tr("Practice"))
        with st.container(key="practice_title_tools", horizontal=True, width="content", vertical_alignment="center"):
            st.button(
                tr("New practice"), icon=":material/add:", key=f"practice_new_{course.course_id}",
                on_click=open_setup, args=(course.course_id, session.session_id),
            )

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


# ---- Page ---------------------------------------------------------------------------

apply_app_styles()

course = st.session_state.get("current_course")

if course is None:
    setup_heading()
    st.info(tr("Load a course from the dashboard first."))
    st.page_link("pages/0_Dashboard.py", label=tr("Back to Dashboard"))
    st.stop()

confirmed_key = f"confirmed_scope_{course.course_id}"
confirmed_topic_ids = st.session_state.get(confirmed_key)

if not confirmed_topic_ids:
    setup_heading()
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
    setup_heading()
    st.error(tr("The confirmed scope is invalid. Confirm it again in Study Plan."))
    st.page_link("pages/1_Study_Hub.py", label=tr("Go to Study Plan"))
    st.stop()

practice_key = f"active_practice_{course.course_id}"
active_practice = st.session_state.get(practice_key)
pending_entry = st.session_state.get(f"practice_entry_{course.course_id}")
st.session_state.pop("priority_ready", None)

# app.py sets this flag when the student arrives from another page: the page then opens
# the session (or its result) again rather than a setup screen asked for earlier.
arrived = st.session_state.pop(f"rehydrate_practice_{course.course_id}", False)
setup_request_key = f"practice_setup_{course.course_id}"
setup_request = st.session_state.get(setup_request_key)
if setup_request is not None and (
    arrived or active_practice is None or setup_request != active_practice["session"].session_id
):
    st.session_state.pop(setup_request_key, None)
    setup_request = None

in_progress = active_practice is not None and "result" not in active_practice
if in_progress:
    # Answers, confidence and hints of questions that are not on screen live in the drafts.
    hydrate_widgets(st.session_state, active_practice, force=arrived)

if active_practice is None or pending_entry is not None or setup_request is not None:
    render_setup_screen(course, confirmed_topic_ids, topic_names, active_practice, pending_entry)
elif not in_progress:
    render_result_screen(course, active_practice, confirmed_topic_ids, topic_names)
elif active_practice.get("worksheet_step") == "review":
    render_review_step(course, active_practice)
else:
    render_question_screen(course, active_practice, topic_names)
