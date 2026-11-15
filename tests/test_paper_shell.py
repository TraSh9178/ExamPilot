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
    # No navigation menus: the only popover left is the account avatar's.
    assert block_types(app.main).count("popover") == 1
    assert block_types(find_block(app.main, "account_menu")) == ["popover"]
    assert not [box for box in app.main.selectbox if (box.key or "").startswith("flight_review")]
    assert not [link for link in app.main.get("page_link") if link.proto.label in {"Home", "Practice"}]
    assert any(block.endswith("-flight_course_context") for block in main_ids)
    assert "Calculus I Demo  /  Home" in [caption.value for caption in app.main.caption]


def find_block(node, key: str) -> Block | None:
    """Return the first keyed container below node whose key is `key`."""
    for child in node.children.values():
        if isinstance(child, Block):
            if child.proto is not None and getattr(child.proto, "id", "").endswith(f"-{key}"):
                return child
            found = find_block(child, key)
            if found is not None:
                return found
    return None


def test_sidebar_holds_save_status_then_accessibility_last_and_no_account_block():
    app = signed_in_app(APP_PATH).run()

    assert not app.exception
    sidebar_keys = ("sidebar_footer", "account_sidebar", "flight_sync_status", "sidebar_accessibility")
    order = [
        block.rsplit("-", 1)[-1] for block in block_ids(app.sidebar)
        if block.endswith(tuple(f"-{key}" for key in sidebar_keys))
    ]
    # Save status sits in the footer; accessibility is its own block after it.
    assert order == ["sidebar_footer", "flight_sync_status", "sidebar_accessibility"]
    footer = find_block(app.sidebar, "sidebar_footer")
    accessibility = find_block(app.sidebar, "sidebar_accessibility")
    assert not footer.expander
    assert [item.label for item in accessibility.expander] == ["Accessibility settings"]
    assert [item.key for item in accessibility.toggle] == ["a11y_simplify", "_ui_chinese_toggle"]
    assert [item.label for item in app.sidebar.expander] == ["Accessibility settings"]
    # The account moved to the avatar menu; nothing of it is left in the sidebar.
    assert not app.sidebar.get("page_link")
    assert not [button for button in app.sidebar.button if button.key == "logout_button"]
    assert not any("SIGNED IN AS" in item.value for item in app.sidebar.markdown)


def test_account_actions_stay_inside_the_avatar_popover():
    from tests.auth_helpers import TEST_USER

    app = signed_in_app(APP_PATH).run()

    assert not app.exception
    menu = find_block(app.main, "account_menu")
    (popover,) = [child for child in menu.children.values() if isinstance(child, Block)]
    # The avatar button shows only the initial; the two actions are inside its menu.
    assert popover.type == "popover"
    assert popover.proto.popover.label == TEST_USER.username[:1].upper()
    assert [link.proto.label for link in popover.get("page_link")] == ["My account"]
    assert popover.button(key="logout_button").label == "Log out"
    assert not popover.get("checkbox")
    # Nowhere else on the page.
    assert [link.proto.label for link in app.main.get("page_link")].count("My account") == 1
    assert [button.key for button in app.main.button].count("logout_button") == 1


def test_account_avatar_is_a_round_button_fixed_in_the_top_right_corner():
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")

    corner = css_rule(shell, ".st-key-account_menu")
    assert "position: fixed;" in corner
    assert "top: .5rem;" in corner
    assert "right: 7.5rem;" in corner
    button = css_rule(shell, '.st-key-account_menu [data-testid="stPopover"] button')
    assert "border-radius: 50%;" in button
    assert "width: 2.75rem;" in button and "height: 2.75rem;" in button
    # Both rows of the menu start from the left edge.
    rows = (
        '[data-testid="stPopoverBody"]:has(.account-menu-identity)'
        ' :is([data-testid="stPageLink"] a, .st-key-logout_button button)'
    )
    assert "justify-content: flex-start;" in css_rule(shell, rows)


def css_rule(stylesheet: str, selector: str) -> str:
    """Return the declarations of the first top-level rule with this exact selector."""
    match = re.search(rf"(?m)^{re.escape(selector)} \{{\n(.*?)\n\}}", stylesheet, re.DOTALL)
    assert match, f"no rule for {selector}"
    return match.group(1)


def test_accessibility_settings_rest_on_the_bottom_edge_below_the_sidebar_watercolour():
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")
    wrapper = '[data-testid="stSidebarUserContent"] [data-testid="stLayoutWrapper"]'

    closed = css_rule(shell, f"{wrapper}:has(> .st-key-sidebar_accessibility)")
    # The block grows into the height the page list leaves free, which rests
    # the settings on the bottom edge.
    assert "flex: 1 0 auto;" in closed
    # Opaque, so nothing shows through the open panel; not sticky while closed,
    # so on a short window it never covers the links above it.
    assert "background-color: var(--paper-bg);" in closed
    assert "position:" not in closed
    opened = css_rule(shell, f"{wrapper}:has(> .st-key-sidebar_accessibility details[open])")
    assert "position: sticky;" in opened
    assert "bottom: 0;" in opened

    # The watercolour is drawn in that free space, above the control, not
    # behind the whole sidebar, so it can never sit under a control.
    painting = css_rule(shell, ".st-key-sidebar_accessibility::before")
    assert "var(--paper-landscape-left" in painting
    assert "flex: 1 0 0px;" in painting
    assert "background-position: left bottom;" in painting
    assert "clamp(0px," in painting
    assert "var(--paper-landscape-left" not in css_rule(shell, 'section[data-testid="stSidebar"]')
    assert "padding-bottom: 0;" in css_rule(shell, '[data-testid="stSidebarUserContent"]')


def test_stacked_blocks_keep_a_gap_between_them():
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")

    # Markdown blocks without a paragraph lose 1rem below them; these three get it back.
    pulled_together = re.search(r"((?:[^{}\n]+,\n)*[^{}\n]+) \{\n  margin-bottom: 0;\n\}", shell)
    assert pulled_together
    selectors = [selector.strip() for selector in pulled_together.group(1).split(",\n")]
    assert selectors == [
        '[data-testid="stMarkdownContainer"]:has(> .account-menu-identity)',
        '[class*="st-key-dashboard_course_card_"] [data-testid="stMarkdownContainer"]:has(> .academic-course-icon)',
        '[class*="st-key-dashboard_course_card_"] > [data-testid="stElementContainer"]:first-child'
        ' [data-testid="stCaptionContainer"]',
    ]
    expander = '[data-testid="stMain"] [data-testid="stLayoutWrapper"]:has(> [data-testid="stExpander"])'
    assert "margin-top: .5rem;" in css_rule(shell, expander)
    card_row = '[data-testid="stMain"] [data-testid="stHorizontalBlock"]:has([class*="st-key-dashboard_course_card_"])'
    assert "margin-bottom: .5rem;" in css_rule(shell, card_row)


def test_sidebar_hills_move_to_the_window_corner_when_the_sidebar_is_collapsed():
    shell = (ASSETS / "paper_shell.css").read_text(encoding="utf-8")
    main = '[data-testid="stMain"]'

    # The main area always paints two layers; the left one is empty by default.
    base = css_rule(shell, main)
    assert "--paper-main-left: none;" in base
    assert "background-image: var(--paper-main-left), var(--paper-landscape-right, none);" in base
    assert "background-position: left bottom, right bottom;" in base
    collapsed = css_rule(
        shell,
        '[data-testid="stAppViewContainer"]'
        ':has(section[data-testid="stSidebar"][aria-expanded="false"]) ' + main,
    )
    assert "--paper-main-left: var(--paper-landscape-left, none);" in collapsed
    # The sign-in page and narrow screens still clear the whole background.
    assert "background-image: none;" in css_rule(
        shell, f'[data-testid="stApp"]:has(.st-key-auth_forms) {main}'
    )
    narrow = re.search(r"@media \(max-width: 759\.98px\) \{\n(.*?)\n\}\n", shell, re.DOTALL)
    assert narrow and re.search(
        r"\[data-testid=\"stMain\"\] \{\n\s+background-image: none;", narrow.group(1)
    )


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
