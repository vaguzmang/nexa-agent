from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from s2.agent import run_learning_agent
from s2.tools import get_learning_state
from s3.intake import classify_learning_intake, resolve_objective
from s3.metrics import build_task_metrics, persist_task_metrics
from s3.safeguarding import assess_safeguarding


@dataclass(frozen=True)
class StudentTurnResult:
    response: str
    diagnosis: object | dict
    diagnosis_meta: object | None
    agent_meta: object
    intake: object
    objective_resolution: object
    safeguarding: object
    metrics: dict




def _difficulty_relation_for_resolution(action):
    if action in {"create_inferred", "switch_objective"}:
        return "new_context"
    if action in {"continue_existing", "resume_suspended", "reopen_closed"}:
        return "same_context"
    return "unknown"

def _synthetic_non_evaluable_context(objective, intake, message):
    return {
        "schema_version": "diag.v1.1",
        "objective": {
            "domain": "Conversación de aprendizaje",
            "skill": objective,
        },
        "evidence": {
            "type": "open_ended",
            "result": "insufficient_evidence",
            "summary": (
                f"Turno no evaluable ({intake.turn_type}); no se ejecutó diag.v1.1. "
                "El alumno solicitó apoyo o inició una consulta de aprendizaje."
            ),
            "criteria": None,
        },
        "understanding": {"demonstrated": None, "missing": None},
        "gap": {"present": False, "type": "none", "description": None},
        "next_step": "ask_clarifying",
    }


def run_student_turn(
    *,
    student_id,
    message,
    activity=None,
    client=None,
    db_path=None,
    task_id=None,
    started_at=None,
    objective_id=None,
    objective_source=None,
    objective_label=None,
    institution_id=None,
    subject_family=None,
    objective_family=None,
    cost_optimized=True,
):
    resolved_task_id = task_id or f"task-{uuid4()}"
    started = started_at or datetime.now(timezone.utc).isoformat()
    safeguarding = assess_safeguarding(message)
    state = get_learning_state(student_id, db_path=db_path)
    safe_state = {} if state.get("ok") is False else state

    intake = classify_learning_intake(
        message=message,
        activity=activity,
        state=safe_state,
    )
    resolution = resolve_objective(
        student_id=student_id,
        message=message,
        activity=activity,
        intake=intake,
        state=safe_state,
        objective_id=objective_id,
        objective_source=objective_source,
        objective_label=objective_label,
        db_path=db_path,
    )

    diagnosis_meta = None
    if intake.should_diagnose:
        from grok_client import analizar_respuesta
        target = intake.diagnosis_target or resolution.objective
        diagnosis, diagnosis_meta = analizar_respuesta(target, message, client=client)
    else:
        diagnosis = _synthetic_non_evaluable_context(
            resolution.objective,
            intake,
            message,
        )

    activity_for_agent = (
        str(activity or "").strip()
        or intake.diagnosis_target
        or resolution.objective
    )

    response, agent_meta = run_learning_agent(
        student_id=student_id,
        activity=activity_for_agent,
        student_answer=message,
        diagnosis=diagnosis,
        objective_id=resolution.objective_id,
        objective_source=resolution.objective_source,
        task_id=resolved_task_id,
        turn_type_override=intake.turn_type,
        interaction_need_override=intake.interaction_need,
        objective_action=resolution.action,
        difficulty_relation=_difficulty_relation_for_resolution(resolution.action),
        safeguarding_context=safeguarding.as_dict(),
        institution_id=institution_id,
        subject_family=subject_family,
        objective_family=objective_family,
        cost_optimized=cost_optimized,
        preloaded_state=safe_state,
        client=client,
        db_path=db_path,
    )

    metrics = build_task_metrics(
        task_id=resolved_task_id,
        diagnosis_meta=diagnosis_meta,
        agent_meta=agent_meta,
        student_id=student_id,
        episode_id=agent_meta.episode_id,
        objective_id=resolution.objective_id,
        started_at=started,
        diagnosis_skipped=(diagnosis_meta is None),
        cost_optimized=cost_optimized,
    )
    persist_task_metrics(metrics, db_path=db_path)

    return StudentTurnResult(
        response=response,
        diagnosis=diagnosis,
        diagnosis_meta=diagnosis_meta,
        agent_meta=agent_meta,
        intake=intake,
        objective_resolution=resolution,
        safeguarding=safeguarding,
        metrics=metrics,
    )
