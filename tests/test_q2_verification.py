import pytest
from conftest import SyntheticTransport

from scripts.verify_q2 import inspect
from workspace.gemini import Gemini
from workspace.service import Service


@pytest.mark.parametrize("invalid_conflict", [False, True])
def test_q2_verification_requires_valid_draft_as_well_as_empty_checker(store, invalid_conflict):
    draft = {"question_id": "Q2", "disposition": "unresolved", "answer": "", "citations": [],
             "unresolved_reason": "JSON export is undocumented.", "conflicts": []}
    if invalid_conflict:
        draft["conflicts"] = [{"passage_ids": ["EXPORT-v1", "EXPORT-v2"],
                               "explanation": "Synthetic reproduction of invalid document-level IDs"}]
    check = {"question_id": "Q2", "full_answer": "", "all_claims_covered": True,
             "answers_question": False, "citations_relevant": False,
             "omitted_claims": [], "claims": [], "conflicts": []}
    service = Service(store, Gemini(store, SyntheticTransport(draft, check)))
    question = {k: store.question("Q2")[k] for k in ("id", "topic", "text")}
    row, observed = inspect(service, question, {"id": "Q2", "status": "unresolved", "owner": "Product reviewer"})
    assert row["question_result"] == "pass"
    assert row["checker"]["semantic_result"] == "pass"
    assert row["result"] == ("fail" if invalid_conflict else "pass")
    assert bool(row["draft_findings"]) == invalid_conflict
    assert observed["answer"] == ""
    assert store.question("Q2")["status"] == "unresolved"
    assert not store.rows("SELECT * FROM approvals")
