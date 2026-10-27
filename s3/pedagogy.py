import os
from dataclasses import asdict, dataclass

from .effectiveness import build_strategy_effectiveness_profile


@dataclass(frozen=True)
class StrategyPlanItem:
    strategy_type: str
    priority_score: float
    rationale: str
    evidence_basis: str
    recommended_support_level: str
    institutional_confidence: str | None = None

    def as_dict(self):
        return asdict(self)


STRATEGY_PEDAGOGY = {
    "probe": {"task_types": {"conceptual", "mixed", "unknown"}, "support": "low"},
    "hint": {"task_types": {"procedural", "conceptual", "mixed", "unknown"}, "support": "low"},
    "concept_explanation": {"task_types": {"conceptual", "mixed", "unknown"}, "support": "medium"},
    "analogy": {"task_types": {"conceptual", "mixed"}, "support": "medium"},
    "contrast_example": {"task_types": {"conceptual", "mixed", "unknown"}, "support": "medium"},
    "worked_example": {"task_types": {"procedural", "mixed", "unknown"}, "support": "high"},
    "guided_practice": {"task_types": {"procedural", "mixed", "unknown"}, "support": "medium"},
    "prerequisite_review": {"task_types": {"procedural", "conceptual", "mixed", "unknown"}, "support": "high"},
    "independent_practice": {"task_types": {"procedural", "conceptual", "mixed", "unknown"}, "support": "none"},
}


def _individual_bonus(entry):
    if not entry or entry.get("score") is None:
        return 0.0, "sin evidencia individual suficiente"
    decisive = int(entry.get("decisive") or 0)
    if decisive < 2:
        return 0.0, "evidencia individual preliminar"
    score = float(entry["score"])
    return (score - 0.5) * 2 * 0.60, (
        f"individual: {decisive} outcomes decisivos, "
        f"{entry.get('independent_confirmations',0)} confirmaciones independientes"
    )


def _institutional_bonus(entry):
    if not entry:
        return 0.0, None, "sin evidencia institucional comparable"
    confidence = entry.get("confidence") or "insufficient_evidence"
    detail = (
        f"institucional {confidence}: {entry.get('unique_students',0)} estudiantes únicos, "
        f"{entry.get('decisive',0)} outcomes independientes decisivos"
    )
    mode = (os.getenv("NEXA_INSTITUTIONAL_EVIDENCE_MODE") or "shadow").strip().lower()
    if mode != "advisory" or confidence == "insufficient_evidence":
        return 0.0, confidence, detail
    score = entry.get("score")
    if score is None:
        return 0.0, confidence, detail
    weight = 0.12 if confidence == "emerging_pattern" else 0.20
    return (float(score) - 0.5) * 2 * weight, confidence, detail


def plan_strategy_candidates(
    *, eligible, student_id=None, objective_id=None, task_type=None,
    support_level=None, institution_id=None, subject_family=None,
    objective_family=None, db_path=None,
):
    profile = build_strategy_effectiveness_profile(
        student_id=student_id,
        objective_id=objective_id,
        task_type=task_type,
        institution_id=institution_id,
        subject_family=subject_family,
        objective_family=objective_family,
        db_path=db_path,
    )
    individual = profile["individual"]
    institutional = profile["institutional"]
    planned = []

    for item in eligible:
        strategy = item["type"]
        meta = STRATEGY_PEDAGOGY.get(
            strategy, {"task_types": {"unknown"}, "support": "unknown"}
        )
        score = 0.5
        reasons, basis = [], []

        if task_type and task_type in meta["task_types"]:
            score += 0.10
            reasons.append(f"compatible con tarea {task_type}")
        elif task_type and "unknown" not in meta["task_types"]:
            score -= 0.08
            reasons.append(f"menos específica para tarea {task_type}")

        ind_bonus, ind_text = _individual_bonus(individual.get(strategy))
        score += ind_bonus
        if individual.get(strategy):
            basis.append(ind_text)

        inst_bonus, inst_confidence, inst_text = _institutional_bonus(
            institutional.get(strategy)
        )
        score += inst_bonus
        # Shadow o insuficiente: NO llega como pista a Grok.
        if inst_bonus != 0.0:
            basis.append(inst_text)

        if support_level in {"high", "medium"} and meta["support"] == "none":
            score -= 0.08
            reasons.append("requiere menos apoyo que el contexto entrante")

        planned.append(StrategyPlanItem(
            strategy_type=strategy,
            priority_score=round(max(0.0, min(1.0, score)), 4),
            rationale="; ".join(reasons) or "candidato pedagógico elegible",
            evidence_basis=" | ".join(basis) or "sin evidencia utilizable para ranking",
            recommended_support_level=meta["support"],
            institutional_confidence=inst_confidence,
        ))

    planned.sort(key=lambda x: (-x.priority_score, x.strategy_type))
    return [item.as_dict() for item in planned]

