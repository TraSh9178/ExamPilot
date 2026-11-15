"""Explicit cross-page intents; switching tools must not discard unfinished work."""
from copy import deepcopy

from services.question_editor import available_questions



def stage_practice(state, course, topic_id=None):
    confirmed=state.get(f'confirmed_scope_{course.course_id}', [])
    if topic_id is not None:
        if topic_id not in {t.id for t in course.topics} or topic_id not in confirmed:
            raise ValueError('Confirm this topic in Study Plan first.')
        state[f'practice_mode_{course.course_id}']='Topic Practice'
        state[f'practice_topic_{course.course_id}']=topic_id
    state[f'practice_entry_{course.course_id}']={'topic_id':topic_id}


def stage_topic_practice(state, course, topic_id):
    """Prepare practice for an explicitly chosen topic, even outside the exam scope."""
    if topic_id not in {topic.id for topic in course.topics} or not any(
        question.topic_id == topic_id for question in available_questions(course)
    ):
        return False
    if topic_id in (state.get(f"confirmed_scope_{course.course_id}") or []):
        stage_practice(state, course, topic_id)
    else:
        state[f"practice_entry_{course.course_id}"] = {"topic_id": topic_id, "focused": True}
    return True


def install_practice(state, course_id, practice):
    key=f'active_practice_{course_id}'
    old=state.get(key)
    if old and 'result' not in old:
        sid=old['session'].session_id
        archived=deepcopy(old)
        if archived.get('focus_timer'):
            archived['focus_timer']['since']=None
        archived['_draft_widgets']={**archived.get('_draft_widgets', {}), **{k:state[k] for q in old['questions']
            for k in (f'answer_{sid}_{q.id}',f'confidence_{sid}_{q.id}',f'hints_shown_{sid}_{q.id}') if k in state}}
        state.setdefault(f'practice_drafts_{course_id}',{})[sid]=archived
    state[key]=practice
    state.pop(f'practice_entry_{course_id}',None)


def resume_draft(state, course_id, sid):
    drafts=state.get(f'practice_drafts_{course_id}',{})
    draft=deepcopy(drafts.pop(sid))
    widgets=draft.get('_draft_widgets',{})
    install_practice(state,course_id,draft)
    state.update(widgets)


def open_lab(state, course_id, topic_id):
    if course_id!='calculus-i-demo' or topic_id not in {'calc_limits','calc_derivatives'}:
        raise ValueError('No experiment is available for this topic.')
    state[f'concept_lab_topic_{course_id}']=topic_id


def remember_widget(state, course_id, session_id, widget_key):
    active = state.get(f'active_practice_{course_id}')
    if active and active['session'].session_id == session_id and 'result' not in active:
        active.setdefault('_draft_widgets', {})[widget_key] = state.get(widget_key)


def hydrate_widgets(state, active, force=False):
    for key, value in active.get('_draft_widgets', {}).items():
        if force or key not in state:
            state[key] = value
