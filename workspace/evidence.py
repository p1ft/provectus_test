"""Conservative evidence and authority validation."""

from workspace.schemas import (
    CapturedRun,
    Citation,
    Claim,
    Conflict,
    Document,
    Draft,
    Nonempty,
    Passage,
    Question,
    Seed,
    SemanticCheck,
    StrictModel,
    fingerprint,
    json_text,
)

__all__ = [
    "CapturedRun",
    "Citation",
    "Claim",
    "Conflict",
    "Document",
    "Draft",
    "Nonempty",
    "Passage",
    "Question",
    "Seed",
    "SemanticCheck",
    "StrictModel",
    "conflict_errors",
    "fingerprint",
    "json_text",
    "passage_index",
    "reference_errors",
    "replaced_evidence",
    "replaces",
    "semantic_errors",
    "validate_seed",
]


def validate_seed(value):
    seed = Seed.model_validate(value)
    documents = seed.model_dump()["documents"]
    ids = [d["id"] for d in documents]
    passages = [p["id"] for d in documents for p in d["passages"]]
    questions = [q.id for q in seed.questions]
    for label, values in [("document", ids), ("passage", passages), ("question", questions)]:
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {label} ID")
    for document in documents:
        if document["supersedes"] is not None and document["supersedes"] not in ids:
            raise ValueError("Missing supersedes target")
    graph = {d["id"]: d["supersedes"] for d in documents}
    for doc_id in ids:
        seen = set()
        while doc_id is not None:
            if doc_id in seen:
                raise ValueError("Supersession cycle")
            seen.add(doc_id)
            doc_id = graph[doc_id]
    if any(q.topic not in seed.owners for q in seed.questions):
        raise ValueError("Missing topic reviewer mapping")
    return seed.model_dump()


def passage_index(snapshot):
    return {
        p["id"]: (d, p)
        for d in snapshot["documents"]
        for p in d["passages"]
    }


def replaces(snapshot, newer, older):
    graph = {d["id"]: d["supersedes"] for d in snapshot["documents"]}
    parent = graph.get(newer)
    seen = set()
    while parent is not None:
        if parent in seen:
            raise ValueError("Supersession cycle")
        seen.add(parent)
        if parent == older:
            return True
        parent = graph.get(parent)
    return False


def reference_errors(draft, question_id, snapshot):
    errors = []
    index = passage_index(snapshot)
    if draft.question_id != question_id:
        errors.append("Response question ID does not match")
    if draft.disposition == "unresolved":
        errors.append(draft.unresolved_reason)
    ids = [c.passage_id for c in draft.citations]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate citation")
    for citation in draft.citations:
        if citation.passage_id not in index:
            errors.append(f"Missing passage: {citation.passage_id}")
            continue
        doc, passage = index[citation.passage_id]
        if not snapshot["availability"][doc["id"]]:
            errors.append(f"Source unavailable: {doc['id']}")
        if not citation.excerpt.strip() or citation.excerpt not in passage["text"]:
            errors.append(f"Excerpt is not verbatim: {citation.passage_id}")
        if any(replaces(snapshot, d["id"], doc["id"])
               for d in snapshot["documents"]):
            errors.append(f"Supporting passage has been replaced: {citation.passage_id}")
    errors.extend(conflict_errors(draft.conflicts, snapshot))
    return errors


def conflict_errors(conflicts, snapshot):
    errors = []
    index = passage_index(snapshot)
    for conflict in conflicts:
        left, right = conflict.passage_ids
        if left not in index or right not in index or left == right:
            errors.append("Invalid conflicting passage references")
            continue
        a, b = index[left][0]["id"], index[right][0]["id"]
        if not (replaces(snapshot, a, b) or replaces(snapshot, b, a)):
            errors.append(f"Unresolved source conflict: {left} / {right}")
    return errors


def semantic_errors(draft, check, snapshot):
    errors = []
    if check.question_id != draft.question_id or check.full_answer != draft.answer:
        errors.append("Semantic check does not match the exact answer")
    if not check.all_claims_covered or check.omitted_claims:
        errors.append("Semantic check has missing claim coverage")
    if not check.answers_question:
        errors.append("Answer does not answer the question")
    if not check.citations_relevant:
        errors.append("Citations are irrelevant to the answer")
    cited = {c.passage_id for c in draft.citations}
    used = set()
    covered = set()
    for claim in check.claims:
        if (claim.end > len(draft.answer) or claim.start >= claim.end
                or draft.answer[claim.start:claim.end] != claim.text):
            # The model supplies exact claim text; derive a unique span rather than
            # relying on its character arithmetic. Ambiguous or invented text fails.
            positions = [i for i in range(len(draft.answer)) if draft.answer.startswith(claim.text, i)]
            if len(positions) == 1:
                covered.update(range(positions[0], positions[0] + len(claim.text)))
            else:
                errors.append("Invalid claim span")
        else:
            covered.update(range(claim.start, claim.end))
        if claim.verdict != "supported":
            errors.append(f"{claim.verdict.capitalize()} claim: {claim.text}")
        if (not claim.supporting_passage_ids
                or not set(claim.supporting_passage_ids) <= cited):
            errors.append("Claim support must use the answer's cited passages")
        used.update(claim.supporting_passage_ids)
    if any(i not in covered for i, char in enumerate(draft.answer) if not char.isspace()):
        errors.append("Semantic check omitted answer text")
    if cited - used:
        errors.append("Citations lack claim support")
    errors.extend(conflict_errors(check.conflicts, snapshot))
    return errors


def replaced_evidence(draft, snapshot):
    """Include all explicitly replaced passages; never rely on model conflict labels."""
    index = passage_index(snapshot)
    documents = {index[c.passage_id][0]["id"] for c in draft.citations
                 if c.passage_id in index}
    return [
        {"passage_id": p["id"], "excerpt": p["text"], "role": "replaced"}
        for d in snapshot["documents"]
        if any(replaces(snapshot, current, d["id"]) for current in documents)
        for p in d["passages"]
    ]
