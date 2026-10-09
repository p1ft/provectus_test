import json

import pytest
from pydantic import ValidationError

from scripts.prepare_verification import prepare
from workspace.evidence import CapturedRun, Draft, SemanticCheck, fingerprint
from workspace.gemini import FileReplayTransport, Gemini, ModelFailure
from workspace.service import Service
from workspace.store import Store


def test_file_replay_into_independent_database_preserves_current_evidence(tmp_path, seed):
    captures = prepare(tmp_path / "captures")
    seed["documents"].reverse()  # Different local source row IDs from the capture database.
    store = Store(tmp_path / "replay.db")
    try:
        store.import_seed(seed)
        service = Service(store, Gemini(store, FileReplayTransport(captures, synthetic=True)))
        revision = service.generate("Q1")
        assert revision is not None
        assert store.question("Q1")["status"] == "answered"
        for citation in store.revision(revision)["citations"]:
            document = json.loads(citation["document"])
            assert citation["source_revision"] == store.snapshot()["revision_ids"][document["id"]]
        runs = store.rows("SELECT * FROM model_runs")
        assert len(runs) == 2
        assert all(r["origin"] == "replay_synthetic" and r["original_run"] for r in runs)
        assert all(json.loads(r["metadata"])["capture_file"] for r in runs)
    finally:
        store.close()


def test_synthetic_bundle_never_satisfies_real_replay(tmp_path, store):
    captures = prepare(tmp_path / "captures")
    service = Service(store, Gemini(store, FileReplayTransport(captures)))
    assert service.generate("Q1") is None
    assert store.question("Q1")["last_error"] == "No exact replay match"


def test_tampered_and_malformed_bundles_fail_closed(tmp_path, store):
    captures = prepare(tmp_path / "captures")
    # Only the matching draft request is needed; tamper all draft captures so none can match.
    for path in captures.glob("*.json"):
        value = json.loads(path.read_text())
        if value["purpose"] == "draft":
            value["request"]["question"]["text"] = "Tampered"
            path.write_text(json.dumps(value))
    (captures / "broken.json").write_text("{not JSON")
    service = Service(store, Gemini(store, FileReplayTransport(captures, synthetic=True)))
    assert service.generate("Q1") is None
    assert store.question("Q1")["last_error"] == "No exact replay match"


@pytest.mark.parametrize("question", [
    "not-an-object", None, [], 7, {"id": "Q1"},
    {"id": ["Q1"], "topic": "exports", "text": "Can free-plan users export CSV?"},
])
def test_capture_rejects_malformed_nested_question(question):
    request = {"question": question, "purpose": "draft"}
    value = {"id": 1, "question_id": "Q1", "purpose": "draft", "request": request,
             "request_fingerprint": fingerprint(request), "raw_response": "{}", "error": None,
             "origin": "synthetic", "original_run": None, "metadata": {},
             "created_at": "2026-10-09T12:00:00Z"}
    with pytest.raises(ValidationError):
        CapturedRun.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("valid_capture_available", [True, False])
def test_invalid_nested_question_does_not_crash_or_block_replay(
        tmp_path, store, valid_capture_available):
    captures = prepare(tmp_path / "captures")
    value = json.loads(next(captures.glob("*.json")).read_text())
    value["request"]["question"] = "not-an-object"
    value["request_fingerprint"] = fingerprint(value["request"])
    if not valid_capture_available:
        captures = tmp_path / "invalid-only"
        captures.mkdir()
    # Sort before every valid bundle to reproduce an unrelated file blocking replay.
    (captures / "000-invalid.json").write_text(json.dumps(value))
    (captures / "000-invalid-encoding.json").write_bytes(b"\xff")
    service = Service(store, Gemini(store, FileReplayTransport(captures, synthetic=True)))
    revision = service.generate("Q1")
    runs = store.rows("SELECT * FROM model_runs ORDER BY id")
    if valid_capture_available:
        assert revision is not None
        assert store.question("Q1")["status"] == "answered"
        assert len(runs) == 2
        assert all(run["error"] is None for run in runs)
    else:
        assert revision is None
        assert store.question("Q1")["last_error"] == "No exact replay match"
        assert len(runs) == 1
        assert runs[0]["error"] == "No exact replay match"
        assert not store.rows("SELECT * FROM answer_revisions")


def test_matching_malformed_raw_response_saved_before_parsing(tmp_path, store):
    captures = prepare(tmp_path / "captures")
    for path in captures.glob("*.json"):
        value = json.loads(path.read_text())
        if value["purpose"] == "draft" and value["question_id"] == "Q1":
            value["raw_response"] = "{broken raw response"
            path.write_text(json.dumps(value))
    engine = Gemini(store, FileReplayTransport(captures, synthetic=True))
    question = {k: store.question("Q1")[k] for k in ("id", "topic", "text")}
    with pytest.raises(ModelFailure, match="Invalid Gemini output") as error:
        engine.run("draft", question, store.snapshot())
    assert store.one("SELECT * FROM model_runs WHERE id=?", (error.value.run_id,))["raw_response"] == "{broken raw response"


def test_capture_contains_exact_prompts_schema_sources_and_settings(tmp_path):
    captures = prepare(tmp_path / "captures")
    run = CapturedRun.model_validate_json(next(captures.glob("*.json")).read_text())
    request = run.request
    assert len(request["source_snapshot"]["documents"]) == 5
    assert request["system_instruction"]
    assert request["schema"] == (Draft.model_json_schema() if run.purpose == "draft"
                                 else SemanticCheck.model_json_schema())
    assert request["model"] and request["sdk_version"]
    assert request["settings"] == {"temperature": 0, "max_output_tokens": 8192}
    assert request["timeout_ms"] == 30000
    assert "GEMINI_API_KEY" not in json.dumps(request)
