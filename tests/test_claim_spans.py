"""Synthetic regressions for the off-by-one observed in a real checker response."""

from workspace.evidence import Draft, SemanticCheck, semantic_errors


def test_unique_exact_claim_text_corrects_model_character_arithmetic(store, synthetic):
    draft = Draft.model_validate(synthetic["draft"])
    value = synthetic["check"]
    value["claims"][0]["end"] -= 1
    check = SemanticCheck.model_validate(value)
    assert semantic_errors(draft, check, store.snapshot()) == []
    # The raw model object is retained unchanged, including the incorrect offset.
    assert check.claims[0].end == len(draft.answer) - 1


def test_invented_claim_text_still_fails_coverage(store, synthetic):
    draft = Draft.model_validate(synthetic["draft"])
    value = synthetic["check"]
    value["claims"][0]["text"] = "An invented claim that does not occur in the proposed answer"
    errors = semantic_errors(draft, SemanticCheck.model_validate(value), store.snapshot())
    assert "Invalid claim span" in errors
    assert "Semantic check omitted answer text" in errors


def test_unsupported_verdict_is_not_repaired_with_offsets(store, synthetic):
    draft = Draft.model_validate(synthetic["draft"])
    value = synthetic["check"]
    value["claims"][0]["end"] -= 1
    value["claims"][0]["verdict"] = "unsupported"
    errors = semantic_errors(draft, SemanticCheck.model_validate(value), store.snapshot())
    assert any("Unsupported claim" in error for error in errors)


def test_ambiguous_text_with_invalid_offsets_is_rejected(store, synthetic):
    draft_value = synthetic["draft"]
    draft_value["answer"] = "No. No."
    draft = Draft.model_validate(draft_value)
    check_value = synthetic["check"]
    check_value.update(full_answer=draft.answer)
    check_value["claims"][0].update(start=1, end=2, text="No.")
    assert "Invalid claim span" in semantic_errors(draft, SemanticCheck.model_validate(check_value), store.snapshot())
