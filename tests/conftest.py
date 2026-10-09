import json
import tempfile
from pathlib import Path

import pytest

from workspace.gemini import Response
from workspace.store import Store


def pytest_configure():
    # Streamlit also creates temporary directories outside pytest's basetemp.
    directory = Path(__file__).resolve().parents[1] / ".tmp"
    directory.mkdir(exist_ok=True)
    tempfile.tempdir = str(directory)


@pytest.fixture(autouse=True)
def prevent_live_client(monkeypatch):
    def forbidden_client(*args, **kwargs):
        pytest.fail("Offline test attempted to initialize a real Gemini client")

    monkeypatch.setattr("workspace.gemini.genai.Client", forbidden_client)


@pytest.fixture
def seed():
    return json.loads(Path("tasks/evidence/seed.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path, seed):
    result = Store(tmp_path / "test.sqlite3")
    result.import_seed(seed)
    yield result
    result.close()


@pytest.fixture
def synthetic():
    value = json.loads(Path("tests/fixtures/synthetic/export.json").read_text(encoding="utf-8"))
    assert value["provenance"].startswith("synthetic")
    return value


class SyntheticTransport:
    origin = "synthetic"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def send(self, request, contract):
        self.calls.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Response(response if isinstance(response, str) else json.dumps(response),
                        {"provenance": "synthetic test response"})
