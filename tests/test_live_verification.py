import json

import pytest
from conftest import SyntheticTransport
from google.genai.errors import APIError
from pydantic import ValidationError

from scripts import verify_live
from workspace.evidence import Draft, SemanticCheck
from workspace.gemini import (
    CHECK_PROMPT,
    EMPTY_ANSWER_CHECK_PROMPT,
    Gemini,
    ModelFailure,
    wire_schema,
)


def test_empty_proposed_answer_has_no_invented_checker_claims():
    value = {"question_id": "Q2", "full_answer": "", "all_claims_covered": True,
             "answers_question": False, "citations_relevant": False,
             "omitted_claims": [], "claims": [], "conflicts": []}
    assert SemanticCheck.model_validate(value).claims == []
    with pytest.raises(ValidationError, match="requires claim coverage"):
        SemanticCheck.model_validate(dict(value, full_answer="A factual claim"))


def test_api_schema_is_derived_without_weakening_local_extra_field_validation(synthetic):
    assert "additionalProperties" not in json.dumps(wire_schema(Draft))
    assert Draft.model_json_schema()["additionalProperties"] is False
    with pytest.raises(ValidationError):
        Draft.model_validate(dict(synthetic["draft"], unexpected_field="rejected locally"))
    with pytest.raises(ValidationError):
        Draft.model_validate(dict(synthetic["draft"], answer="x" * 2001))


def test_provider_error_preserves_diagnostic_but_redacts_credentials(store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-private-value")
    error = APIError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                   "message": "Rejected schema; key=synthetic-private-value"}})
    engine = Gemini(store, SyntheticTransport(error))
    question = {k: store.question("Q1")[k] for k in ("id", "topic", "text")}
    with pytest.raises(ModelFailure, match="HTTP 400 / INVALID_ARGUMENT"):
        engine.run("draft", question, store.snapshot())
    recorded = store.one("SELECT * FROM model_runs")["error"]
    assert "Rejected schema" in recorded
    assert "synthetic-private-value" not in recorded
    assert "[REDACTED]" in recorded


def test_explicit_verification_config_loader_never_loads_other_private_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_live, "ROOT", tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    (tmp_path / ".env").write_text('GEMINI_API_KEY="synthetic-only" # comment\nGEMINI_MODEL=gemini-test\nPRIVATE_NOTE=secret\n')
    assert verify_live.local_configuration() == "gemini-test"
    assert verify_live.os.environ["GEMINI_API_KEY"] == "synthetic-only"
    assert "PRIVATE_NOTE" not in verify_live.os.environ


def test_seed_transport_rejects_user_added_source_before_any_client(store, seed):
    transport = verify_live.ApprovedSeedTransport(seed["questions"], store.snapshot())
    engine = Gemini(store, transport)
    question = {k: store.question("Q1")[k] for k in ("id", "topic", "text")}
    request = engine.request("draft", question, store.snapshot())
    request["source_snapshot"] = json.loads(json.dumps(request["source_snapshot"]))
    request["source_snapshot"]["documents"][0]["passages"][0]["text"] = "Private user-added source"
    with pytest.raises(ValueError, match="outside the approved"):
        transport.send(request, verify_live.Draft)


def test_seed_transport_rejects_private_notes_in_request_contents(store, seed):
    transport = verify_live.ApprovedSeedTransport(seed["questions"], store.snapshot())
    engine = Gemini(store, transport)
    question = {k: store.question("Q1")[k] for k in ("id", "topic", "text")}
    request = engine.request("draft", question, store.snapshot())
    request["contents"].append(json.dumps({"reviewer_note": "private and not authorized"}))
    with pytest.raises(ValueError, match="outside the approved application payload"):
        transport.send(request, verify_live.Draft)


def test_empty_checker_guidance_preserves_answered_requests_and_guard(store, seed, synthetic, monkeypatch):
    from workspace.gemini import LiveTransport, Response

    engine = Gemini(store, None)
    question = {k: store.question("Q2")[k] for k in ("id", "topic", "text")}
    draft = Draft.model_validate({"question_id": "Q2", "disposition": "unresolved", "answer": "",
                                  "citations": [], "conflicts": [], "unresolved_reason": "JSON export is undocumented"})
    request = engine.request("check", question, store.snapshot(), draft)
    assert request["system_instruction"] == CHECK_PROMPT + EMPTY_ANSWER_CHECK_PROMPT
    assert json.loads(request["contents"][2])["proposed_answer"]["answer"] == ""
    answered = Draft.model_validate(synthetic["draft"])
    q1 = {k: store.question("Q1")[k] for k in ("id", "topic", "text")}
    assert engine.request("check", q1, store.snapshot(), answered)["system_instruction"] == CHECK_PROMPT
    calls = []
    monkeypatch.setattr(LiveTransport, "send", lambda self, value, contract: calls.append(value) or Response("{}"))
    transport = verify_live.ApprovedSeedTransport([question], store.snapshot())
    transport.send(request, SemanticCheck)
    assert calls == [request]
    with pytest.raises(ValueError, match="outside the approved application payload"):
        transport.send({**request, "system_instruction": CHECK_PROMPT}, SemanticCheck)
