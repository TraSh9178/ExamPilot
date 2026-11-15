"""Read optional explanatory copy without treating it as always-visible text."""
import html
import re


def tooltip_texts(app):
    # A module's one popover may contain several paragraphs of supporting copy.
    return [paragraph for item in app.markdown
            for text in re.findall(r'<span class="quiet-help-text"[^>]*>(.*?)</span>', item.value, re.S)
            for paragraph in html.unescape(text.replace('<br><br>', '\n\n').replace('<br>', '\n')).split('\n\n')]


def supporting_texts(app):
    return [item.value for item in app.caption] + tooltip_texts(app)
