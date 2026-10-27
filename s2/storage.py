import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


STRATEGY_SEED = (
    ("probe", ["uncertain", "unclear_communication", "misconception"], "Pregunta breve para obtener evidencia adicional antes de explicar o corregir."),
    ("hint", ["incomplete_procedure", "factual_error", "missing_prerequisite"], "Pista mínima que orienta el siguiente paso sin resolver la tarea por el estudiante."),
    ("concept_explanation", ["misconception", "missing_prerequisite", "factual_error"], "Explicación conceptual breve centrada en la brecha observada, seguida de participación del estudiante."),
    ("analogy", ["misconception", "missing_prerequisite"], "Analogía concreta para conectar el concepto con una experiencia familiar sin presentarla como equivalencia perfecta."),
    ("contrast_example", ["misconception", "factual_error", "unclear_communication"], "Contraste entre dos casos cercanos para hacer visible la diferencia conceptual relevante."),
    ("worked_example", ["incomplete_procedure", "missing_prerequisite"], "Ejemplo resuelto por etapas que hace explícito el procedimiento; debe ir seguido de una tarea del estudiante."),
    ("guided_practice", ["incomplete_procedure", "missing_prerequisite", "factual_error"], "Práctica por pasos con ayuda decreciente y una respuesta activa del estudiante."),
    ("prerequisite_review", ["missing_prerequisite"], "Repaso focalizado del prerrequisito que bloquea el objetivo actual."),
    ("independent_practice", ["none"], "Práctica sin ayuda para confirmar evidencia reciente de acierto; usar solo cuando exista evidencia suficiente."),
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
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_database(db_path=None):
    # closing() es obligatorio en Windows para no dejar handles abiertos.
    with closing(connect(db_path)) as connection:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            # SQLite en memoria u otros backends temporales pueden no aceptar WAL.
            pass

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

            CREATE TABLE IF NOT EXISTS learning_episodes (
                episode_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                objective_id TEXT NOT NULL,
                objective TEXT NOT NULL,
                objective_source TEXT NOT NULL
                    CHECK(objective_source IN ('teacher', 'course', 'inferred')),
                status TEXT NOT NULL
                    CHECK(status IN ('active', 'awaiting_evidence', 'evidence_confirmed', 'closed', 'reopened', 'suspended')),
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                reopen_count INTEGER NOT NULL DEFAULT 0,
                last_learning_delta TEXT,
                last_evidence_mode TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_learning_episodes_student_objective
            ON learning_episodes(student_id, objective_id, updated_at);

            CREATE TABLE IF NOT EXISTS learning_observations (
                observation_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                student_id TEXT NOT NULL,
                episode_id TEXT,
                objective_id TEXT NOT NULL,
                activity_id TEXT,
                observed_at TEXT NOT NULL,
                turn_type TEXT NOT NULL,
                evidence_eligible INTEGER NOT NULL CHECK(evidence_eligible IN (0, 1)),
                task_type TEXT NOT NULL,
                evidence_mode TEXT NOT NULL,
                support_level TEXT NOT NULL,
                difficulty_relation TEXT NOT NULL,
                diagnostic_outcome TEXT NOT NULL,
                gap TEXT NOT NULL,
                learning_delta TEXT,
                evidence_summary TEXT,
                evidence_profile TEXT,
                interaction_need TEXT,
                objective_action TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_learning_observations_student_objective
            ON learning_observations(student_id, objective_id, observed_at);

            CREATE TABLE IF NOT EXISTS task_runs (
                task_id TEXT PRIMARY KEY,
                student_id TEXT,
                episode_id TEXT,
                objective_id TEXT,
                started_at TEXT,
                finished_at TEXT,
                diagnosis_prompt_tokens INTEGER,
                diagnosis_completion_tokens INTEGER,
                diagnosis_tokens INTEGER,
                agent_prompt_tokens INTEGER,
                agent_completion_tokens INTEGER,
                agent_tokens INTEGER,
                total_tokens INTEGER,
                diagnosis_latency_ms INTEGER,
                agent_latency_ms INTEGER,
                total_latency_ms INTEGER,
                llm_calls INTEGER,
                tool_calls INTEGER,
                repairs INTEGER,
                errors INTEGER,
                estimated_cost_usd REAL,
                status TEXT NOT NULL,
                diagnosis_skipped INTEGER NOT NULL DEFAULT 0,
                diagnosis_visible_tokens INTEGER,
                agent_visible_tokens INTEGER,
                visible_token_sum INTEGER,
                cost_optimized INTEGER NOT NULL DEFAULT 0
            );
            """
        )

        # Migración de learning_episodes para admitir el estado suspended sin
        # perder episodios existentes. SQLite no permite ampliar un CHECK con ALTER.
        episode_schema_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='learning_episodes'"
        ).fetchone()
        episode_schema_sql = (episode_schema_row["sql"] or "") if episode_schema_row else ""
        if "'suspended'" not in episode_schema_sql:
            connection.execute("DROP INDEX IF EXISTS idx_learning_episodes_student_objective")
            connection.execute("ALTER TABLE learning_episodes RENAME TO learning_episodes_old_status")
            connection.execute(
                """
                CREATE TABLE learning_episodes (
                    episode_id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    objective_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    objective_source TEXT NOT NULL
                        CHECK(objective_source IN ('teacher', 'course', 'inferred')),
                    status TEXT NOT NULL
                        CHECK(status IN ('active', 'awaiting_evidence', 'evidence_confirmed', 'closed', 'reopened', 'suspended')),
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT,
                    reopen_count INTEGER NOT NULL DEFAULT 0,
                    last_learning_delta TEXT,
                    last_evidence_mode TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO learning_episodes(
                    episode_id, student_id, objective_id, objective, objective_source,
                    status, started_at, updated_at, closed_at, reopen_count,
                    last_learning_delta, last_evidence_mode
                )
                SELECT episode_id, student_id, objective_id, objective, objective_source,
                       status, started_at, updated_at, closed_at, reopen_count,
                       last_learning_delta, last_evidence_mode
                FROM learning_episodes_old_status
                """
            )
            connection.execute("DROP TABLE learning_episodes_old_status")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_learning_episodes_student_objective
                ON learning_episodes(student_id, objective_id, updated_at)
                """
            )

        observation_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(learning_observations)").fetchall()
        }
        if "activity_id" not in observation_columns:
            connection.execute("ALTER TABLE learning_observations ADD COLUMN activity_id TEXT")
        if "interaction_need" not in observation_columns:
            connection.execute("ALTER TABLE learning_observations ADD COLUMN interaction_need TEXT")
        if "objective_action" not in observation_columns:
            connection.execute("ALTER TABLE learning_observations ADD COLUMN objective_action TEXT")

        for column, sql_type in {
            "response_format": "TEXT",
            "retrieval_required": "INTEGER",
            "transfer_context": "INTEGER",
            "independent_evidence_eligible": "INTEGER",
        }.items():
            if column not in observation_columns:
                connection.execute(
                    f"ALTER TABLE learning_observations ADD COLUMN {column} {sql_type}"
                )

        # Migraciones aditivas: preservan los eventos de S2/S3 ya existentes.
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(learning_events)").fetchall()
        }

        additive_columns = {
            "event_type": "TEXT",
            "objective_id": "TEXT",
            "evaluates_event_id": "TEXT",
            "result_reason": "TEXT",
            "episode_id": "TEXT",
            "turn_type": "TEXT",
            "task_type": "TEXT",
            "response_format": "TEXT",
            "retrieval_required": "INTEGER",
            "transfer_context": "INTEGER",
            "evidence_mode": "TEXT",
            "independent_evidence_eligible": "INTEGER",
            "support_level": "TEXT",
            "intervention_support_level": "TEXT",
            "planner_top_strategy": "TEXT",
            "selection_mode": "TEXT",
            "selection_reason": "TEXT",
            "selection_reason_code": "TEXT",
            "institution_id": "TEXT",
            "subject_family": "TEXT",
            "objective_family": "TEXT",
            "learning_delta": "TEXT",
            "difficulty_relation": "TEXT",
            "evidence_profile": "TEXT",
        }

        for column, sql_type in additive_columns.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE learning_events ADD COLUMN {column} {sql_type}"
                )

        connection.execute(
            """
            UPDATE learning_events
            SET event_type = 'legacy'
            WHERE event_type IS NULL
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_learning_events_student_objective_time
            ON learning_events(student_id, objective_id, recorded_at)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_learning_events_episode_time
            ON learning_events(episode_id, recorded_at)
            """
        )
        connection.execute("DROP INDEX IF EXISTS idx_learning_events_one_evaluation")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_learning_events_one_terminal
            ON learning_events(evaluates_event_id)
            WHERE event_type IN ('strategy_evaluated', 'strategy_interrupted')
              AND evaluates_event_id IS NOT NULL
            """
        )

        task_run_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(task_runs)").fetchall()
        }
        task_additive_columns = {
            "diagnosis_skipped": "INTEGER NOT NULL DEFAULT 0",
            "diagnosis_visible_tokens": "INTEGER",
            "agent_visible_tokens": "INTEGER",
            "visible_token_sum": "INTEGER",
            "cost_optimized": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, sql_type in task_additive_columns.items():
            if column not in task_run_columns:
                connection.execute(f"ALTER TABLE task_runs ADD COLUMN {column} {sql_type}")

        for strategy_type, compatible_gaps, summary in STRATEGY_SEED:
            connection.execute(
                """
                INSERT OR IGNORE INTO teaching_strategies
                    (type, compatible_gaps, summary, active)
                VALUES (?, ?, ?, 1)
                """,
                (strategy_type, json.dumps(compatible_gaps, ensure_ascii=False), summary),
            )
        connection.commit()
