from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ObjectiveSource = Literal["teacher", "course", "inferred"]
StrategyResult = Literal["helped", "failed", "inconclusive"]
DiagnosticOutcome = Literal["incorrect", "partial", "correct", "inconclusive"]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GetLearningStateInput(ToolInput):
    student_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


class StrategyTried(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    result: StrategyResult


class GetLearningStateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str
    has_history: bool
    current_objective: str | None
    objective_source: ObjectiveSource | None
    can_cite_as_teacher_objective: bool
    attempts_count: int = Field(ge=0)
    previous_gaps: list[str]
    strategies_tried: list[StrategyTried]
    recent_evidence: list[str]


class ListTeachingStrategiesInput(ToolInput):
    gap: str = Field(min_length=1, max_length=64)
    exclude_types: list[str] = Field(default_factory=list, max_length=20)


class EligibleStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    summary: str


class ExcludedStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    reason: Literal["previously_failed", "incompatible_gap"]


class ListTeachingStrategiesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gap: str
    eligible: list[EligibleStrategy]
    excluded: list[ExcludedStrategy]
    catalog_incomplete: bool


class RecordLearningEventInput(ToolInput):
    student_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    objective: str = Field(min_length=1, max_length=250)
    objective_source: ObjectiveSource
    activity: str = Field(min_length=1, max_length=120)
    gap: str = Field(min_length=1, max_length=64)
    strategy_type: str = Field(min_length=1, max_length=64)
    strategy_result: StrategyResult
    diagnostic_outcome: DiagnosticOutcome
    evidence: str = Field(min_length=1, max_length=500)

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value[:500]


class RecordLearningEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Literal[True] = True
    event_id: str
    recorded_at: str


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: Literal[False] = False
    error_code: Literal["validation_error", "storage_error", "unknown_tool", "invalid_arguments"]
    message: str
