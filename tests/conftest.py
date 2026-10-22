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
