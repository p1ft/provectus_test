"""Shared source, answer, checker and captured-run contracts."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


Nonempty = Annotated[str, Field(min_length=1, max_length=10000, pattern=r"\S")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")


class Passage(StrictModel):
    id: Nonempty
    text: Nonempty


class Document(StrictModel):
    id: Nonempty
    version: Annotated[int, Field(ge=1)]
    date: Nonempty
    status: Literal["current", "superseded"]
    supersedes: str | None
    passages: Annotated[list[Passage], Field(min_length=1)]

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value


class Question(StrictModel):
    id: Nonempty
    topic: Nonempty
    text: Nonempty


class Seed(StrictModel):
    documents: Annotated[list[Document], Field(min_length=1)]
    questions: Annotated[list[Question], Field(min_length=1)]
    owners: dict[str, Nonempty]


class Citation(StrictModel):
    passage_id: Nonempty
    excerpt: Annotated[str, Field(min_length=1, max_length=1000)]


class Conflict(StrictModel):
    passage_ids: Annotated[list[Nonempty], Field(min_length=2, max_length=2)]
    explanation: Nonempty


class Draft(StrictModel):
    question_id: Nonempty
    disposition: Literal["answered", "unresolved"]
    answer: Annotated[str, Field(max_length=2000)]
    citations: Annotated[list[Citation], Field(max_length=20)]
    unresolved_reason: Annotated[str, Field(max_length=2000)]
    conflicts: Annotated[list[Conflict], Field(max_length=20)]

    @model_validator(mode="after")
    def valid_disposition(self):
        if self.disposition == "answered":
            if not self.answer.strip() or not self.citations:
                raise ValueError("Answered output requires wording and citations")
            if self.unresolved_reason.strip():
                raise ValueError("Answered output includes an unresolved reason")
        elif not self.unresolved_reason.strip():
            raise ValueError("Unresolved output requires a reason")
        return self


class Claim(StrictModel):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=1)]
    text: Nonempty
    supporting_passage_ids: Annotated[list[Nonempty], Field(max_length=20)]
    verdict: Literal["supported", "unsupported", "uncertain", "contradicted"]
    explanation: Nonempty


class SemanticCheck(StrictModel):
    question_id: Nonempty
    full_answer: Annotated[str, Field(max_length=2000)]
    all_claims_covered: bool
    answers_question: bool
    citations_relevant: bool
    omitted_claims: Annotated[list[Nonempty], Field(max_length=30)]
    claims: Annotated[list[Claim], Field(max_length=30)]
    conflicts: Annotated[list[Conflict], Field(max_length=20)]

    @model_validator(mode="after")
    def claims_for_wording(self):
        if self.full_answer.strip() and not self.claims:
            raise ValueError("Nonempty answer requires claim coverage")
        return self


class CapturedRun(StrictModel):
    id: int
    question_id: Nonempty
    purpose: Literal["draft", "check"]
    request: dict[str, Any]
    request_fingerprint: Nonempty
    raw_response: str | None
    error: str | None
    origin: Literal["live", "synthetic", "replay_real", "replay_synthetic"]
    original_run: int | None
    metadata: dict[str, Any]
    created_at: Nonempty

    @model_validator(mode="after")
    def exact_request(self):
        if fingerprint(self.request) != self.request_fingerprint:
            raise ValueError("Captured request fingerprint mismatch")
        question = Question.model_validate(self.request.get("question"))
        if (question.id != self.question_id
                or self.request.get("purpose") != self.purpose):
            raise ValueError("Captured request identity mismatch")
        return self


@dataclass
class Response:
    raw: str
    metadata: dict = field(default_factory=dict)
    original_run: int | None = None
