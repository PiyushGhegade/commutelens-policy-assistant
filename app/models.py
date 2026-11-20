from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Section(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    title: str = Field(min_length=3, max_length=100)
    text: str = Field(min_length=10, max_length=900)


class Policy(StrictModel):
    document: str = Field(min_length=3, max_length=100)
    version: int = Field(ge=1)
    sections: list[Section] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def unique_sections(self):
        if len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError("Section IDs must be unique.")
        return self


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1200)
    retrieval: Literal["dense", "hybrid"] = "hybrid"


class AnswerPoint(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    section_ids: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def valid_references(self):
        if len(self.section_ids) != len(set(self.section_ids)):
            raise ValueError("Duplicate evidence")
        # Citation numbers belong to the server, never the model.
        if "[" in self.text or "]" in self.text:
            raise ValueError("Put evidence IDs in section_ids, not in answer text")
        return self


class PolicyResponse(StrictModel):
    """Model-written conclusion with evidence references, never model-written quotes."""

    verdict: Literal["yes", "no", "conditional", "information", "not_covered"]
    points: list[AnswerPoint] = Field(max_length=3)

    @property
    def section_ids(self):
        return list(dict.fromkeys(sid for point in self.points for sid in point.section_ids))

    @property
    def not_covered(self):
        return self.verdict == "not_covered"

    @model_validator(mode="after")
    def consistent(self):
        if self.not_covered != (not self.points):
            raise ValueError("Only not_covered may have no answer points")
        if len(self.section_ids) > 3:
            raise ValueError("At most three distinct evidence sections")
        return self


class Citation(StrictModel):
    document: str
    version: int
    section_id: str
    section: str
    quote: str


class LLMAttempt(StrictModel):
    model: str
    status: str
    latency_ms: float
    http_status: int | None = None


class Answer(StrictModel):
    status: Literal["answered", "not_covered", "try_again"]
    answer: str
    citations: list[Citation] = Field(default_factory=list, max_length=3)
    company: str
    version: int | None = None
    llm_calls: int = 0
    latency_ms: float = 0
    retrieval_ms: float = 0
    retrieved_ids: list[str] = Field(default_factory=list)
    provider: str
    reason: str = ""
    request_id: str = ""
    llm_model: str = ""
    llm_attempts: list[LLMAttempt] = Field(default_factory=list, max_length=2)
    answer_style: Literal["direct", "policy_excerpt"] = "direct"
    verdict: Literal["yes", "no", "conditional", "information", "not_covered"] | None = None
