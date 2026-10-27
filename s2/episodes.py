import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4

from .storage import connect, ensure_database


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    return dict(row) if row is not None else None


def get_latest_episode(student_id, objective_id=None, *, db_path=None):
    ensure_database(db_path)
    with closing(connect(db_path)) as connection:
        if objective_id is None:
            row = connection.execute(
                """
                SELECT * FROM learning_episodes
                WHERE student_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT * FROM learning_episodes
                WHERE student_id = ? AND objective_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (student_id, objective_id),
            ).fetchone()
    return _row_to_dict(row)


def ensure_learning_episode(
    *,
    student_id,
    objective_id,
    objective,
    objective_source,
    turn_type,
    db_path=None,
):
    """Obtiene/crea el episodio y reabre uno confirmado cuando el alumno retorna."""
    ensure_database(db_path)
    now = _now()
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT * FROM learning_episodes
            WHERE student_id = ? AND objective_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (student_id, objective_id),
        ).fetchone()

        previous_status = row["status"] if row is not None else None
        reopened = False
        resumed = False

        if row is None:
            episode_id = f"episode-{uuid4()}"
            connection.execute(
                """
                INSERT INTO learning_episodes(
                    episode_id, student_id, objective_id, objective, objective_source,
                    status, started_at, updated_at, closed_at, reopen_count
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL, 0)
                """,
                (episode_id, student_id, objective_id, objective, objective_source, now, now),
            )
        else:
            episode_id = row["episode_id"]
            if row["status"] == "suspended" and turn_type != "off_topic":
                resumed = True
                connection.execute(
                    """
                    UPDATE learning_episodes
                    SET status = 'active', updated_at = ?, closed_at = NULL,
                        objective = ?, objective_source = ?
                    WHERE episode_id = ?
                    """,
                    (now, objective, objective_source, episode_id),
                )
            elif row["status"] in {"evidence_confirmed", "closed"} and turn_type != "off_topic":
                reopened = True
                connection.execute(
                    """
                    UPDATE learning_episodes
                    SET status = 'reopened', updated_at = ?, closed_at = NULL,
                        reopen_count = reopen_count + 1,
                        objective = ?, objective_source = ?
                    WHERE episode_id = ?
                    """,
                    (now, objective, objective_source, episode_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE learning_episodes
                    SET updated_at = ?, objective = ?, objective_source = ?
                    WHERE episode_id = ?
                    """,
                    (now, objective, objective_source, episode_id),
                )

        connection.commit()
        current = connection.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()

    result = dict(current)
    result["previous_status"] = previous_status
    result["reopened_now"] = reopened
    result["resumed_now"] = resumed
    return result


def suspend_learning_episode(episode_id, *, db_path=None):
    """Suspende un episodio incompleto cuando el alumno cambia de objetivo."""
    ensure_database(db_path)
    now = _now()
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            return None
        if row["status"] in {"active", "awaiting_evidence", "reopened"}:
            connection.execute(
                """
                UPDATE learning_episodes
                SET status = 'suspended', updated_at = ?, closed_at = NULL
                WHERE episode_id = ?
                """,
                (now, episode_id),
            )
            connection.commit()
        updated = connection.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
    return dict(updated)


def update_episode_projection(
    *,
    episode_id,
    status=None,
    learning_delta=None,
    evidence_mode=None,
    db_path=None,
):
    ensure_database(db_path)
    now = _now()
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            return None

        new_status = status or row["status"]
        closed_at = now if new_status in {"evidence_confirmed", "closed"} else None
        connection.execute(
            """
            UPDATE learning_episodes
            SET status = ?, updated_at = ?, closed_at = ?,
                last_learning_delta = COALESCE(?, last_learning_delta),
                last_evidence_mode = COALESCE(?, last_evidence_mode)
            WHERE episode_id = ?
            """,
            (new_status, now, closed_at, learning_delta, evidence_mode, episode_id),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT * FROM learning_episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
    return dict(updated)


def record_learning_observation(
    *,
    task_id,
    student_id,
    episode_id,
    objective_id,
    activity_id,
    turn_type,
    evidence_eligible,
    task_type,
    response_format=None,
    retrieval_required=False,
    transfer_context=False,
    evidence_mode=None,
    independent_evidence_eligible=False,
    support_level=None,
    difficulty_relation,
    diagnostic_outcome,
    gap,
    learning_delta,
    evidence_summary,
    evidence_profile,
    interaction_need=None,
    objective_action=None,
    db_path=None,
):
    """Log append-only e idempotente por task_id para cada turno observado."""
    ensure_database(db_path)
    observed_at = _now()
    observation_id = f"observation-{task_id}"
    try:
        with closing(connect(db_path)) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO learning_observations(
                    observation_id, task_id, student_id, episode_id, objective_id, activity_id,
                    observed_at, turn_type, evidence_eligible, task_type, response_format,
                    retrieval_required, transfer_context, evidence_mode, independent_evidence_eligible,
                    support_level, difficulty_relation, diagnostic_outcome, gap, learning_delta,
                    evidence_summary, evidence_profile, interaction_need, objective_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id, task_id, student_id, episode_id, objective_id, activity_id,
                    observed_at, turn_type, 1 if evidence_eligible else 0, task_type, response_format,
                    1 if retrieval_required else 0, 1 if transfer_context else 0, evidence_mode,
                    1 if independent_evidence_eligible else 0, support_level, difficulty_relation,
                    diagnostic_outcome, gap, learning_delta,
                    (evidence_summary or "")[:500], evidence_profile, interaction_need, objective_action,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM learning_observations WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(row)
    except (sqlite3.Error, OSError):
        return None


def list_recent_episodes(student_id, *, limit=12, db_path=None):
    ensure_database(db_path)
    safe_limit = max(1, min(int(limit), 50))
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT * FROM learning_episodes
            WHERE student_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (student_id, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]
