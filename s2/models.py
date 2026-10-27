from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ObjectiveSource = Literal["teacher", "course", "inferred"]
StrategyResult = Literal["helped", "failed", "inconclusive"]
DiagnosticOutcome = Literal["incorrect", "partial", "correct", "inconclusive"]
LearningEventType = Literal["strategy_applied", "strategy_evaluated", "strategy_interrupted", "legacy"]
ResultReason = Literal[
    "same_error_persists",
    "partial_improvement",
    "objective_met",
    "mixed_evidence",
    "insufficient_evidence",
    "objective_changed",
    "no_attempt",
    "help_requested_before_attempt",
    "topic_switched_before_attempt",
]
TurnType = Literal[
    "attempt",
    "question",
    "request_hint",
    "request_explanation",
    "confirmation",
    "metacognitive",
    "off_topic",
    "mixed",
    "learning_request",
]
TaskType = Literal["procedural", "conceptual", "mixed", "unknown"]
ResponseFormat = Literal["open", "closed", "not_applicable", "unknown"]
EvidenceMode = Literal["independent", "guided", "copied_or_prompted", "unknown", "not_applicable"]
SupportLevel = Literal["none", "low", "medium", "high", "unknown", "not_applicable"]
DifficultyRelation = Literal[
    "same_context",
    "similar_context",
    "transfer_context",
    "higher_difficulty",
    "new_context",
    "unknown",
]
LearningDelta = Literal[
    "retained",
    "partial_recall",
    "regression_signal",
    "new_gap",
    "transfer_gap",
    "no_evaluable_attempt",
]
InteractionNeed = Literal[
    "diagnostic_gap",
    "explanation",
    "hint",
    "reassessment",
    "practice",
    "confirmation",
    "exploration",
    "none",
]

EpisodeStatus = Literal[
    "active",
    "awaiting_evidence",
    "evidence_confirmed",
    "closed",
    "reopened",
    "suspended",
]


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
    objective_id: str | None = None
    result_reason: ResultReason | None = None
    applied_event_id: str | None = None
    evaluated_event_id: str | None = None
    terminal_event_type: str | None = None
    incoming_evidence_support: SupportLevel | None = None
    intervention_support_level: SupportLevel | None = None
    planner_top_strategy: str | None = None
    selection_mode: str | None = None


class PendingIntervention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applied_event_id: str
    objective_id: str
    objective: str
    objective_source: ObjectiveSource
    strategy_type: str
    diagnostic_outcome: DiagnosticOutcome
    gap: str
    recorded_at: str
    episode_id: str | None = None


class LearningEpisodeState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    objective_id: str
    objective: str
    objective_source: ObjectiveSource
    status: EpisodeStatus
    started_at: str
    updated_at: str
    closed_at: str | None = None
    reopen_count: int = Field(ge=0)
    last_learning_delta: LearningDelta | None = None
    last_evidence_mode: EvidenceMode | None = None


class LearningDeltaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective_id: str
    episode_id: str | None = None
    delta: LearningDelta
    recorded_at: str


class ComponentProgressItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    result: str


class GetLearningStateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str
    has_history: bool
    current_objective: str | None
    current_objective_id: str | None = None
    current_activity: str | None = None
    objective_source: ObjectiveSource | None
    can_cite_as_teacher_objective: bool
    attempts_count: int = Field(ge=0)
    previous_gaps: list[str]
    strategies_tried: list[StrategyTried]
    recent_evidence: list[str]
    pending_intervention: PendingIntervention | None = None
    active_episode: LearningEpisodeState | None = None
    previous_confirmed_evidence: list[str] = Field(default_factory=list)
    learning_deltas: list[LearningDeltaItem] = Field(default_factory=list)
    component_progress: list[ComponentProgressItem] = Field(default_factory=list)


class ListTeachingStrategiesInput(ToolInput):
    gap: str = Field(min_length=1, max_length=64)
    exclude_types: list[str] = Field(default_factory=list, max_length=20)
    interaction_need: InteractionNeed | None = None
    student_id: str | None = Field(default=None, max_length=64)
    objective_id: str | None = Field(default=None, max_length=120)
    task_type: TaskType | None = None
    response_format: ResponseFormat | None = None
    retrieval_required: bool | None = None
    transfer_context: bool | None = None
    support_level: SupportLevel | None = None
    institution_id: str | None = Field(default=None, max_length=120)
    subject_family: str | None = Field(default=None, max_length=80)
    objective_family: str | None = Field(default=None, max_length=120)


class EligibleStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    summary: str
    priority_score: float | None = None
    rationale: str | None = None
    evidence_basis: str | None = None
    recommended_support_level: str | None = None
    institutional_confidence: str | None = None


class ExcludedStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    reason: Literal["previously_failed", "incompatible_gap", "incompatible_need"]


class ListTeachingStrategiesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gap: str
    interaction_need: InteractionNeed | None = None
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

    # Campos S3 internos. No tienen que exponerse al LLM como argumentos de tool.
    event_type: LearningEventType | None = None
    objective_id: str | None = Field(default=None, min_length=1, max_length=120)
    evaluates_event_id: str | None = Field(default=None, min_length=1, max_length=64)
    result_reason: ResultReason | None = None
    episode_id: str | None = Field(default=None, min_length=1, max_length=80)
    turn_type: TurnType | None = None
    task_type: TaskType | None = None
    response_format: ResponseFormat | None = None
    retrieval_required: bool | None = None
    transfer_context: bool | None = None
    evidence_mode: EvidenceMode | None = None
    independent_evidence_eligible: bool | None = None
    support_level: SupportLevel | None = None
    intervention_support_level: SupportLevel | None = None
    planner_top_strategy: str | None = Field(default=None, max_length=64)
    selection_mode: Literal["planner_top", "agent_override", "no_planner_context"] | None = None
    selection_reason: str | None = Field(default=None, max_length=500)
    selection_reason_code: Literal[
        "planner_top",
        "interaction_need_mismatch",
        "prior_strategy_failed_same_objective",
        "student_asked_explicit_form",
        "task_type_mismatch",
        "insufficient_planner_confidence",
        "avoid_repeat_explanation",
        "other",
    ] | None = None
    institution_id: str | None = Field(default=None, max_length=120)
    subject_family: str | None = Field(default=None, max_length=80)
    objective_family: str | None = Field(default=None, max_length=120)
    learning_delta: LearningDelta | None = None
    difficulty_relation: DifficultyRelation | None = None
    evidence_profile: str | None = Field(default=None, max_length=4000)

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
