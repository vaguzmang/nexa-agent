from dataclasses import asdict, dataclass
from contextlib import closing

from s2.storage import connect, ensure_database


@dataclass(frozen=True)
class EffectivenessEvidence:
    strategy_type: str
    unique_students: int
    exposures: int
    helped: int
    failed: int
    decisive: int
    independent_confirmations: int
    score: float | None
    confidence: str
    scope: str

    def as_dict(self):
        return asdict(self)


def _confidence(unique_students: int, decisive: int) -> str:
    if unique_students >= 20 and decisive >= 12:
        return "supported_pattern"
    if unique_students >= 5 and decisive >= 4:
        return "emerging_pattern"
    return "insufficient_evidence"


def _score(helped: int, failed: int) -> float | None:
    decisive = helped + failed
    if decisive == 0:
        return None
    return round((helped + 1) / (decisive + 2), 4)


def _individual_profile(*, student_id, objective_id=None, task_type=None, db_path=None):
    ensure_database(db_path)
    filters = ["ap.event_type='strategy_applied'", "ap.student_id=?"]
    args = [student_id]
    if objective_id:
        filters.append("ap.objective_id=?")
        args.append(objective_id)
    if task_type:
        filters.append("ap.task_type=?")
        args.append(task_type)

    query = f"""
        SELECT ap.strategy_type,
               COUNT(*) AS exposures,
               SUM(CASE WHEN t.strategy_result='helped' THEN 1 ELSE 0 END) AS helped,
               SUM(CASE WHEN t.strategy_result='failed' THEN 1 ELSE 0 END) AS failed,
               SUM(CASE WHEN t.strategy_result='helped'
                         AND COALESCE(t.independent_evidence_eligible,0)=1
                        THEN 1 ELSE 0 END) AS independent_confirmations
        FROM learning_events ap
        LEFT JOIN learning_events t
          ON t.evaluates_event_id=ap.event_id
         AND t.event_type='strategy_evaluated'
        WHERE {' AND '.join(filters)}
        GROUP BY ap.strategy_type
    """
    with closing(connect(db_path)) as c:
        rows = c.execute(query, tuple(args)).fetchall()

    out = {}
    for r in rows:
        helped, failed = int(r["helped"] or 0), int(r["failed"] or 0)
        exposures = int(r["exposures"] or 0)
        independent = int(r["independent_confirmations"] or 0)
        decisive = helped + failed
        out[r["strategy_type"]] = EffectivenessEvidence(
            strategy_type=r["strategy_type"],
            unique_students=1,
            exposures=exposures,
            helped=helped,
            failed=failed,
            decisive=decisive,
            independent_confirmations=independent,
            score=_score(helped, failed),
            confidence="supported_pattern" if decisive >= 2 else "insufficient_evidence",
            scope="individual",
        )
    return out


def _institutional_profile(
    *, institution_id, subject_family, objective_family, task_type,
    exclude_student_id=None, db_path=None,
):
    if not all([institution_id, subject_family, objective_family, task_type]):
        return {}

    ensure_database(db_path)
    args = [institution_id, subject_family, objective_family, task_type]
    exclude_sql = ""
    if exclude_student_id:
        exclude_sql = "AND ap.student_id <> ?"
        args.append(exclude_student_id)

    query = f"""
        WITH candidates AS (
            SELECT ap.student_id, ap.strategy_type, t.strategy_result, t.recorded_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY ap.student_id, ap.strategy_type
                       ORDER BY t.recorded_at DESC
                   ) AS rn
            FROM learning_events ap
            JOIN learning_events t
              ON t.evaluates_event_id=ap.event_id
             AND t.event_type='strategy_evaluated'
             AND t.strategy_result IN ('helped','failed')
             AND COALESCE(t.independent_evidence_eligible,0)=1
            WHERE ap.event_type='strategy_applied'
              AND ap.institution_id=?
              AND ap.subject_family=?
              AND ap.objective_family=?
              AND ap.task_type=?
              {exclude_sql}
        ),
        latest AS (
            SELECT student_id, strategy_type, strategy_result
            FROM candidates WHERE rn=1
        )
        SELECT strategy_type,
               COUNT(*) AS unique_students,
               COUNT(*) AS exposures,
               SUM(CASE WHEN strategy_result='helped' THEN 1 ELSE 0 END) AS helped,
               SUM(CASE WHEN strategy_result='failed' THEN 1 ELSE 0 END) AS failed
        FROM latest
        GROUP BY strategy_type
    """
    with closing(connect(db_path)) as c:
        rows = c.execute(query, tuple(args)).fetchall()

    out = {}
    for r in rows:
        n = int(r["unique_students"] or 0)
        helped, failed = int(r["helped"] or 0), int(r["failed"] or 0)
        decisive = helped + failed
        out[r["strategy_type"]] = EffectivenessEvidence(
            strategy_type=r["strategy_type"],
            unique_students=n,
            exposures=int(r["exposures"] or 0),
            helped=helped,
            failed=failed,
            decisive=decisive,
            independent_confirmations=decisive,
            score=_score(helped, failed),
            confidence=_confidence(n, decisive),
            scope="institutional",
        )
    return out


def _population_audit(*, exclude_student_id=None, task_type=None, db_path=None):
    """Vista poblacional SOLO para analítica/auditoría; nunca para el Planner."""
    ensure_database(db_path)
    filters = ["ap.event_type='strategy_applied'"]
    args = []
    if exclude_student_id:
        filters.append("ap.student_id<>?")
        args.append(exclude_student_id)
    if task_type:
        filters.append("ap.task_type=?")
        args.append(task_type)
    with closing(connect(db_path)) as c:
        rows = c.execute(
            f"""SELECT ap.strategy_type,
                       COUNT(DISTINCT ap.student_id) AS unique_students,
                       COUNT(*) AS exposures
                FROM learning_events ap
                WHERE {' AND '.join(filters)}
                GROUP BY ap.strategy_type""",
            tuple(args),
        ).fetchall()
    return {
        r["strategy_type"]: {
            "strategy_type": r["strategy_type"],
            "unique_students": int(r["unique_students"] or 0),
            "exposures": int(r["exposures"] or 0),
            "scope": "population_audit_only",
            "confidence": "not_for_individual_ranking",
        }
        for r in rows
    }


def build_strategy_effectiveness_profile(
    *, student_id=None, objective_id=None, task_type=None,
    institution_id=None, subject_family=None, objective_family=None,
    db_path=None,
):
    individual = _individual_profile(
        student_id=student_id,
        objective_id=objective_id,
        task_type=task_type,
        db_path=db_path,
    ) if student_id else {}
    institutional = _institutional_profile(
        institution_id=institution_id,
        subject_family=subject_family,
        objective_family=objective_family,
        task_type=task_type,
        exclude_student_id=student_id,
        db_path=db_path,
    )
    population = _population_audit(
        exclude_student_id=student_id,
        task_type=task_type,
        db_path=db_path,
    )
    return {
        "individual": {k: v.as_dict() for k, v in individual.items()},
        "institutional": {k: v.as_dict() for k, v in institutional.items()},
        # backward-compatible diagnostic view; NEVER used by Planner.
        "aggregate": population,
        "population": population,
    }


def build_population_analytics_payload(
    *, geography_level, geography_key, subject_family, objective_family,
    learners_count, difficulty_count, period,
):
    return {
        "scope": "population",
        "geography_level": geography_level,
        "geography_key": geography_key,
        "subject_family": subject_family,
        "objective_family": objective_family,
        "learners_count": int(learners_count),
        "difficulty_count": int(difficulty_count),
        "period": period,
    }
