"""Supply the v2 registry omitted by Streamlit 1.55's AppTest runtime.

Use the real component manager so page regressions still render and validate
the component definition. Browser interaction is verified separately.
"""

from unittest.mock import MagicMock

import pytest
from streamlit.components.v2.component_manager import BidiComponentManager
from streamlit.runtime import Runtime
from streamlit.testing.v1 import app_test


@pytest.fixture(autouse=True)
def app_test_component_registry(monkeypatch):
    manager = BidiComponentManager()

    def runtime_mock(*args, **kwargs):
        mocked = MagicMock(*args, **kwargs)
        if kwargs.get("spec") is Runtime:
            mocked.bidi_component_registry = manager
        return mocked

    monkeypatch.setattr(app_test, "MagicMock", runtime_mock)
    from services.tutor_assistant_ui import _component

    _component.cache_clear()
    yield
    _component.cache_clear()
