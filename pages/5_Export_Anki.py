"""Flashcards: review one card at a time; the Anki export opens on its own page."""
from services.ui_help import help_heading
from html import escape

import streamlit as st

from components.page_links import open_page_button
from services.flashcards import (
    DECK_LABELS,
    Flashcard,
    answer_text,
    build_decks,
    default_deck,
    option_letter,
)
from services.i18n import tr
from services.question_editor import available_questions
from services.ui_style import apply_app_styles


def _text(text: str) -> str:
    """Escaped course text; line breaks kept for code questions."""
    return "<br>".join(escape(line, quote=False) for line in text.splitlines())


def _step(state_key: str, delta: int, size: int) -> None:
    """Move one card; Next on the last card starts over at card 1."""
    state = st.session_state[state_key]
    index = max(0, min(state["index"], size - 1))
    if delta > 0:
        target = 0 if index >= size - 1 else index + 1
    elif index == 0:
        return  # Already on the first card; a late click changes nothing.
    else:
        target = index - 1
    state.update(
        index=target,
        side="front",
        move="next" if delta > 0 else "prev",
        step=state["step"] + 1,
    )


def _flip(state_key: str) -> None:
    state = st.session_state[state_key]
    state.update(
        side="back" if state["side"] == "front" else "front",
        move="flip",
        step=state["step"] + 1,
    )


def _render_question(card: Flashcard, side: str) -> None:
    question = card.question
    if side == "front":
        options = "".join(
            f'<div class="flashcard-option">{option_letter(index)}. {_text(option)}</div>'
            for index, option in enumerate(question.options)
        )
        st.markdown(
            f'<div class="flashcard-heading" role="heading" aria-level="3">{_text(question.question)}</div>'
            f'<div class="flashcard-options">{options}</div>',
            unsafe_allow_html=True,
        )
        return

    note = ""
    if card.mistake:
        last = (
            tr("Last time you left this blank.")
            if card.last_choice is None
            else tr(f"Last time you chose {option_letter(card.last_choice)}.")
        )
        note = f'<div class="flashcard-last">{escape(last)}</div>'
    st.markdown(
        f'<div class="flashcard-recap">{_text(question.question)}</div>'
        f'<div class="flashcard-label">{escape(tr("Answer"))}</div>'
        f'<div class="flashcard-answer"><strong>{_text(answer_text(question))}</strong></div>'
        f"{note}"
        f'<div class="flashcard-explanation">{_text(question.explanation)}</div>',
        unsafe_allow_html=True,
    )


def _render_idea(card: Flashcard, side: str) -> None:
    if side == "front":
        st.markdown(
            f'<div class="flashcard-eyebrow">{escape(tr("Key idea"))}</div>'
            f'<div class="flashcard-heading" role="heading" aria-level="3">{_text(card.topic_name)}</div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        f'<div class="flashcard-recap">{_text(card.topic_name)}</div>'
        f'<div class="flashcard-summary">{_text(card.summary)}</div>',
        unsafe_allow_html=True,
    )


apply_app_styles()

help_heading(tr("Flashcards"), tr("One card at a time, from your mistakes, weak topics and key ideas.") + "\n\n" + tr("Think of your answer first, then flip the card.") + " " + tr("Recall what you know about this idea, then flip the card."), level='title')

course = st.session_state.get("current_course")

if course is None:
    st.info(tr("Load a course from the dashboard first."))
    st.stop()

if not available_questions(course):
    st.info(tr("This course has no questions to review yet."))
    st.stop()

history = st.session_state.get(f"practice_history_{course.course_id}", {})
decks = build_decks(course, history)

state_key = f"flashcards_{course.course_id}"
deck_key = f"flashcards_deck_{course.course_id}"
state = st.session_state.setdefault(state_key, {})
for name, value in (
    ("deck", None), ("picked", False), ("index", 0), ("side", "front"), ("step", 0), ("move", "none"),
):
    state.setdefault(name, value)

# The deck choice is cleared when another page runs, so its absence means the
# page has just been opened: show the card without replaying the last move.
if deck_key not in st.session_state:
    state["move"] = "none"
chosen = st.session_state.get(deck_key)
if chosen in decks and chosen != state["deck"]:
    # A click on another deck starts it at card 1.
    state.update(deck=chosen, picked=True, index=0, side="front", move="none")
elif state["deck"] not in decks or not state["picked"]:
    # Until a deck is picked, follow the default as practice history grows.
    deck = default_deck(decks)
    if deck != state["deck"]:
        state.update(deck=deck, picked=False, index=0, side="front", move="none")
# The control always shows the deck in use: clicking the chosen deck again
# would clear it, and the labels change with the counts and the language.
st.session_state[deck_key] = state["deck"]
deck_labels = {key: f"{tr(DECK_LABELS[key])} · {len(deck)}" for key, deck in decks.items()}
st.pills(
    tr("Cards to review"),
    options=list(decks),
    format_func=deck_labels.__getitem__,
    selection_mode="single",
    key=deck_key,
    label_visibility="collapsed",
)
if not history:
    st.caption(tr("After some practice, your mistakes will appear here as their own deck."))

cards = decks[state["deck"]]
# Deck sizes change as practice history changes; stay in range.
state["index"] = index = max(0, min(int(state["index"]), len(cards) - 1))
card = cards[index]
if state["side"] not in ("front", "back") or state.get("card") != card.ident:
    # A card that was not on screen in the last run always starts on its front.
    state["side"] = "front"
state["card"] = card.ident
side = state["side"]

# The key names the last move and alternates a/b, so the stylesheet can replay
# the page-turn or flip on every move (see assets/paper_flashcards.css).
move = state["move"] if state["move"] in ("next", "prev", "flip") else "none"
card_key = (
    f"flashcard_none_{course.course_id}"
    if move == "none"
    else f"flashcard_{move}_{'ab'[state['step'] % 2]}_{course.course_id}"
)
with st.container(border=True, key=card_key):
    position = f"Card {index + 1} of {len(cards)}"
    if card.kind == "idea":
        st.caption(tr(position))
        _render_idea(card, side)
    else:
        # A question whose topic has no name gets the plain position line.
        st.caption(tr(f"{position} · {card.topic_name}" if card.topic_name else position))
        _render_question(card, side)

last = index == len(cards) - 1
with st.container(
    horizontal=True,
    horizontal_alignment="distribute",
    vertical_alignment="center",
    key=f"flashcards_actions_{course.course_id}",
):
    st.button(
        tr("Previous card"),
        icon=":material/arrow_back:",
        disabled=index == 0,
        key=f"flashcards_previous_{course.course_id}",
        on_click=_step,
        args=(state_key, -1, len(cards)),
    )
    st.button(
        tr("Show answer") if side == "front" else tr("Show question"),
        icon=":material/flip:",
        type="primary",
        key=f"flashcards_flip_{course.course_id}",
        on_click=_flip,
        args=(state_key,),
    )
    st.button(
        tr("Start over") if last else tr("Next card"),
        icon=":material/restart_alt:" if last else ":material/arrow_forward:",
        icon_position="left" if last else "right",
        key=f"flashcards_next_{course.course_id}",
        on_click=_step,
        args=(state_key, 1, len(cards)),
    )

# The Anki download is secondary: a small button on the right edge opens it.
open_page_button(
    tr("Export to Anki"),
    "pages/11_Anki_Export.py",
    key=f"flashcards_open_export_{course.course_id}",
    icon=":material/download:",
    align="right",
)
