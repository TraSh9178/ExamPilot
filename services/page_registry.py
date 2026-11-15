"""Pages that are opened from a button on another page, not from the sidebar.

Secondary material (history, tools, exports, the answers behind an analysis)
gets a page of its own instead of an expander, so the page a student is on
stays about one thing.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file under the project root, English title, URL path). A page is registered
# only once its file exists, so each one can be added separately.
FOCUS_PAGES = (
    ("pages/14_Topic_Details.py", "Detailed explanation & examples", "Topic_Details"),
    ("pages/8_Practice_History.py", "Practice history", "Practice_History"),
    ("pages/9_Course_Tools.py", "Course tools", "Course_Tools"),
    ("pages/10_Topic_Summaries.py", "Topic summaries", "Topic_Summaries"),
    ("pages/11_Anki_Export.py", "Export to Anki", "Anki_Export"),
    ("pages/12_Learning_Evidence.py", "Answers behind Learning DNA", "Learning_Evidence"),
    ("pages/13_Answer_Review.py", "Review answers", "Answer_Review"),
)


def existing_focus_pages(root: Path | None = None) -> list[tuple[str, str, str]]:
    """The focus pages whose files are present, in registry order."""
    base = ROOT if root is None else root
    return [entry for entry in FOCUS_PAGES if (base / entry[0]).is_file()]
