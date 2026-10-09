"""Exercise the separate starter extension with labelled synthetic exact replay only."""

import argparse
import copy
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prepare_verification import prepare
from workspace.gemini import FileReplayTransport, Gemini
from workspace.service import ReviewBlocked, Service
from workspace.store import Store

SEED = ROOT / "exercises/evidence/seed.json"
RESPONSES = ROOT / "tests/fixtures/synthetic/extension-responses.json"


def verify(output):
    output = Path(output).resolve()
    if not any(output.is_relative_to(ROOT / p) for p in (".tmp", "artifacts/verification")):
        raise ValueError("Extension verification requires an isolated output directory")
    output.mkdir(parents=True, exist_ok=True)
    captures = prepare(output / "synthetic-captures", seed_path=SEED, fixture_path=RESPONSES)
    database = output / f"extension-{uuid4().hex}.sqlite3"
    store = Store(database)
    store.import_seed(json.loads(SEED.read_text(encoding="utf-8")))
    expected = json.loads((SEED.parent / "expected-results.json").read_text(encoding="utf-8"))
    service = Service(store, Gemini(store, FileReplayTransport(captures, synthetic=True)))
    results = []

    def record(case, passed, observed):
        results.append({"case": case, "status": "pass" if passed else "fail",
                        "expected": expected[case], "observed": observed})

    def approve(revision):
        return service.approve(revision, reviewer_name="Synthetic demonstration reviewer",
                               reviewer_role="Product reviewer", evidence_confirmed=True,
                               note="Synthetic extension exercise; not a working approval")

    try:
        supported = service.generate("EXT-SUPPORTED")
        supported_row = store.question("EXT-SUPPORTED")
        record("supported", supported is not None and supported_row["status"] == "answered"
               and any(c["passage_id"] == expected["supported"]["source"]
                       for c in store.revision(supported)["citations"]), supported_row["status"])
        unknown = service.generate("EXT-UNKNOWN")
        unknown_row = store.question("EXT-UNKNOWN")
        record("unsupported", unknown is not None and unknown_row["status"] == "unresolved"
               and unknown_row["reviewer"] == expected["unsupported"]["owner"]
               and store.revision(unknown)["draft"].unresolved_reason == expected["unsupported"]["reason"],
               {"status": unknown_row["status"], "reviewer": unknown_row["reviewer"]})
        conflict = service.generate("EXT-CONFLICT")
        try:
            service.approve(conflict, reviewer_name="Synthetic demonstration reviewer",
                            reviewer_role="Billing reviewer", evidence_confirmed=True)
            blocked = False
        except ReviewBlocked:
            blocked = True
        evidence = store.revision(conflict)["citations"]
        ids = {c["passage_id"] for c in evidence}
        record("conflicting_source", blocked and store.question("EXT-CONFLICT")["status"] == "unresolved"
               and set(expected["conflicting_source"]["sources"]) <= ids,
               {"approval_blocked": blocked, "displayed_sources": sorted(ids)})
        text = supported_row["text"]
        excluded_before = not service.reuse(text)["eligible"]
        approve(supported)
        answer = store.revision(supported)["draft"]
        pending = copy.deepcopy(answer.model_dump())
        pending["answer"] += " Pending unsupported addition."
        service.edit("EXT-SUPPORTED", pending)
        reused = service.reuse(store.question("EXT-REUSE")["text"])
        record("approved_reuse", excluded_before and reused["eligible"] and reused["answer"] == answer.answer
               and store.question("EXT-REUSE")["status"] == "pending", reused["answer"])
        changed = service.generate("EXT-CHANGE")
        approve(changed)
        old_evidence = store.revision(changed)["citations"]
        update = json.loads(RESPONSES.read_text(encoding="utf-8"))["source_updates"][0]
        store.update_source(update)
        status = store.question("EXT-CHANGE")["status"]
        excluded_after = not service.reuse(store.question("EXT-CHANGE")["text"])["eligible"]
        retained = store.revision(changed)["citations"] == old_evidence
        fresh = service.edit("EXT-CHANGE", store.revision(changed)["draft"])
        errors = service.validate(fresh)
        approve(fresh)
        reused = service.reuse(store.question("EXT-CHANGE")["text"])
        record("changed_source", status == "review_required" and excluded_after and retained
               and not errors and reused["eligible"],
               {"status_after_change": status, "reuse_blocked": excluded_after,
                "old_evidence_retained": retained, "fresh_approval_reusable": reused["eligible"]})
    finally:
        store.close()
    report = {"provenance": "Synthetic exact replay; no credentials or external model calls. Approvals are demonstrations.",
              "database": str(database), "results": results,
              "real_extension_verification": {"status": "unverified",
                  "reason": "No saved real extension captures exist; new external model calls are prohibited for this task."}}
    (output / "extension-results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp/extension-verification")
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if all(r["status"] == "pass" for r in report["results"]) else 1)
