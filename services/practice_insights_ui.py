"""Practice-time controls and post-session reflection; grades remain unchanged."""

from services.i18n import tr
import time
from copy import deepcopy

import streamlit as st

from services.practice_insights import (CONFIDENCE, REASONS, ResponseInsight, analytics,
    before_submit, focus_question, session_insights, set_session_insights, settle_focus, transfer_session, priority_session)
from services.hints import hint_state_key
from services.course_state import save_course
from services.account_sync import save_course_with_history
from services.ai_service import generation_available, check_explanation
from services.learning_flow import remember_widget, install_practice


# Save failures never show the stored reason; the student only needs to know the outcome.
REFLECTION_NOT_SAVED = "Couldn't save your reflection. Your score is unchanged."
ACCOUNT_NOT_SAVED = "Couldn't save to your account. Your work is kept on this device for now."
NOTES_NOT_SAVED = "Your answers were graded, but your practice notes couldn't be saved."
CONFIRM_TOPIC = 'Confirm this topic in Study Plan first.'


def save_rows(course, sid, rows):
    try:
        updated = set_session_insights(course, sid, rows)
    except ValueError:
        st.error(tr(REFLECTION_NOT_SAVED))
        return None
    save_course(st.session_state, updated)
    outcome = save_course_with_history(st.session_state, updated)
    if outcome is not None and not outcome.success:
        st.warning(tr(ACCOUNT_NOT_SAVED))
    return updated


def start_focus_controls(active):
    now = time.monotonic()
    if 'focus_timer' not in active:
        focus_question(active, active['questions'][0].id, now)
    settle_focus(active, now)
    with st.expander(tr('About focus time')):
        st.caption(tr('Focus time is an estimate for the selected question, capped at 120 seconds between interactions. Pause when taking a break; it does not measure attention.'))
    timer = active['focus_timer']
    if st.button(tr('Resume focus timer') if timer['since'] is None else tr('Pause focus timer'), key=f"focus_pause_{active['session'].session_id}"):
        if timer['since'] is None:
            timer['since'] = now
        else:
            settle_focus(active, now)
            timer['since'] = None
        st.rerun()


def answer_controls(active, question, course_id):
    sid = active['session'].session_id
    if st.button(tr('Work on this question'), key=f'focus_{sid}_{question.id}'):
        focus_question(active, question.id, time.monotonic())
        st.rerun()
    # One click records confidence; no selection (None) means "not recorded".
    key = f'confidence_{sid}_{question.id}'
    st.segmented_control(tr('How confident are you?'), [value for value in CONFIDENCE if value is not None],
        format_func=lambda value: tr(CONFIDENCE[value]), key=key,
        on_change=remember_widget, args=(st.session_state, course_id, sid, key))


def checklist(active):
    sid = active['session'].session_id
    rows = before_submit(active['questions'],
        {q.id:st.session_state.get(f'answer_{sid}_{q.id}') for q in active['questions']},
        {q.id:st.session_state.get(f'confidence_{sid}_{q.id}') for q in active['questions']})
    st.subheader(tr('Review before submit'))
    if rows:
        st.dataframe([{tr(key): ', '.join(tr(flag.strip()) for flag in value.split(',')) if key == 'Check' else value for key, value in row.items()} for row in rows], hide_index=True, width='stretch')
        st.caption(tr('You can change these answers above or submit them as they are.'))
    else:
        st.caption(tr('No unanswered, unsure or guessed answers to review.'))


def capture_submission(course, active):
    settle_focus(active, time.monotonic())
    sid = active['session'].session_id
    rows = {}
    for q in active['questions']:
        rows[q.id] = ResponseInsight(
            confidence=st.session_state.get(f'confidence_{sid}_{q.id}'),
            hints_used=st.session_state.get(hint_state_key(sid,q.id),0),
            focus_seconds=active.get('focus_seconds',{}).get(q.id),
        ).model_dump(mode='json')
    try:
        updated = set_session_insights(course, sid, rows)
    except ValueError:
        st.session_state['insights_capture_error'] = True
        return course
    save_course(st.session_state, updated)
    return updated


def result_overview(course, session, questions, result):
    if st.session_state.pop('insights_capture_error', False):
        st.warning(tr(NOTES_NOT_SAVED))
    rows = session_insights(course, session.session_id)
    data = analytics(questions, result['attempts'], rows)
    st.subheader(tr('Practice insights'))
    guesses = len(data['correct_guesses'])
    if guesses == 1:
        st.info(tr('1 correct answer was marked Guessed. Revisit it before treating it as secure knowledge.'))
    elif guesses:
        st.info(tr(f"{guesses} correct answers were marked Guessed. Revisit them before treating them as secure knowledge."))
    if data['topic_seconds']:
        names={t.id:t.name for t in course.topics}
        with st.expander(tr('Time breakdown')):
            st.markdown(tr('**Tracked focus time by topic**'))
            st.dataframe([{tr('Topic'):names.get(t,tr('Topic')),tr('Tracked seconds'):round(seconds,1)}
                for t,seconds in sorted(data['topic_seconds'].items(),key=lambda p:-p[1])],hide_index=True,width='stretch')
            slowest=max(questions,key=lambda q:rows.get(q.id,{}).get('focus_seconds') or 0)
            st.caption(tr('Longest tracked question: ') + slowest.question)
    render_priorities(course, data['priorities'])


def launch_priority(course, priorities):
    try:
        install_practice(st.session_state, course.course_id, priority_session(
            course, priorities, st.session_state.get(f"confirmed_scope_{course.course_id}", []),
        ))
    except ValueError as error:
        st.session_state["priority_launch_error"] = str(error)
    else:
        st.session_state["priority_ready"] = True


def render_priorities(course, priorities):
    st.markdown(tr('**Smart review list**'))
    if priorities:
        st.caption(tr('1 question could benefit from another look.') if len(priorities) == 1
                   else tr(f"{len(priorities)} questions could benefit from another look."))
        with st.expander(tr("Why this review order")):
            st.caption(tr('Priority uses incorrect/unanswered responses, confidence, hints and relative tracked time. It is a transparent practice suggestion, not a diagnosis.'))
            names={t.id:t.name for t in course.topics}
            st.dataframe([{tr('Rank'):i,tr('Topic'):names.get(r['topic_id'],tr('Topic')),
                           tr('Question'):r['question'],tr('Why review'):', '.join(tr(reason) for reason in r['reasons'])}
                          for i,r in enumerate(priorities,1)],hide_index=True,width='stretch')
        st.button(tr('Practise review priorities'), key=f'priorities_{course.course_id}',
            on_click=launch_priority, args=(course, priorities))
        if error := st.session_state.pop('priority_launch_error', None):
            st.info(tr(error))
        if st.session_state.pop('priority_ready', False):
            st.switch_page('pages/2_Practice_Center.py')

    else:
        st.caption(tr('No review priorities from the available evidence yet.'))


def launch_transfer(course, question, session, confirmed, practice_key):
    try:
        install_practice(st.session_state, course.course_id, transfer_session(course, question, session, confirmed))
    except ValueError as error:
        # Only the scope message asks the student to act; any other reason means no match yet.
        st.session_state['transfer_launch_error'] = CONFIRM_TOPIC if str(error) == CONFIRM_TOPIC else 'No similar question yet.'


def evidence_line(saved):
    """One short line such as "Sure · 1 hint · 42 s"; unrecorded parts are left out."""
    parts = []
    if saved.confidence is not None:
        parts.append(tr(CONFIDENCE[saved.confidence]))
    if saved.hints_used is not None:
        hints = saved.hints_used
        parts.append(tr('No hints') if hints == 0 else tr('1 hint') if hints == 1 else tr(f'{hints} hints'))
    if saved.focus_seconds is not None:
        parts.append(tr(f'{round(saved.focus_seconds)} s'))
    return ' · '.join(parts)


def reflection_controls(course, session, question, review, confirmed, practice_key):
    sid=session.session_id
    rows=deepcopy(session_insights(course,sid))
    saved=ResponseInsight.model_validate(rows.get(question.id,{}))
    if line := evidence_line(saved):
        st.caption(line)
    with st.expander(tr('Reflect and explain your answer')):
        st.caption(tr('Write your reasoning in your own words. This reflection is after feedback and never changes your score.'))
        with st.form(f'reflection_{sid}_{question.id}'):
            reason=saved.mistake_reason
            if not review['is_correct']:
                # No pill selected (None) keeps the reason "not recorded".
                reason=st.pills(tr('Why did you miss this question?'),[v for v in REASONS if v is not None],
                    default=reason,format_func=lambda v:tr(REASONS[v]),
                    key=f'reason_{sid}_{question.id}')
            text=st.text_area(tr('Explain your answer'),value=saved.explanation,max_chars=4000,
                key=f'explain_{sid}_{question.id}')
            save=st.form_submit_button(tr('Save reflection'))
            ai=st.form_submit_button(tr('Check explanation with AI'),disabled=not generation_available())
        if not generation_available():
            st.caption(tr('AI checking is not configured. You can still write and save your explanation.'))
        else:
            st.caption(tr('AI checking sends this explanation and question to the configured Claude service. Its feedback may be wrong; verify it against your material.'))
        if save or ai:
            row=saved.model_copy(update={'mistake_reason':reason,'explanation':text})
            if text != saved.checked_explanation:
                row.feedback=None
                row.checked_explanation=None
            if ai:
                with st.spinner(tr('Checking your reasoning…')):
                    response=check_explanation(question, text)
                if response['ok']:
                    from services.practice_insights import ExplanationFeedback
                    row.feedback=ExplanationFeedback.model_validate(response['feedback'])
                    row.checked_explanation=text
                else:
                    st.error(tr(response['message']))
            rows[question.id]=row.model_dump(mode='json')
            updated = save_rows(course,sid,rows)
            if updated is not None:
                st.success(tr('Saved.'))
                saved=row
        if saved.feedback is not None and saved.checked_explanation==saved.explanation:
            st.markdown(tr('**AI reasoning feedback — not a grade**'))
            st.write(tr(saved.feedback.verdict.replace('_',' ').capitalize()))
            st.write(saved.feedback.reasoning)
            st.write(saved.feedback.next_step)
    if not review['is_correct']:
        st.button(tr('Try a different structure'), key=f'transfer_{sid}_{question.id}',
            on_click=launch_transfer, args=(course, question, session, confirmed, practice_key))
        if error := st.session_state.pop('transfer_launch_error', None):
            st.info(tr(error))


def render_history_insights(course, history, mode):
    if not history: return
    ordered=list(course.learning_state.get('session_order',[]))
    ordered.extend(sid for sid in history if sid not in ordered)
    latest={}
    from services.practice_insights import family_id
    by_id={q.id:q for q in course.questions}
    for record in history.values():
        by_id.update({q.id:q for q in record['questions']})
    for sid in ordered:
        record=history.get(sid)
        if not record or record['session'].mode!=mode: continue
        for attempt in record['attempts']:
            q=by_id[attempt.question_id]
            latest[(q.topic_id,family_id(q,by_id))]=(q,attempt,session_insights(course,sid).get(q.id,{}))
    total_seconds={}
    names={t.id:t.name for t in course.topics}
    for sid,record in history.items():
        if record['session'].mode != mode:continue
        for q in record['questions']:
            seconds=session_insights(course,sid).get(q.id,{}).get('focus_seconds')
            if seconds is not None:total_seconds[q.topic_id]=total_seconds.get(q.topic_id,0.0)+seconds
    if total_seconds:
        with st.expander(tr('Time by topic')):
            st.subheader(tr('Tracked focus time by topic'))
            st.caption(tr('Totals across recorded sessions in this mode; missing time is not treated as zero.'))
            st.dataframe([{tr('Topic'):names.get(t,tr('Topic')),tr('Tracked seconds'):round(seconds,1)}
                for t,seconds in sorted(total_seconds.items(),key=lambda p:-p[1])],hide_index=True,width='stretch')
    qs=[value[0] for value in latest.values()]
    attempts=[value[1] for value in latest.values()]
    rows={q.id:r for q,a,r in latest.values()}
    data=analytics(qs,attempts,rows)
    st.subheader(tr('Your next review'))
    render_priorities(course,data['priorities'])
