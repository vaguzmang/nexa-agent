import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from .models import (
    GetLearningStateInput,
    GetLearningStateResult,
    ListTeachingStrategiesInput,
    ListTeachingStrategiesResult,
    RecordLearningEventInput,
    RecordLearningEventResult,
    ToolError,
)
from .storage import connect, ensure_database


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


def get_learning_state(student_id, *, db_path=None):
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
                SELECT recorded_at, objective, objective_source, gap,
                       strategy_type, strategy_result, evidence
                FROM learning_events
                WHERE student_id = ?
                ORDER BY recorded_at DESC
                """,
                (data.student_id,),
            ).fetchall()
    except (sqlite3.Error, OSError) as error:
        return _error(
            "storage_error",
            f"No fue posible consultar la memoria de aprendizaje: {type(error).__name__}.",
        )

    if not rows:
        return GetLearningStateResult(
            student_id=data.student_id,
            has_history=False,
            current_objective=None,
            objective_source=None,
            can_cite_as_teacher_objective=False,
            attempts_count=0,
            previous_gaps=[],
            strategies_tried=[],
            recent_evidence=[],
        ).model_dump()

    latest = rows[0]
    previous_gaps = _recent_unique(
        [row["gap"] for row in rows if row["gap"] != "none"],
        limit=5,
    )

    strategies = []
    seen_strategies = set()
    for row in rows:
        strategy_type = row["strategy_type"]
        if strategy_type in seen_strategies:
            continue
        seen_strategies.add(strategy_type)
        strategies.append(
            {
                "type": strategy_type,
                "result": row["strategy_result"],
            }
        )
        if len(strategies) >= 5:
            break

    recent_evidence = [
        row["evidence"][:240]
        for row in rows[:3]
        if row["evidence"]
    ]

    source = latest["objective_source"]
    return GetLearningStateResult(
        student_id=data.student_id,
        has_history=True,
        current_objective=latest["objective"],
        objective_source=source,
        can_cite_as_teacher_objective=(source == "teacher"),
        attempts_count=len(rows),
        previous_gaps=previous_gaps,
        strategies_tried=strategies,
        recent_evidence=recent_evidence,
    ).model_dump()


def list_teaching_strategies(gap, exclude_types=None, *, db_path=None):
    try:
        data = ListTeachingStrategiesInput(
            gap=gap,
            exclude_types=exclude_types or [],
        )
    except ValidationError:
        return _error(
            "validation_error",
            "gap es obligatorio y exclude_types debe ser una lista válida.",
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

    exclude = set(data.exclude_types)
    eligible = []
    excluded = []

    for row in rows:
        try:
            compatible = json.loads(row["compatible_gaps"])
        except (TypeError, json.JSONDecodeError):
            compatible = []

        if data.gap not in compatible:
            excluded.append(
                {"type": row["type"], "reason": "incompatible_gap"}
            )
            continue

        if row["type"] in exclude:
            excluded.append(
                {"type": row["type"], "reason": "previously_failed"}
            )
            continue

        eligible.append(
            {
                "type": row["type"],
                "summary": row["summary"],
            }
        )

    return ListTeachingStrategiesResult(
        gap=data.gap,
        eligible=eligible,
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
    *,
    db_path=None,
):
    """
    Semántica S2 congelada para record_learning_event:

    - diagnostic_outcome describe la evidencia ENTRANTE de este turno.
    - strategy_type describe la intervención que NEXA va a aplicar ahora.
    - si aún no existe una respuesta posterior del estudiante a esa intervención,
      strategy_result DEBE ser "inconclusive": significa "resultado aún no observado".
    - "helped" o "failed" solo son válidos cuando existe evidencia posterior del
      estudiante que permita evaluar el efecto de una estrategia aplicada antes.
    - nunca inferir "helped" porque la explicación generada parezca buena.

    La tool genera event_id/timestamp y solo confirma persistencia con event_id.
    No acepta mastery, grade, score ni rubric.
    """
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
        )
    except ValidationError:
        return _error(
            "validation_error",
            "El evento contiene campos inválidos o valores fuera del contrato S2.",
        )

    event_id = str(uuid4())
    recorded_at = datetime.now(timezone.utc).isoformat()

    try:
        ensure_database(db_path)
        with closing(connect(db_path)) as connection:
            strategy = connection.execute(
                """
                SELECT type
                FROM teaching_strategies
                WHERE type = ? AND active = 1
                """,
                (data.strategy_type,),
            ).fetchone()

            if strategy is None:
                return _error(
                    "validation_error",
                    "strategy_type no existe o no está activa en el catálogo pedagógico.",
                )

            connection.execute(
                """
                INSERT OR IGNORE INTO students(student_id, created_at)
                VALUES (?, ?)
                """,
                (data.student_id, recorded_at),
            )

            connection.execute(
                """
                INSERT INTO learning_events(
                    event_id, student_id, recorded_at,
                    objective, objective_source, activity,
                    gap, strategy_type, strategy_result,
                    diagnostic_outcome, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    data.student_id,
                    recorded_at,
                    data.objective,
                    data.objective_source,
                    data.activity,
                    data.gap,
                    data.strategy_type,
                    data.strategy_result,
                    data.diagnostic_outcome,
                    data.evidence,
                ),
            )
            connection.commit()
    except (sqlite3.Error, OSError) as error:
        return _error(
            "storage_error",
            f"No fue posible persistir esta interacción: {type(error).__name__}.",
        )

    return RecordLearningEventResult(
        event_id=event_id,
        recorded_at=recorded_at,
    ).model_dump()


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_learning_state",
            "description": (
                "Consulta la memoria persistente de un estudiante. "
                "Debe usarse antes de afirmar algo sobre intentos, objetivos "
                "o estrategias anteriores del alumno."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {
                        "type": "string",
                        "description": "Identificador interno opaco del estudiante.",
                    }
                },
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
                "Consulta el catálogo pedagógico y devuelve opciones compatibles "
                "con un gap. No elige la estrategia final ni redacta la lección."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gap": {
                        "type": "string",
                        "description": "Gap observado en el diagnóstico actual.",
                    },
                    "exclude_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Estrategias que no deben repetirse automáticamente, "
                            "por ejemplo las que fallaron previamente."
                        ),
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
                "Registra de forma append-only lo ocurrido en una interacción de aprendizaje. "
                "diagnostic_outcome describe la evidencia entrante. Si la estrategia se "
                "aplica en este mismo turno y aún no hay respuesta posterior del alumno, "
                "strategy_result debe ser inconclusive; helped/failed requieren evidencia "
                "posterior. Solo afirmar que quedó registrado si devuelve event_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string"},
                    "objective": {"type": "string"},
                    "objective_source": {
                        "type": "string",
                        "enum": ["teacher", "course", "inferred"],
                    },
                    "activity": {"type": "string"},
                    "gap": {"type": "string"},
                    "strategy_type": {"type": "string"},
                    "strategy_result": {
                        "type": "string",
                        "enum": ["helped", "failed", "inconclusive"],
                    },
                    "diagnostic_outcome": {
                        "type": "string",
                        "enum": ["incorrect", "partial", "correct", "inconclusive"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": [
                    "student_id",
                    "objective",
                    "objective_source",
                    "activity",
                    "gap",
                    "strategy_type",
                    "strategy_result",
                    "diagnostic_outcome",
                    "evidence",
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
        return _error(
            "unknown_tool",
            f"Herramienta desconocida: {name}.",
        )

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return _error(
                "invalid_arguments",
                "Los argumentos de la herramienta no son JSON válido.",
            )

    if not isinstance(arguments, dict):
        return _error(
            "invalid_arguments",
            "Los argumentos de la herramienta deben ser un objeto JSON.",
        )

    try:
        return function(**arguments, db_path=db_path)
    except TypeError:
        return _error(
            "validation_error",
            "Los argumentos no cumplen la firma de la herramienta.",
        )
