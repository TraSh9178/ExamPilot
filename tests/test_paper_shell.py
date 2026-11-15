"""Paper shell: sidebar navigation, brand, stylesheet loading and decorations."""

import base64
from pathlib import Path
import re

import streamlit as st
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

from services import ui_style
from tests.auth_helpers import signed_in_app


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
ASSETS = ROOT / "assets"
RADAR_PAGE = ROOT / "pages" / "7_Learning_Radar.py"
SIDEBAR_CONTROLS = ("stSidebar", "stSidebarCollapseButton", "stExpandSidebarButton")


def expected_sidebar_titles() -> list[str]:
    titles = ["Home", "Study Plan", "Practice", "Progress", "Knowledge Map"]
    if RADAR_PAGE.exists():
        titles.append("Learning Radar")
    return [*titles, "Concept Lab", "Export to Anki"]


def record_calls(monkeypatch, name: str) -> list[tuple[tuple, dict]]:
    """Wrap a Streamlit command so a test can read its arguments."""
    calls = []
    original = getattr(st, name)

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(st, name, spy)
    return calls


def sidebar_navigation(monkeypatch, app: AppTest | None = None):
    """Run the signed-in app and return (visible pages, hidden pages, position)."""
    calls = record_calls(monkeypatch, "navigation")
    app = (app or signed_in_app(APP_PATH)).run()
    assert not app.exception
    (pages,), kwargs = calls[-1]
    visible = [page for page in pages if page.visibility == "visible"]
    hidden = [page for page in pages if page.visibility == "hidden"]
    return visible, hidden, kwargs.get("position", "sidebar")


def block_ids(node) -> list[str]:
    ids = []
    for child in node.children.values():
        if isinstance(child, Block):
            if child.proto is not None and getattr(child.proto, "id", ""):
                ids.append(child.proto.id)
            ids += block_ids(child)
    return ids


def block_types(node) -> list[str]:
    types = []
    for child in node.children.values():
        if isinstance(child, Block):
            types.append(child.type)
            types += block_types(child)
    return types


def injected_styles() -> str:
    def script():
        from services.ui_style import apply_app_styles

        apply_app_styles()

    app = AppTest.from_function(script).run()
    assert not app.exception
    return "\n".join(item.value for item in app.markdown if "<style>" in item.value)


def css_rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return [
        (selector.strip(), body)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def test_sidebar_lists_pages_in_study_order(monkeypatch):
    visible, hidden, position = sidebar_navigation(monkeypatch)

    assert position == "sidebar"
    assert [page.title for page in visible] == expected_sidebar_titles()
    assert visible[0]._default
    assert [(page.title, page.url_path) for page in hidden] == [("My account", "account")]
    if RADAR_PAGE.exists():
        radar = next(page for page in visible if page.title == "Learning Radar")
        assert radar.icon == ":material/radar:"


def test_learning_radar_is_left_out_until_its_page_file_exists(monkeypatch):
    original_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists",
        lambda path: False if path.name == RADAR_PAGE.name else original_exists(path),
    )

    visible, _, _ = sidebar_navigation(monkeypatch)

    assert "Learning Radar" not in [page.title for page in visible]
    assert [page.title for page in visible][-2:] == ["Concept Lab", "Export to Anki"]


def test_sidebar_titles_follow_the_interface_language(monkeypatch):
    calls = record_calls(monkeypatch, "navigation")
    app = signed_in_app(APP_PATH).run()
    next(item for item in app.sidebar.toggle if item.key == "_ui_chinese_toggle").set_value(True).run()

    assert not app.exception
    (pages,), _ = calls[-1]
    titles = [page.title for page in pages if page.visibility == "visible"]
    assert titles[:3] == ["首页", "学习计划", "练习"]
    assert titles[-1] == "导出到 Anki"


def test_brand_logo_and_responsive_sidebar_are_configured(monkeypatch):
    logos = record_calls(monkeypatch, "logo")
    page_configs = record_calls(monkeypatch, "set_page_config")

    app = signed_in_app(APP_PATH).run()

    assert not app.exception
    (image,), options = logos[-1]
    assert Path(image) == ASSETS / "brand-logo.svg"
    assert Path(options["icon_image"]) == ASSETS / "brand-plane.svg"
    assert options["size"] == "large"
    assert page_configs[0][1]["initial_sidebar_state"] == "auto"
    for name in ("brand-logo.svg", "brand-plane.svg"):
        assert (ASSETS / name).read_text(encoding="utf-8").lstrip().startswith("<svg")


def test_top_header_row_is_gone_and_breadcrumb_stays():
    from tests.test_learning_flow_ux import calculus

    app = signed_in_app(APP_PATH)
    app.session_state["current_course"] = calculus()
    app.run()

    assert not app.exception
    main_ids = block_ids(app.main)
    assert not any(block.endswith("-flight_header") for block in main_ids)
    assert "popover" not in block_types(app.main)
    assert not [box for box in app.main.selectbox if (box.key or "").startswith("flight_review")]
    assert not [link for link in app.main.get("page_link") if link.proto.label in {"Home", "Practice"}]
    assert any(block.endswith("-flight_course_context") for block in main_ids)
    assert "Calculus I Demo  /  Home" in [caption.value for caption in app.main.caption]


def test_sidebar_footer_holds_account_status_and_accessibility():
    app = signed_in_app(APP_PATH).run()

    assert not app.exception
    footer = [block for block in block_ids(app.sidebar) if block.endswith("-sidebar_footer")]
    assert footer
    order = [
        block.rsplit("-", 1)[-1] for block in block_ids(app.sidebar)
        if block.endswith(("-account_sidebar", "-flight_sync_status"))
    ]
    assert order[0] == "account_sidebar"
    assert app.sidebar.button(key="logout_button").label == "Log out"
    assert [item.label for item in app.sidebar.expander] == ["Accessibility settings"]
    assert [item.key for item in app.sidebar.toggle] == ["a11y_simplify", "_ui_chinese_toggle"]


def test_injected_styles_include_paper_shell_and_landscape_illustrations():
    styles = injected_styles()
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")
    academic = (ASSETS / "academic_ui.css").read_text(encoding="utf-8")

    assert shell in styles
    assert styles.index(academic) < styles.index(shell)
    for name in ("landscape-left", "landscape-right", "home-foliage"):
        encoded = base64.b64encode(
            (ASSETS / "illustrations" / f"{name}.webp").read_bytes()
        ).decode("ascii")
        assert f'--paper-{name}: url("data:image/webp;base64,{encoded}");' in styles
    assert "var(--paper-landscape-left" in shell
    assert "var(--paper-landscape-right" in shell
    assert "var(--paper-home-foliage" in shell


def test_paper_stylesheets_load_shell_first_then_by_file_name(tmp_path, monkeypatch):
    for name in ("paper_zeta.css", "paper_practice.css", "paper_shell.css", "paper_radar.css", "other.css"):
        (tmp_path / name).write_text("/* test */", encoding="utf-8")
    monkeypatch.setattr(ui_style, "ASSETS", tmp_path)

    assert [path.name for path in ui_style.paper_stylesheets()] == [
        "paper_shell.css", "paper_practice.css", "paper_radar.css", "paper_zeta.css",
    ]


def test_stylesheet_reads_are_cached_until_the_file_changes(tmp_path):
    sheet = tmp_path / "paper_cache.css"
    sheet.write_text("a { color: red; }", encoding="utf-8")
    first = ui_style._stylesheet(sheet)
    hits = ui_style._read_text.cache_info().hits

    assert ui_style._stylesheet(sheet) == first
    assert ui_style._read_text.cache_info().hits == hits + 1
    assert ui_style.illustration_data_uri("landscape-left") is ui_style.illustration_data_uri("landscape-left")


def test_no_stylesheet_hides_the_sidebar_or_its_buttons_after_sign_in():
    rules = css_rules(injected_styles())
    hiding = [
        selector for selector, body in rules
        if re.search(r"display:\s*none|visibility:\s*hidden", body)
        and any(f'"{control}"' in selector for control in SIDEBAR_CONTROLS)
    ]
    # Only the sign-in page, which has no navigation, keeps the sidebar away.
    assert hiding
    assert all("auth_forms" in selector for selector in hiding)
    assert any(
        "stSidebarCollapseButton" in selector and "visibility: visible !important" in body
        for selector, body in rules
    )


def test_paper_tokens_and_core_rules_are_defined():
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")
    root = css_rules(shell)[0][1]
    tokens = {
        "--paper-bg": "#FEF7EF", "--paper-panel": "#FAF3E9", "--paper-card": "#FFFCF7",
        "--paper-badge": "#F0EADA", "--paper-line": "#EEE7DF", "--paper-select": "#FAE5D2",
        "--ink": "#13224F", "--ink-body": "#2A2F33", "--ink-muted": "#6B7280",
        "--accent-rust": "#B5622E", "--accent-blue": "#5D81A1", "--accent-blue-dark": "#4A6C8A",
        "--font-title": 'Georgia, "Times New Roman", serif',
    }
    for name, value in tokens.items():
        assert f"{name}: {value};" in root
    rules = dict(css_rules(shell))
    headings = rules['[data-testid="stMain"] [data-testid="stMarkdownContainer"] :is(h1, h2),\n[data-testid="stMain"] :is(h1, h2)']
    assert "font-style: italic" in headings and "var(--font-title)" in headings
    buttons = rules[
        '[data-testid="stSidebarCollapseButton"] button,\nbutton[data-testid="stExpandSidebarButton"]'
    ]
    assert "min-width: 2.5rem" in buttons and "min-height: 2.5rem" in buttons
    assert "color: var(--ink)" in buttons
    narrow = shell[shell.index("@media (max-width: 759.98px)"):]
    assert "background-image: none" in narrow.split("}")[0]


def test_paper_text_colours_meet_contrast_on_their_surfaces():
    def luminance(hex_colour: str) -> float:
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(foreground: str, background: str) -> float:
        high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    pairs = [
        ("#FFFFFF", "#557A99"),  # primary button label on --accent-blue-fill
        ("#FFFFFF", "#4A6C8A"),  # primary hover
        ("#9A5426", "#FAE5D2"),  # current page / chosen pill label
        ("#13224F", "#F0EADA"),  # pill label
        ("#2A2F33", "#FEF7EF"),  # body text
        ("#586475", "#FAF3E9"),  # muted text, disabled buttons
        ("#4A6C8A", "#FEF7EF"),  # theme primary as text (tabs, links)
    ]
    for foreground, background in pairs:
        assert contrast(foreground, background) >= 4.5, (foreground, background)


def test_pilot_launcher_clears_the_app_header_on_narrow_screens():
    script = (ASSETS / "tutor_assistant.js").read_text(encoding="utf-8")

    assert "flight_header" not in script
    assert "document.querySelector('[data-testid=\"stHeader\"]')" in script
    assert "state.x = view.left + view.width - size - 24;" in script
    assert "state.y = view.top + view.height - size - 24;" in script
