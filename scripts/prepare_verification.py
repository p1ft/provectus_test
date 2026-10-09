"""Create explicitly synthetic exact-request captures without credentials or API calls."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workspace.gemini import Gemini, capture_bundle
from workspace.schemas import Draft, SemanticCheck
from workspace.store import Store


def synthetic_check(draft):
    """Only called for the explicitly declared fixture wording, never arbitrary user edits."""
    return SemanticCheck.model_validate({
        "question_id": draft.question_id, "full_answer": draft.answer, "all_claims_covered": True,
        "answers_question": True, "citations_relevant": True, "omitted_claims": [],
        "conflicts": [c.model_dump() for c in draft.conflicts],
        "claims": [{"start": 0, "end": len(draft.answer), "text": draft.answer,
                    "supporting_passage_ids": [c.passage_id for c in draft.citations],
                    "verdict": "supported", "explanation": "Synthetic fixture assessment; not a real model result"}],
    })


def prepare(output, *, seed_path=ROOT / "tasks/evidence/seed.json",
            fixture_path=ROOT / "tests/fixtures/synthetic/seed-responses.json"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    assert fixture["provenance"].startswith("Synthetic")
    store = Store(":memory:")
    store.import_seed(json.loads(Path(seed_path).read_text(encoding="utf-8")))
    engine = Gemini(store, None)
    snapshots = [store.snapshot()]
    source = next(d for d in snapshots[0]["documents"] if d["id"] == "EXPORT-v2")
    for update in fixture.get("source_updates", [{**source, "version": 3}]):
        store.update_source(update)
        snapshots.append(store.snapshot())
    try:
        for snapshot in snapshots:
            for value in [*fixture["drafts"], *fixture["edited_answers"]]:
                draft = Draft.model_validate(value)
                q = store.question(draft.question_id)
                question = {k: q[k] for k in ("id", "topic", "text")}
                for purpose in ("draft", "check"):
                    if purpose == "check" and draft.disposition == "unresolved":
                        continue
                    request = engine.request(purpose, question, snapshot,
                                             draft if purpose == "check" else None)
                    # Edited fixtures have no draft request, because a person supplies their wording.
                    if purpose == "draft" and value in fixture["edited_answers"]:
                        continue
                    check = fixture.get("checks", {}).get(draft.question_id)
                    response = draft if purpose == "draft" else (
                        SemanticCheck.model_validate(check) if check else synthetic_check(draft))
                    run_id = store.record_run(request, response.model_dump_json(), None, "synthetic",
                                               {"provenance": fixture["provenance"]})
                    bundle = capture_bundle(store, run_id)
                    (output / f"synthetic-{bundle.request_fingerprint}.json").write_text(
                        bundle.model_dump_json(indent=2), encoding="utf-8")
    finally:
        store.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification/synthetic-captures")
    parser.add_argument("--seed", type=Path, default=ROOT / "tasks/evidence/seed.json")
    parser.add_argument("--responses", type=Path, default=ROOT / "tests/fixtures/synthetic/seed-responses.json")
    args = parser.parse_args()
    print(f"Synthetic captures written to {prepare(args.output, seed_path=args.seed, fixture_path=args.responses)}; no model calls made.")
