import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .models import (
    ComponentProgressItem,
    GetLearningStateInput,
    GetLearningStateResult,
    LearningDeltaItem,
    LearningEpisodeState,
    ListTeachingStrategiesInput,
    ListTeachingStrategiesResult,
    PendingIntervention,
    RecordLearningEventInput,
    RecordLearningEventResult,
    ToolError,
)
from .storage import connect, ensure_database
from s3.pedagogy import plan_strategy_candidates


def _error(code, message):
    return ToolError(error_code=code, message=message).model_dump()


def _recent_unique(values, limit=5):
    output = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def _safe_profile(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("result") or "").strip()
        if name and value:
            result.append(ComponentProgressItem(name=name, result=value))
    return result


def get_learning_state(student_id, *, db_path=None):
    """Proyección de memoria sobre eventos, observaciones y episodio actual."""
    try:
        data = GetLearningStateInput(student_id=student_id)
    except ValidationError:
        return _error(
            "validation_error",
            "student_id es obligatorio y debe ser un identificador opaco válido de hasta 64 caracteres.",
        )

    try:
        ensure_database(db_path)
        with closing(connect(db_path)) as connection:
            rows = connection.execute(
                """
                SELECT event_id, recorded_at, objective, objective_source, activity,
                       gap, strategy_type, strategy_result, diagnostic_outcome, evidence,
                       event_type, objective_id, evaluates_event_id, result_reason,
                       episode_id, turn_type, task_type, evidence_mode, support_level,
                       intervention_support_level, planner_top_strategy, selection_mode,
                       selection_reason, learning_delta, difficulty_relation, evidence_profile
                FROM learning_events
                WHERE student_id = ?
                ORDER BY recorded_at DESC
                """,
                (data.student_id,),
            ).fetchall()

            episode_row = connection.execute(
                """
                SELECT * FROM learning_episodes
                WHERE student_id = ?
                  AND status IN ('active', 'awaiting_evidence', 'reopened', 'evidence_confirmed')
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (data.student_id,),
            ).fetchone()

            observations = connection.execute(
                """
                SELECT * FROM learning_observations
                WHERE student_id = ?
                ORDER BY observed_at DESC
                LIMIT 8
                """,
                (data.student_id,),
            ).fetchall()

            confirmed = connection.execute(
                """
                SELECT evaluated.objective_id, evaluated.evidence
                FROM learning_events AS evaluated
                JOIN learning_events AS applied
                  ON applied.event_id = evaluated.evaluates_event_id
                WHERE evaluated.student_id = ?
                  AND evaluated.event_type = 'strategy_evaluated'
                  AND evaluated.strategy_result = 'helped'
                  AND evaluated.result_reason = 'objective_met'
                  AND applied.strategy_type = 'independent_practice'
                ORDER BY evaluated.recorded_at DESC
                LIMIT 3
                """,
                (data.student_id,),
            ).fetchall()
    except (sqlite3.Error, OSError) as error:
        return _error(
            "storage_error",
            f"No fue posible consultar la memoria de aprendizaje: {type(error).__name__}.",
        )

    if not rows and episode_row is None and not observations:
        return GetLearningStateResult(
            student_id=data.student_id,
            has_history=False,
            current_objective=None,
            current_objective_id=None,
            current_activity=None,
            objective_source=None,
            can_cite_as_teacher_objective=False,
            attempts_count=0,
            previous_gaps=[],
            strategies_tried=[],
            recent_evidence=[],
            pending_intervention=None,
            active_episode=None,
            previous_confirmed_evidence=[],
            learning_deltas=[],
            component_progress=[],
        ).model_dump()

    terminal_by_applied = {
        row["evaluates_event_id"]: row
        for row in rows
        if row["event_type"] in {"strategy_evaluated", "strategy_interrupted"}
        and row["evaluates_event_id"]
    }
    applied_rows = [
        row for row in rows if row["event_type"] in {"strategy_applied", "legacy"}
    ]
    latest = applied_rows[0] if applied_rows else (rows[0] if rows else None)

    previous_gaps = _recent_unique(
        [row["gap"] for row in applied_rows if row["gap"] and row["gap"] != "none"],
        limit=8,
    )

    strategies = []
    seen = set()
    for row in applied_rows:
        applied_event_id = row["event_id"]
        evaluation = terminal_by_applied.get(applied_event_id)
        projected_result = evaluation["strategy_result"] if evaluation is not None else row["strategy_result"]
        projected_reason = evaluation["result_reason"] if evaluation is not None else row["result_reason"]
        evaluated_event_id = evaluation["event_id"] if evaluation is not None else None
        key = (row["objective_id"] or "__legacy__", row["strategy_type"])
        if key in seen:
            continue
        seen.add(key)
        strategies.append(
            {
                "type": row["strategy_type"],
                "result": projected_result,
                "objective_id": row["objective_id"],
                "result_reason": projected_reason,
                "applied_event_id": applied_event_id,
                "evaluated_event_id": evaluated_event_id,
                "terminal_event_type": evaluation["event_type"] if evaluation is not None else None,
                "incoming_evidence_support": row["support_level"],
                "intervention_support_level": row["intervention_support_level"],
                "planner_top_strategy": row["planner_top_strategy"],
                "selection_mode": row["selection_mode"],
            }
        )
        if len(strategies) >= 10:
            break

    pending_row = next(
        (
            row for row in applied_rows
            if row["event_type"] == "strategy_applied"
            and row["objective_id"]
            and row["event_id"] not in terminal_by_applied
        ),
        None,
    )
    pending = None
    if pending_row is not None:
        pending = PendingIntervention(
            applied_event_id=pending_row["event_id"],
            objective_id=pending_row["objective_id"],
            objective=pending_row["objective"],
            objective_source=pending_row["objective_source"],
            strategy_type=pending_row["strategy_type"],
            diagnostic_outcome=pending_row["diagnostic_outcome"],
            gap=pending_row["gap"],
            recorded_at=pending_row["recorded_at"],
            episode_id=pending_row["episode_id"],
        )

    active_episode = None
    if episode_row is not None:
        active_episode = LearningEpisodeState(
            episode_id=episode_row["episode_id"],
            objective_id=episode_row["objective_id"],
            objective=episode_row["objective"],
            objective_source=episode_row["objective_source"],
            status=episode_row["status"],
            started_at=episode_row["started_at"],
            updated_at=episode_row["updated_at"],
            closed_at=episode_row["closed_at"],
            reopen_count=episode_row["reopen_count"],
            last_learning_delta=episode_row["last_learning_delta"],
            last_evidence_mode=episode_row["last_evidence_mode"],
        )

    deltas = []
    for row in observations:
        if not row["learning_delta"]:
            continue
        deltas.append(
            LearningDeltaItem(
                objective_id=row["objective_id"],
                episode_id=row["episode_id"],
                delta=row["learning_delta"],
                recorded_at=row["observed_at"],
            )
        )
        if len(deltas) >= 5:
            break

    component_progress = []
    for row in observations:
        component_progress = _safe_profile(row["evidence_profile"])
        if component_progress:
            break

    # El episodio activo manda sobre eventos antiguos de otros objetivos.
    if episode_row is not None:
        current_objective = episode_row["objective"]
        current_objective_id = episode_row["objective_id"]
        source = episode_row["objective_source"]
        latest_current = next(
            (row for row in applied_rows if row["objective_id"] == current_objective_id),
            None,
        )
        current_activity = latest_current["activity"] if latest_current is not None else (
            next((row["activity_id"] for row in observations if row["objective_id"] == current_objective_id), None)
        )
    else:
        current_objective = latest["objective"] if latest is not None else None
        current_objective_id = latest["objective_id"] if latest is not None else None
        source = latest["objective_source"] if latest is not None else None
        current_activity = latest["activity"] if latest is not None else None

    current_rows = [
        row for row in rows
        if current_objective_id is None or row["objective_id"] == current_objective_id
    ]
    recent_evidence = [row["evidence"][:240] for row in current_rows[:4] if row["evidence"]]
    previous_gaps = _recent_unique(
        [
            row["gap"] for row in applied_rows
            if row["gap"] and row["gap"] != "none"
            and (current_objective_id is None or row["objective_id"] == current_objective_id)
        ],
        limit=8,
    )
    confirmed_evidence = [
        row["evidence"][:240] for row in confirmed
        if row["evidence"] and (current_objective_id is None or row["objective_id"] == current_objective_id)
    ]

    # Para component_progress, prioriza observaciones del objetivo activo.
    component_progress = []
    for row in observations:
        if current_objective_id is not None and row["objective_id"] != current_objective_id:
            continue
        component_progress = _safe_profile(row["evidence_profile"])
        if component_progress:
            break

    return GetLearningStateResult(
        student_id=data.student_id,
        has_history=bool(rows),
        current_objective=current_objective,
        current_objective_id=current_objective_id,
        current_activity=current_activity,
        objective_source=source,
        can_cite_as_teacher_objective=(source == "teacher"),
        attempts_count=len(applied_rows),
        previous_gaps=previous_gaps,
        strategies_tried=strategies,
        recent_evidence=recent_evidence,
        pending_intervention=pending,
        active_episode=active_episode,
        previous_confirmed_evidence=confirmed_evidence,
        learning_deltas=deltas,
        component_progress=component_progress,
    ).model_dump()


def list_teaching_strategies(
    gap, exclude_types=None, interaction_need=None, student_id=None, objective_id=None,
    task_type=None, response_format=None, retrieval_required=None, transfer_context=None,
    support_level=None, institution_id=None, subject_family=None, objective_family=None, *, db_path=None
):
    try:
        data = ListTeachingStrategiesInput(
            gap=gap,
            exclude_types=exclude_types or [],
            interaction_need=interaction_need,
            student_id=student_id,
            objective_id=objective_id,
            task_type=task_type,
            response_format=response_format,
            retrieval_required=retrieval_required,
            transfer_context=transfer_context,
            support_level=support_level,
            institution_id=institution_id,
            subject_family=subject_family,
            objective_family=objective_family,
        )
    except ValidationError:
        return _error(
            "validation_error",
            "gap, exclude_types o interaction_need contienen valores inválidos.",
        )

    try:
        ensure_database(db_path)
        with closing(connect(db_path)) as connection:
            rows = connection.execute(
                """
                SELECT type, compatible_gaps, summary
                FROM teaching_strategies
                WHERE active = 1
                ORDER BY type
                """
            ).fetchall()
    except (sqlite3.Error, OSError) as error:
        return _error(
            "storage_error",
            f"No fue posible consultar el catálogo pedagógico: {type(error).__name__}.",
        )

    need_map = {
        "explanation": {"concept_explanation", "analogy", "contrast_example", "worked_example"},
        "hint": {"hint", "probe"},
        "reassessment": {"probe", "hint"},
        "confirmation": {"probe", "independent_practice"},
        "exploration": {"concept_explanation", "analogy", "probe"},
        "practice": {"independent_practice"} if data.gap == "none" else {"guided_practice", "hint", "worked_example"},
    }

    exclude = set(data.exclude_types)
    eligible = []
    excluded = []

    for row in rows:
        try:
            compatible = json.loads(row["compatible_gaps"])
        except (TypeError, json.JSONDecodeError):
            compatible = []

        if row["type"] in exclude:
            excluded.append({"type": row["type"], "reason": "previously_failed"})
            continue

        if data.interaction_need in need_map:
            if row["type"] not in need_map[data.interaction_need]:
                excluded.append({"type": row["type"], "reason": "incompatible_need"})
                continue
        else:
            if data.gap not in compatible:
                excluded.append({"type": row["type"], "reason": "incompatible_gap"})
                continue

        eligible.append({"type": row["type"], "summary": row["summary"]})

    plans = plan_strategy_candidates(
        eligible=eligible,
        student_id=data.student_id,
        objective_id=data.objective_id,
        task_type=data.task_type,
        support_level=data.support_level,
        institution_id=data.institution_id,
        subject_family=data.subject_family,
        objective_family=data.objective_family,
        db_path=db_path,
    )
    plan_by_type = {item["strategy_type"]: item for item in plans}
    enriched = []
    for item in eligible:
        plan = plan_by_type.get(item["type"], {})
        enriched.append({
            **item,
            "priority_score": plan.get("priority_score"),
            "rationale": plan.get("rationale"),
            "evidence_basis": plan.get("evidence_basis"),
            "recommended_support_level": plan.get("recommended_support_level"),
            "institutional_confidence": plan.get("institutional_confidence"),
        })
    enriched.sort(key=lambda x: (-(x.get("priority_score") or 0.0), x["type"]))

    return ListTeachingStrategiesResult(
        gap=data.gap,
        interaction_need=data.interaction_need,
        eligible=enriched,
        excluded=excluded,
        catalog_incomplete=(len(eligible) == 0),
    ).model_dump()


def record_learning_event(
    student_id,
    objective,
    objective_source,
    activity,
    gap,
    strategy_type,
    strategy_result,
    diagnostic_outcome,
    evidence,
    event_type=None,
    objective_id=None,
    evaluates_event_id=None,
    result_reason=None,
    episode_id=None,
    turn_type=None,
    task_type=None,
    response_format=None,
    retrieval_required=None,
    transfer_context=None,
    evidence_mode=None,
    independent_evidence_eligible=None,
    support_level=None,
    intervention_support_level=None,
    planner_top_strategy=None,
    selection_mode=None,
    selection_reason=None,
    selection_reason_code=None,
    institution_id=None,
    subject_family=None,
    objective_family=None,
    learning_delta=None,
    difficulty_relation=None,
    evidence_profile=None,
    *,
    db_path=None,
):
    """
    Escritura append-only.

    - strategy_applied conserva strategy_result=inconclusive: resultado aún no observado.
    - helped o failed solo son válidos con evidencia posterior.
    - strategy_evaluated crea un segundo evento; nunca reescribe el aplicado.
    - strategy_interrupted cierra una intervención sin evaluarla cuando el alumno
      pide ayuda antes de producir un intento elegible.
    - metadata longitudinal (episode/turn/evidence) la añade el orquestador, no Grok.
    """
    normalized_event_type = event_type
    if normalized_event_type is None:
        normalized_event_type = "legacy" if objective_id is None else "strategy_applied"

    try:
        data = RecordLearningEventInput(
            student_id=student_id,
            objective=objective,
            objective_source=objective_source,
            activity=activity,
            gap=gap,
            strategy_type=strategy_type,
            strategy_result=strategy_result,
            diagnostic_outcome=diagnostic_outcome,
            evidence=evidence,
            event_type=normalized_event_type,
            objective_id=objective_id,
            evaluates_event_id=evaluates_event_id,
            result_reason=result_reason,
            episode_id=episode_id,
            turn_type=turn_type,
            task_type=task_type,
            response_format=response_format,
            retrieval_required=retrieval_required,
            transfer_context=transfer_context,
            evidence_mode=evidence_mode,
            independent_evidence_eligible=independent_evidence_eligible,
            support_level=support_level,
            intervention_support_level=intervention_support_level,
            planner_top_strategy=planner_top_strategy,
            selection_mode=selection_mode,
            selection_reason=selection_reason,
            selection_reason_code=selection_reason_code,
            institution_id=institution_id,
            subject_family=subject_family,
            objective_family=objective_family,
            learning_delta=learning_delta,
            difficulty_relation=difficulty_relation,
            evidence_profile=evidence_profile,
        )
    except ValidationError:
        return _error("validation_error", "El evento contiene campos inválidos o valores fuera del contrato de aprendizaje.")

    if data.event_type == "strategy_applied":
        if not data.objective_id:
            return _error("validation_error", "strategy_applied requiere objective_id estable.")
        if data.strategy_result != "inconclusive":
            return _error("validation_error", "strategy_applied debe registrar strategy_result='inconclusive'.")
        if data.evaluates_event_id is not None or data.result_reason is not None:
            return _error("validation_error", "strategy_applied no puede evaluar otro evento ni incluir result_reason.")

    if data.event_type in {"strategy_evaluated", "strategy_interrupted"}:
        if not data.objective_id or not data.evaluates_event_id or not data.result_reason:
            return _error(
                "validation_error",
                f"{data.event_type} requiere objective_id, evaluates_event_id y result_reason.",
            )
        if data.event_type == "strategy_interrupted":
            if data.strategy_result != "inconclusive" or data.diagnostic_outcome != "inconclusive":
                return _error(
                    "validation_error",
                    "strategy_interrupted debe ser inconclusive y no representa una evaluación del aprendizaje.",
                )
            if data.result_reason not in {"help_requested_before_attempt", "topic_switched_before_attempt"}:
                return _error(
                    "validation_error",
                    "strategy_interrupted requiere una razón de interrupción válida.",
                )

    event_id = str(uuid4())
    recorded_at = datetime.now(timezone.utc).isoformat()

    try:
        ensure_database(db_path)
        with closing(connect(db_path)) as connection:
            strategy = connection.execute(
                "SELECT type FROM teaching_strategies WHERE type = ? AND active = 1",
                (data.strategy_type,),
            ).fetchone()
            if strategy is None:
                return _error("validation_error", "strategy_type no existe o no está activa en el catálogo pedagógico.")

            if data.event_type in {"strategy_evaluated", "strategy_interrupted"}:
                applied = connection.execute(
                    """
                    SELECT event_id, student_id, objective_id, strategy_type, event_type, episode_id
                    FROM learning_events WHERE event_id = ?
                    """,
                    (data.evaluates_event_id,),
                ).fetchone()
                if applied is None or applied["event_type"] != "strategy_applied":
                    return _error("validation_error", "evaluates_event_id no referencia una intervención strategy_applied válida.")
                if applied["student_id"] != data.student_id:
                    return _error("validation_error", "La evaluación no pertenece al mismo estudiante.")
                if applied["objective_id"] != data.objective_id:
                    return _error("validation_error", "La evaluación no pertenece al mismo objective_id.")
                if applied["strategy_type"] != data.strategy_type:
                    return _error("validation_error", "La evaluación no corresponde a la misma estrategia aplicada.")
                if data.episode_id and applied["episode_id"] and data.episode_id != applied["episode_id"]:
                    return _error("validation_error", "La evaluación no pertenece al mismo episodio de aprendizaje.")
                existing = connection.execute(
                    """
                    SELECT event_id FROM learning_events
                    WHERE event_type IN ('strategy_evaluated', 'strategy_interrupted')
                      AND evaluates_event_id=?
                    LIMIT 1
                    """,
                    (data.evaluates_event_id,),
                ).fetchone()
                if existing is not None:
                    return _error(
                        "validation_error",
                        "La intervención ya tiene un evento terminal y no puede cerrarse dos veces.",
                    )

            connection.execute(
                "INSERT OR IGNORE INTO students(student_id, created_at) VALUES (?, ?)",
                (data.student_id, recorded_at),
            )
            connection.execute(
                """
                INSERT INTO learning_events(
                    event_id, student_id, recorded_at, objective, objective_source,
                    activity, gap, strategy_type, strategy_result, diagnostic_outcome,
                    evidence, event_type, objective_id, evaluates_event_id, result_reason,
                    episode_id, turn_type, task_type, response_format, retrieval_required, transfer_context,
                    evidence_mode, independent_evidence_eligible, support_level, intervention_support_level,
                    planner_top_strategy, selection_mode, selection_reason, selection_reason_code,
                    institution_id, subject_family, objective_family,
                    learning_delta, difficulty_relation, evidence_profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, data.student_id, recorded_at, data.objective, data.objective_source,
                    data.activity, data.gap, data.strategy_type, data.strategy_result,
                    data.diagnostic_outcome, data.evidence, data.event_type, data.objective_id,
                    data.evaluates_event_id, data.result_reason, data.episode_id,
                    data.turn_type, data.task_type, data.response_format,
                    1 if data.retrieval_required else 0 if data.retrieval_required is not None else None,
                    1 if data.transfer_context else 0 if data.transfer_context is not None else None,
                    data.evidence_mode,
                    1 if data.independent_evidence_eligible else 0 if data.independent_evidence_eligible is not None else None,
                    data.support_level, data.intervention_support_level, data.planner_top_strategy, data.selection_mode,
                    data.selection_reason, data.selection_reason_code, data.institution_id, data.subject_family,
                    data.objective_family, data.learning_delta, data.difficulty_relation, data.evidence_profile,
                ),
            )
            connection.commit()
    except sqlite3.IntegrityError:
        return _error("validation_error", "La evaluación viola una restricción de integridad del historial.")
    except (sqlite3.Error, OSError) as error:
        return _error("storage_error", f"No fue posible persistir esta interacción: {type(error).__name__}.")

    return RecordLearningEventResult(event_id=event_id, recorded_at=recorded_at).model_dump()


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_learning_state",
            "description": (
                "Consulta memoria persistente: objetivo, episodio, evidencia confirmada, "
                "deltas de aprendizaje, intentos y estrategias. Debe usarse antes de "
                "afirmar algo sobre historial del alumno."
            ),
            "parameters": {
                "type": "object",
                "properties": {"student_id": {"type": "string", "description": "Identificador interno opaco del estudiante."}},
                "required": ["student_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_teaching_strategies",
            "description": (
                "Consulta el catálogo pedagógico. Puede filtrar por gap diagnóstico o por "
                "interaction_need cuando el alumno pide explicación, pista, reevaluación o práctica. "
                "Devuelve opciones; no elige la estrategia final."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gap": {"type": "string", "description": "Gap observado; usa 'none' si no hubo diagnóstico elegible."},
                    "interaction_need": {
                        "type": "string",
                        "enum": [
                            "diagnostic_gap", "explanation", "hint", "reassessment",
                            "practice", "confirmation", "exploration", "none"
                        ],
                        "description": "Necesidad pedagógica del turno actual."
                    },
                    "exclude_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Estrategias failed del MISMO objective_id que no deben repetirse automáticamente.",
                    },
                },
                "required": ["gap"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_learning_event",
            "description": (
                "Registra una NUEVA estrategia aplicada en este turno. El agente solo crea "
                "strategy_applied con strategy_result=inconclusive. La evaluación con evidencia posterior "
                "la realiza el orquestador determinista."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string"},
                    "objective": {"type": "string"},
                    "objective_source": {"type": "string", "enum": ["teacher", "course", "inferred"]},
                    "activity": {"type": "string"},
                    "gap": {"type": "string"},
                    "strategy_type": {"type": "string"},
                    "strategy_result": {"type": "string", "enum": ["inconclusive"]},
                    "diagnostic_outcome": {"type": "string", "enum": ["incorrect", "partial", "correct", "inconclusive"]},
                    "evidence": {"type": "string"},
                    "event_type": {"type": "string", "enum": ["strategy_applied"]},
                    "objective_id": {"type": "string", "description": "ID estable del objetivo entregado por el orquestador."},
                },
                "required": [
                    "student_id", "objective", "objective_source", "activity", "gap",
                    "strategy_type", "strategy_result", "diagnostic_outcome", "evidence",
                    "event_type", "objective_id",
                ],
                "additionalProperties": False,
            },
        },
    },
]


def execute_tool_call(name, arguments, *, db_path=None):
    registry = {
        "get_learning_state": get_learning_state,
        "list_teaching_strategies": list_teaching_strategies,
        "record_learning_event": record_learning_event,
    }
    function = registry.get(name)
    if function is None:
        return _error("unknown_tool", f"Herramienta desconocida: {name}.")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return _error("invalid_arguments", "Los argumentos de la herramienta no son JSON válido.")
    if not isinstance(arguments, dict):
        return _error("invalid_arguments", "Los argumentos de la herramienta deben ser un objeto JSON.")

    try:
        return function(**arguments, db_path=db_path)
    except TypeError:
        return _error("validation_error", "Los argumentos no cumplen la firma de la herramienta.")
