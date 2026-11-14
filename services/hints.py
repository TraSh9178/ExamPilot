import json
import re
from functools import cache
from pathlib import Path

MAX_HINTS = 3
_DEMO_HINTS_PATH = Path(__file__).resolve().parents[1] / "data" / "hints" / "demo_hints.json"


@cache
def _demo_hints() -> dict[str, list[str]]:
    return json.loads(_DEMO_HINTS_PATH.read_text(encoding="utf-8"))


def hints_for(question) -> list[str]:
    """Return the first available set of hints for the question."""
    if attached_hints := getattr(question, "hints", None):
        return list(attached_hints)

    demo_hints = _demo_hints()
    return list(
        demo_hints.get(question.id)
        or demo_hints.get(getattr(question, "version_of", None))
        or []
    )


def validate_hints(hints: list[str], correct_option: str) -> None:
    """Reject too many hints, blank hints or a hint containing the answer."""
    if len(hints) > MAX_HINTS:
        raise ValueError(f"At most {MAX_HINTS} hints are allowed.")
    if any(not hint.strip() for hint in hints):
        raise ValueError("Hints cannot be blank.")

    answer = correct_option.strip()
    if len(answer) >= 3:
        whole_answer = re.compile(rf"(?<!\w){re.escape(answer)}(?!\w)", re.IGNORECASE)
        if any(whole_answer.search(hint) for hint in hints):
            raise ValueError("A hint contains the correct option.")


def hint_state_key(session_id: str, question_id: str) -> str:
    return f"hints_shown_{session_id}_{question_id}"
