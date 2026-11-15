"""The Anki download, shown on its own page (pages/11_Anki_Export.py).

Moved here unchanged from the Flashcards page's former expander: the same
choices, session keys, messages, file name, MIME type and TSV bytes.
"""
import csv
import re
from io import StringIO

import streamlit as st

from services.anki_export_service import export_anki_tsv, get_weak_topic_ids
from services.flashcards import practice_topic_stats
from services.i18n import tr


def safe_filename(course_name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", course_name.strip())
    token = token.strip("_-").lower()[:80]
    return f"anki_{token or 'course'}.tsv"


def render_anki_export(course, history) -> None:
    """Instructions, the scope choice and the download; problems are messages here."""
    st.write(tr("Download the file, then in Anki on your computer choose File → Import and match Front, Back and Tags. Cards are not sent to AnkiWeb automatically."))
    export_scope = st.radio(
        tr("Questions to export"),
        options=[tr("All Questions"), tr("Weak Topics")],
        key=f"anki_export_scope_{course.course_id}",
        horizontal=True,
        width="stretch",
    )

    topic_ids = None
    if export_scope == tr("Weak Topics"):
        mode_label = st.radio(
            tr("Practice mode"),
            options=[tr("Mock Exam"), tr("Topic Practice")],
            key=f"anki_export_mode_{course.course_id}",
            horizontal=True,
            width="stretch",
        )
        mode = "mock" if mode_label == tr("Mock Exam") else "topic"
        try:
            stats = practice_topic_stats(course, history)
        except ValueError:
            st.error(tr("Couldn't find your weak topics from this practice history."))
            return
        topic_ids = get_weak_topic_ids(stats, mode)
        if not topic_ids:
            st.info(tr("No weak or developing topics in this practice mode."))
            return
        if not any(question.topic_id in topic_ids for question in course.questions):
            st.info(tr("No questions match the weak or developing topics."))
            return

    content = export_anki_tsv(course, topic_ids=topic_ids)
    if not content:
        st.info(tr("No questions match the selected export."))
        return

    rows = list(csv.reader(StringIO(content), delimiter="\t"))
    st.caption(tr(f"{len(rows)} cards · {export_scope}"))
    st.download_button(
        tr("Download Anki TSV"),
        data=content.encode("utf-8"),
        file_name=safe_filename(course.course_name),
        mime="text/tab-separated-values; charset=utf-8",
        icon=":material/download:",
    )
