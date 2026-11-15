"""Explicit append-only demo updates; never replace a learner's saved content."""
from pathlib import Path
from copy import deepcopy
from models.schemas import StudyPackage
from services.question_review import normalized_text

FILES={'econ101':'sample_course.json','calculus-i-demo':'calculus_i_demo.json','python-basics-demo':'demo_python_basics.json'}


def demo_update(course):
    filename=FILES.get(course.course_id)
    if not filename:return course,0
    latest=StudyPackage.model_validate_json((Path(__file__).resolve().parents[1]/'data'/filename).read_text(encoding='utf-8'))
    known={q.id for q in course.questions}
    stems={normalized_text(q.question) for q in course.questions}
    topics={t.id for t in course.topics}
    # Topic expansion belongs only to the calculus demo. Keep saved summaries,
    # relationships, questions and learner scope, including custom additions.
    new_topics=[t for t in latest.topics if t.id not in topics] if course.course_id=='calculus-i-demo' else []
    topics.update(t.id for t in new_topics)
    added=[q for q in latest.questions if q.id not in known and q.topic_id in topics and normalized_text(q.question) not in stems]
    edges={(r.from_topic,r.to_topic,r.type) for r in course.relationships}
    new_edges=[r for r in latest.relationships if (r.from_topic,r.to_topic,r.type) not in edges] if course.course_id=='calculus-i-demo' else []
    if not added and not new_topics and not new_edges:return course,0
    data=course.model_dump(mode='json')
    data['topics'].extend(t.model_dump(mode='json') for t in new_topics)
    data['relationships'].extend(r.model_dump(mode='json') for r in new_edges)
    data['questions'].extend(q.model_dump(mode='json') for q in added)
    metadata=deepcopy(course.learning_state)
    if added:
        reviews=metadata.setdefault('question_reviews',{})
        for q in added:reviews[q.id]='pending'
    data['learning_state']=metadata
    return StudyPackage.model_validate(data),len(added)


def sync_demo_catalog(state):
    """Give every session the current built-in catalog, preserving learner work.

    Run after account restoration so saved legacy packages cannot hide new
    topics. This adds content locally; normal account saves persist it later.
    """
    from services.course_state import initialize_courses
    initialize_courses(state)
    courses = list(state['courses'])
    current = state.get('current_course')
    by_id = {course.course_id: index for index, course in enumerate(courses)}
    if current is not None:
        if current.course_id in by_id:
            courses[by_id[current.course_id]] = current
        else:
            by_id[current.course_id] = len(courses)
            courses.append(current)
    for course_id, filename in FILES.items():
        if course_id in by_id:
            index = by_id[course_id]
            courses[index], _ = demo_update(courses[index])
        else:
            package = StudyPackage.model_validate_json(
                (Path(__file__).resolve().parents[1]/'data'/filename).read_text(encoding='utf-8'))
            by_id[course_id] = len(courses)
            courses.append(package)
    state['courses'] = courses
    if current is not None and current.course_id in by_id:
        state['current_course'] = courses[by_id[current.course_id]]

    # Retain compatibility with older sessions; these markers no longer gate updates.
    state['default_demo_courses_loaded'] = True
    state['default_demo_courses_v3_loaded'] = True
