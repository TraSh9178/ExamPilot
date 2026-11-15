"""Read optional explanatory copy without treating it as always-visible text."""
import html
import re


def tooltip_texts(app):
    return [html.unescape(text) for item in app.markdown
            for text in re.findall(r'<span class="quiet-help-text"[^>]*>(.*?)</span>', item.value, re.S)]


def supporting_texts(app):
    return [item.value for item in app.caption] + tooltip_texts(app)
