"""Static checks for the floating Pilot front-end script."""

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "assets" / "tutor_assistant.js"


def test_translation_helper_is_declared_only_once() -> None:
    # `text(english, chinese)` picks the interface language. A second `text`
    # declaration inside a block hides the helper for that whole block, so a
    # `text(...)` call above it throws and the assistant never mounts.
    source = SCRIPT.read_text(encoding="utf-8")

    declarations = re.findall(r"\b(?:const|let|var)\s+text\b", source)

    assert len(declarations) == 1
