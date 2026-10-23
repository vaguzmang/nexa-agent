from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


EvidenceType = Literal[
    "closed_ended",
    "open_ended",
    "rubric",
]

EvidenceResult = Literal[
    "meets",
    "partial",
    "does_not_meet",
    "insufficient_evidence",
]

CriterionResult = Literal[
    "meets",
    "partial",
    "does_not_meet",
]

GapType = Literal[
    "misconception",
    "missing_prerequisite",
    "incomplete_procedure",
    "factual_error",
    "unclear_communication",
    "uncertain",
    "none",
]

NextStep = Literal[
    "ask_clarifying",
    "teach",
    "practice",
    "escalate",
]


class Objective(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    # Abierto deliberadamente:
    # NEXA debe poder enseñar cualquier dominio.
    domain: str = Field(
        min_length=1,
        max_length=100,
    )

    skill: str = Field(
        min_length=1,
        max_length=250,
    )


class CriterionEvaluation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(
        min_length=1,
        max_length=250,
    )

    result: CriterionResult


class Evidence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    type: EvidenceType
    result: EvidenceResult

    summary: str = Field(
        min_length=1,
        max_length=1000,
    )

    criteria: list[CriterionEvaluation] | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:

        if self.type == "rubric":

            if self.result == "insufficient_evidence":

                if self.criteria:
                    raise ValueError(
                        "No deben evaluarse criterios cuando "
                        "la evidencia global es insuficiente."
                    )

                return self

            if not self.criteria:
                raise ValueError(
                    "Una evidencia tipo rubric con evidencia "
                    "suficiente requiere criteria."
                )

            results = [
                criterion.result
                for criterion in self.criteria
            ]

            # Reducción canónica de rúbrica:
            #
            # todos meets
            # → meets
            #
            # todos does_not_meet
            # → does_not_meet
            #
            # todos partial
            # → partial
            #
            # cualquier mezcla de resultados
            # → partial

            if all(
                result == "meets"
                for result in results
            ):
                expected = "meets"

            elif all(
                result == "does_not_meet"
                for result in results
            ):
                expected = "does_not_meet"

            else:
                expected = "partial"

            if self.result != expected:
                raise ValueError(
                    "El resultado global de la rúbrica "
                    "no coincide con la reducción de "
                    "sus criterios."
                )

        elif self.criteria:
            raise ValueError(
                "criteria solo puede utilizarse "
                "con evidence.type='rubric'."
            )

        return self


class Understanding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    # Puede ser None únicamente cuando no existe evidencia
    # suficiente para inferir comprensión demostrada.
    demonstrated: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )

    # Puede ser None cuando la evidencia
    # observada cumple completamente el objetivo.
    missing: str | None = Field(
        default=None,
        max_length=1000,
    )


class LearningGap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    present: bool
    type: GapType

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_gap(self) -> Self:

        if self.present:

            if self.type == "none":
                raise ValueError(
                    "Un gap presente no puede "
                    "tener type='none'."
                )

            if not self.description:
                raise ValueError(
                    "Un gap presente requiere "
                    "description."
                )

        else:

            if self.type != "none":
                raise ValueError(
                    "Un gap ausente debe tener "
                    "type='none'."
                )

            if self.description:
                raise ValueError(
                    "Un gap ausente no debe "
                    "tener description."
                )

        return self


class DiagnosisResult(BaseModel):
    """
    Contrato de la etapa DIAGNOSTICAR.

    Evalúa evidencia del turno respecto de un
    objetivo de aprendizaje.

    Este contrato NO determina dominio/mastery.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: Literal[
        "diag.v1.1"
    ] = "diag.v1.1"

    objective: Objective
    evidence: Evidence
    understanding: Understanding
    gap: LearningGap
    next_step: NextStep

    @model_validator(mode="after")
    def validate_learning_flow(self) -> Self:

        result = self.evidence.result

        # ----------------------------------------
        # Evidencia insuficiente
        # ----------------------------------------

        if result == "insufficient_evidence":

            if self.gap.present:
                raise ValueError(
                    "No puede declararse una brecha "
                    "cuando la evidencia es insuficiente."
                )

            if self.next_step not in {
                "ask_clarifying",
                "escalate",
            }:
                raise ValueError(
                    "La evidencia insuficiente debe "
                    "conducir a ask_clarifying "
                    "o escalate."
                )

        elif self.understanding.demonstrated is None:
            raise ValueError(
                "understanding.demonstrated solo puede ser None "
                "cuando evidence.result='insufficient_evidence'."
            )

        # ----------------------------------------
        # La evidencia cumple este objetivo
        # ----------------------------------------

        elif result == "meets":

            if self.gap.present:
                raise ValueError(
                    "evidence.result='meets' no puede "
                    "coexistir con gap.present=true."
                )

            if self.understanding.missing:
                raise ValueError(
                    "Si evidence.result='meets', "
                    "understanding.missing debe ser None. "
                    "Si existe una carencia observable, "
                    "el resultado no debe ser meets."
                )

            if self.next_step not in {
                "practice",
                "ask_clarifying",
            }:
                raise ValueError(
                    "Una evidencia que cumple no autoriza "
                    "mastery ni cierre del aprendizaje. "
                    "Debe confirmarse mediante práctica "
                    "o aclaración."
                )

        # ----------------------------------------
        # Hay evidencia de dificultad
        # ----------------------------------------

        elif result in {
            "partial",
            "does_not_meet",
        }:

            if not self.gap.present:
                raise ValueError(
                    "partial o does_not_meet requiere "
                    "una brecha explícita."
                )

            if not self.understanding.missing:
                raise ValueError(
                    "partial o does_not_meet requiere "
                    "describir qué comprensión falta."
                )

            # Si todavía desconocemos la causa,
            # NEXA no debe inventarla.
            if self.gap.type == "uncertain":

                if self.next_step not in {
                    "ask_clarifying",
                    "escalate",
                }:
                    raise ValueError(
                        "Un gap de tipo uncertain debe "
                        "conducir a ask_clarifying "
                        "o escalate."
                    )

            else:

                if self.next_step not in {
                    "teach",
                    "practice",
                    "escalate",
                }:
                    raise ValueError(
                        "Una brecha identificada debe "
                        "conducir a teach, practice "
                        "o escalate."
                    )

        return self
