import json
from pathlib import Path

from scripts.verify_extension import SEED, verify
from workspace.evidence import validate_seed


def test_extension_preserves_original_fixture_contracts():
    original = json.loads(Path("tasks/evidence/seed.json").read_text(encoding="utf-8"))
    extension = validate_seed(json.loads(SEED.read_text(encoding="utf-8")))
    assert extension["documents"][:len(original["documents"])] == original["documents"]
    assert extension["questions"][:len(original["questions"])] == original["questions"]
    assert extension["owners"] == original["owners"]
    assert len(extension["questions"]) == len(original["questions"]) + 5


def test_extension_exercises_all_five_scenarios_through_service(tmp_path):
    report = verify(tmp_path)
    assert {r["case"] for r in report["results"]} == {
        "supported", "unsupported", "conflicting_source", "approved_reuse", "changed_source"}
    assert all(r["status"] == "pass" for r in report["results"]), report
    assert report["real_extension_verification"]["status"] == "unverified"
