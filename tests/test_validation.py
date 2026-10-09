import copy
import json

import pytest
from conftest import SyntheticTransport
from google.genai import _transformers, types
from pydantic import ValidationError

from workspace.evidence import (
    Draft,
    SemanticCheck,
    reference_errors,
    replaced_evidence,
    semantic_errors,
)
from workspace.gemini import Gemini, ModelFailure, ReplayTransport, wire_schema
from workspace.store import Store


@pytest.fixture
def memory(seed):
    store = Store(":memory:")
    store.import_seed(seed)
    yield store
    store.close()


def question(store):
    row = store.question("Q1")
    return {k: row[k] for k in ("id", "text", "topic")}


def test_sdk_accepts_shared_output_contracts_without_client():
    for contract in (Draft, SemanticCheck):
        config = types.GenerateContentConfig(response_schema=contract,
                                             response_mime_type="application/json")
        assert config.response_schema is contract
        schema = _transformers.t_schema(None, config.response_schema)
        assert set(schema.required) == set(contract.model_fields)


def test_supported_synthetic_answer_and_replaced_text(memory, synthetic):
    draft = Draft.model_validate(synthetic["draft"])
    check = SemanticCheck.model_validate(synthetic["check"])
    snapshot = memory.snapshot()
    assert not reference_errors(draft, "Q1", snapshot)
    assert not semantic_errors(draft, check, snapshot)
    assert replaced_evidence(draft, snapshot) == [{
        "passage_id": "EXPORT-v1:p1", "excerpt": "CSV exports are available on every plan.",
        "role": "replaced",
    }]


@pytest.mark.parametrize("purpose,case", [(p, c) for p in ("draft", "check")
                                         for c in ("json", "missing", "type", "extra", "enum")])
def test_bad_output_captured_before_parsing(memory, synthetic, purpose, case):
    value = copy.deepcopy(synthetic[purpose])
    if case == "json":
        raw = "{broken"
    else:
        if case == "missing":
            del value["question_id"]
        elif case == "type":
            value["question_id"] = 1
        elif case == "extra":
            value["approval"] = True
        elif purpose == "draft":
            value["disposition"] = "approved"
        else:
            value["claims"][0]["verdict"] = "approved"
        raw = json.dumps(value)
    engine = Gemini(memory, SyntheticTransport(raw))
    with pytest.raises(ModelFailure, match="Invalid Gemini output") as error:
        engine.run(purpose, question(memory), memory.snapshot(),
                   None if purpose == "draft" else Draft.model_validate(synthetic["draft"]))
    run = memory.one("SELECT * FROM model_runs WHERE id=?", (error.value.run_id,))
    assert run["raw_response"] == raw
    assert run["origin"] == "synthetic"
    assert json.loads(run["request"])["schema"]["additionalProperties"] is False
    replay = Gemini(memory, ReplayTransport(memory, synthetic=True))
    with pytest.raises(ModelFailure, match="Invalid Gemini output"):
        replay.run(purpose, question(memory), memory.snapshot(),
                   None if purpose == "draft" else Draft.model_validate(synthetic["draft"]))


@pytest.mark.parametrize("case,reason", [
    ("missing", "Missing passage"), ("excerpt", "not verbatim"),
    ("old", "has been replaced"), ("unavailable", "Source unavailable"),
    ("question", "question ID"), ("conflict", "Unresolved source conflict"),
])
def test_reference_failures(memory, synthetic, case, reason):
    value = synthetic["draft"]
    snapshot = memory.snapshot()
    citation = value["citations"][0]
    if case == "missing":
        citation["passage_id"] = "absent"
    elif case == "excerpt":
        citation["excerpt"] = "Invented quote"
    elif case == "old":
        citation.update(passage_id="EXPORT-v1:p1", excerpt="CSV exports are available on every plan.")
    elif case == "unavailable":
        snapshot["availability"]["EXPORT-v2"] = False
    elif case == "question":
        value["question_id"] = "other"
    else:
        for doc in snapshot["documents"]:
            if doc["id"] == "EXPORT-v2":
                doc["supersedes"] = None
    errors = reference_errors(Draft.model_validate(value), "Q1", snapshot)
    assert any(reason in e for e in errors)


@pytest.mark.parametrize("case,reason", [
    ("irrelevant", "irrelevant"), ("unsupported", "Unsupported claim"),
    ("uncertain", "Uncertain claim"), ("contradicted", "Contradicted claim"),
    ("coverage", "missing claim coverage"), ("span", "omitted answer text"),
    ("support", "cited passages"), ("exact", "exact answer"),
    ("question", "answer the question"), ("conflict", "Unresolved source conflict"),
])
def test_semantic_failures(memory, synthetic, case, reason):
    draft = Draft.model_validate(synthetic["draft"])
    value = synthetic["check"]
    claim = value["claims"][0]
    snapshot = memory.snapshot()
    if case == "irrelevant":
        value["citations_relevant"] = False
    elif case in ("unsupported", "uncertain", "contradicted"):
        claim["verdict"] = case
    elif case == "coverage":
        value["omitted_claims"] = ["extra capability"]
    elif case == "span":
        claim.update(end=3, text="No.")
    elif case == "support":
        claim["supporting_passage_ids"] = ["SUPPORT-v1:p1"]
    elif case == "exact":
        value["full_answer"] += " "
    elif case == "question":
        value["answers_question"] = False
    else:
        for doc in snapshot["documents"]:
            if doc["id"] == "EXPORT-v2":
                doc["supersedes"] = None
    errors = semantic_errors(draft, SemanticCheck.model_validate(value), snapshot)
    assert any(reason in e for e in errors)


def test_edits_use_same_contract(synthetic):
    synthetic["draft"]["citations"] = []
    with pytest.raises(ValidationError, match="wording and citations"):
        Draft.model_validate(synthetic["draft"])


def test_exact_replay_is_offline_and_synthetic_is_never_real(memory, synthetic, monkeypatch):
    live = Gemini(memory, SyntheticTransport(synthetic["draft"]))
    draft, original_id = live.run("draft", question(memory), memory.snapshot())
    monkeypatch.setattr("workspace.gemini.genai.Client", lambda **kw: pytest.fail("Client initialized"))
    class ForbiddenEnvironment(dict):
        def get(self, *args):
            pytest.fail("Replay attempted environment/credential access")

    monkeypatch.setattr("workspace.gemini.os.environ", ForbiddenEnvironment())
    replay = Gemini(memory, ReplayTransport(memory, synthetic=True))
    result, replay_id = replay.run("draft", question(memory), memory.snapshot())
    assert result == draft
    run = memory.one("SELECT * FROM model_runs WHERE id=?", (replay_id,))
    assert run["origin"] == "replay_synthetic"
    assert run["original_run"] == original_id
    with pytest.raises(ModelFailure, match="replay match"):
        replay.run("draft", {**question(memory), "text": "different"}, memory.snapshot())
    with pytest.raises(ModelFailure, match="replay match"):
        Gemini(memory, ReplayTransport(memory)).run("draft", question(memory), memory.snapshot())


def test_transport_error_is_sanitized_and_recorded(memory):
    engine = Gemini(memory, SyntheticTransport(TimeoutError("Authorization: secret")))
    with pytest.raises(ModelFailure, match="TimeoutError"):
        engine.run("draft", question(memory), memory.snapshot())
    run = memory.one("SELECT * FROM model_runs")
    assert run["raw_response"] is None
    assert "secret" not in run["error"]


def test_sdk_transport_with_stub_client_reads_only_synthetic_configuration(synthetic, monkeypatch):
    """Exercise SDK argument construction locally; no client/network/real key is used."""
    from types import SimpleNamespace

    from workspace.gemini import LiveTransport

    calls = []

    class StubClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "synthetic-placeholder"
            assert kwargs["enterprise"] is False
            assert kwargs["http_options"].base_url == "https://generativelanguage.googleapis.com"
            assert kwargs["http_options"].api_version == "v1beta"
            assert kwargs["http_options"].timeout == 30000
            assert kwargs["http_options"].retry_options.attempts == 1
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps(synthetic["draft"]), response_id="synthetic",
                                   model_version="synthetic", usage_metadata=None, candidates=[])

    monkeypatch.setattr("workspace.gemini.os.environ", {"GEMINI_API_KEY": "synthetic-placeholder"})
    monkeypatch.setattr("workspace.gemini.genai.Client", StubClient)
    request = {"model": "synthetic-test-model", "timeout_ms": 30000,
               "contents": ['{"question":"synthetic"}', '{"documents":[]}'],
               "settings": {"temperature": 0, "max_output_tokens": 8192},
               "system_instruction": "Synthetic test only"}
    response = LiveTransport().send(request, Draft)
    assert response.metadata["response_id"] == "synthetic"
    assert calls[0]["config"].response_json_schema is None
    assert calls[0]["config"].response_schema == wire_schema(Draft)
    assert calls[0]["config"].response_mime_type == "application/json"
    assert [p.text for p in calls[0]["contents"][0].parts] == request["contents"]
