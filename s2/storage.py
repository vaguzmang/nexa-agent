import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


STRATEGY_SEED = (
    (
        "probe",
        ["uncertain", "unclear_communication", "misconception"],
        "Pregunta breve para obtener evidencia adicional antes de explicar o corregir.",
    ),
    (
        "hint",
        ["incomplete_procedure", "factual_error", "missing_prerequisite"],
        "Pista mínima que orienta el siguiente paso sin resolver la tarea por el estudiante.",
    ),
    (
        "concept_explanation",
        ["misconception", "missing_prerequisite", "factual_error"],
        "Explicación conceptual breve centrada en la brecha observada, seguida de participación del estudiante.",
    ),
    (
        "analogy",
        ["misconception", "missing_prerequisite"],
        "Analogía concreta para conectar el concepto con una experiencia familiar sin presentarla como equivalencia perfecta.",
    ),
    (
        "contrast_example",
        ["misconception", "factual_error", "unclear_communication"],
        "Contraste entre dos casos cercanos para hacer visible la diferencia conceptual relevante.",
    ),
    (
        "worked_example",
        ["incomplete_procedure", "missing_prerequisite"],
        "Ejemplo resuelto por etapas que hace explícito el procedimiento; debe ir seguido de una tarea del estudiante.",
    ),
    (
        "guided_practice",
        ["incomplete_procedure", "missing_prerequisite", "factual_error"],
        "Práctica por pasos con ayuda decreciente y una respuesta activa del estudiante.",
    ),
    (
        "prerequisite_review",
        ["missing_prerequisite"],
        "Repaso focalizado del prerrequisito que bloquea el objetivo actual.",
    ),
    (
        "independent_practice",
        ["none"],
        "Práctica sin ayuda para confirmar evidencia reciente de acierto; usar solo cuando exista evidencia suficiente.",
    ),
)


def default_db_path() -> Path:
    configured = os.getenv("NEXA_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "data" / "nexa.db"


def connect(db_path=None):
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_database(db_path=None):
    # sqlite3.Connection.__enter__/__exit__ maneja transacciones,
    # pero NO cierra el handle. En Windows eso bloquea archivos temporales.
    # closing() garantiza el cierre real de la conexión.
    with closing(connect(db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teaching_strategies (
                type TEXT PRIMARY KEY,
                compatible_gaps TEXT NOT NULL,
                summary TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS learning_events (
                event_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                objective TEXT NOT NULL,
                objective_source TEXT NOT NULL
                    CHECK(objective_source IN ('teacher', 'course', 'inferred')),
                activity TEXT NOT NULL,
                gap TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                strategy_result TEXT NOT NULL
                    CHECK(strategy_result IN ('helped', 'failed', 'inconclusive')),
                diagnostic_outcome TEXT NOT NULL
                    CHECK(diagnostic_outcome IN ('incorrect', 'partial', 'correct', 'inconclusive')),
                evidence TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_learning_events_student_time
            ON learning_events(student_id, recorded_at);
            """
        )

        for strategy_type, compatible_gaps, summary in STRATEGY_SEED:
            connection.execute(
                """
                INSERT OR IGNORE INTO teaching_strategies
                    (type, compatible_gaps, summary, active)
                VALUES (?, ?, ?, 1)
                """,
                (
                    strategy_type,
                    json.dumps(compatible_gaps, ensure_ascii=False),
                    summary,
                ),
            )
        connection.commit()
