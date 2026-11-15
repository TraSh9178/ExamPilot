"""Presentation-only wording for practice questions.

The original Question is never changed: grading continues to use its option index.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections.abc import Mapping
from types import MappingProxyType

from models.schemas import Question
from services.i18n import tr, render_language_control


SIMPLIFY_KEY = "a11y_simplify"
BILINGUAL_KEY = "a11y_bilingual_zh"
_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "accessibility"
_PROTECTED = re.compile(r"(`[^`]*`|\$[^$]*\$|\\\([^)]*\\\))")


@dataclass(frozen=True)
class DisplayQuestion:
    question: str
    options: list[str]
    explanation: str
    simplified: bool


def render_accessibility_controls() -> None:
    """Render controls only when the host page invokes this function."""
    import streamlit as st

    st.subheader(tr("Accessibility"))
    st.toggle(tr("Simplified English"), key=SIMPLIFY_KEY)
    render_language_control()
    st.caption(tr("Interface language only; uploaded material and AI-generated answers retain their original language."))


def _read_mapping(filename: str) -> Mapping:
    # Keyed by the full path, so a different data directory is never served
    # from the cache.
    return _load_mapping(_DATA_DIR / filename)


@lru_cache(maxsize=None)
def _load_mapping(path: Path) -> Mapping:
    """Parse a data file once; callers get a read-only view of the cached dict."""
    if not path.is_file():
        return MappingProxyType({})
    with path.open("r", encoding="utf-8") as source:
        data = json.load(source)
    return MappingProxyType(data if isinstance(data, dict) else {})


def annotate_terms(text: str, glossary: dict[str, str]) -> str:
    """Annotate the first whole-word occurrence of each term outside code/math."""
    terms = [term for term in glossary if term and glossary[term]]
    if not terms:
        return text
    terms.sort(key=lambda term: (-len(term), term.casefold()))
    matcher = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)",
        re.IGNORECASE,
    )
    translations = {term.casefold(): translation for term, translation in glossary.items()}
    seen: set[str] = set()

    def annotate_segment(segment: str) -> str:
        def replace(match: re.Match[str]) -> str:
            value = match.group()
            key = value.casefold()
            translation = translations[key]
            # A previously annotated source must not acquire a second label.
            if key in seen or segment[match.end():].startswith(f" ({translation})"):
                seen.add(key)
                return value
            seen.add(key)
            return f"{value} ({translation})"

        return matcher.sub(replace, segment)

    parts = _PROTECTED.split(text)
    return "".join(
        part if _PROTECTED.fullmatch(part) else annotate_segment(part)
        for part in parts
    )


def display_text(text: str, session_state: Mapping[str, object]) -> str:
    if not session_state.get(BILINGUAL_KEY, False):
        return text
    return annotate_terms(text, _read_mapping("glossary_zh.json"))


def display_question(
    course_id: str, question: Question, session_state: Mapping[str, object]
) -> DisplayQuestion:
    """Use optional demo wording, falling back to the unchanged source question."""
    wording = None
    if session_state.get(SIMPLIFY_KEY, False):
        # Course IDs cannot turn the data path into an arbitrary file read.
        if course_id in {"econ101", "calculus-i-demo", "python-basics-demo"}:
            data = _read_mapping(f"simplified_{course_id}.json")
            wording = data.get("questions", {}).get(question.id)
    simplified = bool(
        isinstance(wording, dict)
        and isinstance(wording.get("question"), str)
        and isinstance(wording.get("explanation"), str)
        and isinstance(wording.get("options"), list)
        and len(wording["options"]) == 4
        and all(isinstance(option, str) for option in wording["options"])
    )
    source = wording if simplified else question
    return DisplayQuestion(
        question=display_text(source["question"] if simplified else source.question, session_state),
        options=[display_text(option, session_state) for option in (source["options"] if simplified else source.options)],
        explanation=display_text(source["explanation"] if simplified else source.explanation, session_state),
        simplified=simplified,
    )
