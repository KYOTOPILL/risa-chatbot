import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture(scope="session")
def mock_content(tmp_path_factory):
    """Fresh mock documents in a temp folder, so tests never depend on the real content/ folder."""
    from make_mock_content import main

    root = tmp_path_factory.mktemp("mock_content")
    main(root)
    return root


@pytest.fixture(autouse=True)
def _own_tracker_db(tmp_path, monkeypatch):
    """No test reads or writes the real tracker.db: it holds whatever was clicked in the UI (roles, demo people). A test that builds its own Tracker overrides this."""
    from app.core import state
    from app.features.tracker import Tracker

    tk = Tracker(tmp_path / "default-tracker.db")
    monkeypatch.setattr(state, "get_tracker", lambda: tk)
