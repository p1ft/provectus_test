from scripts.prepare_live_request import prepare
from scripts.verify_reference_cases import verify


def test_reference_report_separates_synthetic_outcomes_and_blocked_real_checks(tmp_path):
    report = verify(tmp_path / "report", replay_directory=tmp_path / "missing-captures")
    synthetic = [r for r in report["rows"] if r["provenance"].startswith("synthetic")]
    assert len(synthetic) == 15
    assert all(r["result"] == "pass" for r in synthetic)
    assert all(r["expected_origin"] for r in synthetic)
    real = [r for r in report["rows"] if not r["provenance"].startswith("synthetic")]
    assert len(real) == 9
    assert all(r["result"] == "unverified" for r in real)
    assert (tmp_path / "report/reference-results.md").exists()
    assert (tmp_path / "report/reference-results.json").exists()


def test_reviewable_live_request_is_prepared_without_model_calls(tmp_path):
    import json

    path = prepare(tmp_path / "pending-live.json")
    proposal = json.loads(path.read_text(encoding="utf-8"))
    assert proposal["status"].startswith("Pending explicit user approval")
    assert len(proposal["draft_requests"]) == 8
    assert all(len(r["source_snapshot"]["documents"]) == 5 for r in proposal["draft_requests"])
    assert proposal["destination"].startswith("https://generativelanguage.googleapis.com/")
    assert proposal["semantic_check"]["schema"]["additionalProperties"] is False
    assert path.with_suffix(".md").exists()


def test_report_renders_unattempted_live_cases_and_partial_replay(tmp_path):
    import json

    output = tmp_path / "blocked-report"
    output.mkdir()
    (output / "live-results.json").write_text(json.dumps({
        "provenance": "Synthetic unit-test input for report failure handling; not a provider result",
        "capture_directory": str(output / "missing-real-captures"),
        "blocker": "Synthetic provider blocker",
        "live_rows": [{"case": "Q2", "result": "unverified", "reason": "Not attempted"}],
        "replay_rows": [],
        "partial_draft_replay": [{"case": "Q1", "result": "pass", "scope": "Synthetic test of partial replay rendering"}],
    }))
    report = verify(output, replay_directory=tmp_path / "missing-captures")
    assert any(row["case"] == "Q2" and row.get("reason") == "Not attempted" for row in report["rows"])
    assert "Synthetic test of partial replay rendering" in (output / "reference-results.md").read_text()


def test_current_malformed_real_replay_is_a_failure_not_missing_evidence(tmp_path, monkeypatch):
    import json

    from scripts import verify_reference_cases
    from scripts.prepare_verification import prepare

    captures = prepare(tmp_path / "captures")
    for path in captures.glob("*.json"):
        value = json.loads(path.read_text())
        if value["question_id"] == "Q3" and value["purpose"] == "draft":
            value.update(origin="live", raw_response="{malformed synthetic test of real replay",
                         metadata={"provenance": "Synthetic malformed real-mode test"})
            path.write_text(json.dumps(value))
    monkeypatch.setattr(verify_reference_cases, "REAL_REPLAY_MODEL", "gemini-3.8-flash")
    report = verify(tmp_path / "report", replay_directory=captures)
    row = next(r for r in report["rows"] if r["case"] == "Q3" and r.get("checker") is None
               and r["provenance"].startswith("replay of"))
    assert row["result"] == "fail"
    assert row["invocation"] == "current"
    assert "Invalid Gemini output" in row["observed"]["error"]
    assert report["current_failures"] == ["Q3"]
