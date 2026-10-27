from __future__ import annotations

import json
import os
import statistics
from contextlib import closing
from datetime import datetime, timezone

from s2.storage import connect, ensure_database

VALID_STATUSES = {"valid", "invalid"}
FLOW_TYPES = {
    "learning_request",
    "diagnosis_required",
    "help_request",
    "objective_switch",
    "resume_reassessment",
    "independent_correct",
    "followup",
    "other",
}


def ensure_evaluation_schema(*, db_path=None):
    """Crea la capa de evaluación S3 sin modificar la lógica pedagógica."""
    ensure_database(db_path)
    with closing(connect(db_path)) as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS s3_evaluations (
                evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                benchmark_case_id TEXT NOT NULL UNIQUE,
                benchmark_status TEXT NOT NULL CHECK(benchmark_status IN ('valid','invalid')),
                flow_type TEXT NOT NULL,
                expected_behavior TEXT,
                observed_behavior TEXT,
                quality_pass INTEGER CHECK(quality_pass IN (0,1) OR quality_pass IS NULL),
                notes TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_s3_evaluations_status_flow
            ON s3_evaluations(benchmark_status, flow_type)
            """
        )
        c.commit()


def latest_task_id(*, only_success=True, cost_optimized_only=True, db_path=None):
    ensure_evaluation_schema(db_path=db_path)
    where = []
    args = []
    if only_success:
        where.append("status='success'")
    if cost_optimized_only:
        where.append("cost_optimized=1")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with closing(connect(db_path)) as c:
        row = c.execute(
            f"SELECT task_id FROM task_runs {where_sql} ORDER BY finished_at DESC LIMIT 1",
            tuple(args),
        ).fetchone()
    return row["task_id"] if row else None


def task_exists(task_id, *, db_path=None):
    ensure_evaluation_schema(db_path=db_path)
    with closing(connect(db_path)) as c:
        return c.execute(
            "SELECT 1 FROM task_runs WHERE task_id=?",
            (task_id,),
        ).fetchone() is not None


def upsert_evaluation(
    *,
    task_id,
    benchmark_case_id,
    benchmark_status="valid",
    flow_type="other",
    expected_behavior=None,
    observed_behavior=None,
    quality_pass=None,
    notes=None,
    source="manual",
    db_path=None,
):
    ensure_evaluation_schema(db_path=db_path)
    if benchmark_status not in VALID_STATUSES:
        raise ValueError(f"benchmark_status debe ser uno de {sorted(VALID_STATUSES)}")
    if flow_type not in FLOW_TYPES:
        raise ValueError(f"flow_type debe ser uno de {sorted(FLOW_TYPES)}")
    if not task_exists(task_id, db_path=db_path):
        raise ValueError(f"task_id no existe en task_runs: {task_id}")
    if quality_pass is not None:
        quality_pass = bool(quality_pass)

    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(db_path)) as c:
        c.execute(
            """
            INSERT INTO s3_evaluations(
                task_id, benchmark_case_id, benchmark_status, flow_type,
                expected_behavior, observed_behavior, quality_pass, notes,
                source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                benchmark_case_id=excluded.benchmark_case_id,
                benchmark_status=excluded.benchmark_status,
                flow_type=excluded.flow_type,
                expected_behavior=excluded.expected_behavior,
                observed_behavior=excluded.observed_behavior,
                quality_pass=excluded.quality_pass,
                notes=excluded.notes,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                task_id, benchmark_case_id, benchmark_status, flow_type,
                expected_behavior, observed_behavior,
                None if quality_pass is None else int(quality_pass),
                notes, source, now, now,
            ),
        )
        c.commit()
    return get_evaluation(task_id=task_id, db_path=db_path)


def get_evaluation(*, task_id, db_path=None):
    ensure_evaluation_schema(db_path=db_path)
    with closing(connect(db_path)) as c:
        row = c.execute(
            "SELECT * FROM s3_evaluations WHERE task_id=?",
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def _percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _stats(values):
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {"count": 0, "avg": None, "median": None, "p95": None}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": round(_percentile(values, 0.95), 2),
    }


def _summarize(rows):
    return {
        "tasks": len(rows),
        "reported_tokens": _stats([r.get("total_tokens") for r in rows]),
        "visible_tokens": _stats([r.get("visible_token_sum") for r in rows]),
        "latency_ms": _stats([r.get("total_latency_ms") for r in rows]),
        "llm_calls": _stats([r.get("llm_calls") for r in rows]),
        "tool_calls": _stats([r.get("tool_calls") for r in rows]),
        "estimated_cost_usd": _stats([r.get("estimated_cost_usd") for r in rows]),
        "diagnosis_skipped_rate": (
            round(sum(1 for r in rows if r.get("diagnosis_skipped")) / len(rows), 4)
            if rows else None
        ),
        "quality_success_rate": (
            round(sum(1 for r in rows if r.get("quality_pass") == 1) / len(rows), 4)
            if rows and all(r.get("quality_pass") is not None for r in rows)
            else None
        ),
        "errors": sum(int(r.get("errors") or 0) for r in rows),
        "repairs": sum(int(r.get("repairs") or 0) for r in rows),
    }


def _billing_tokens(row):
    """Devuelve tokens facturables de entrada/salida.

    Los modelos con razonamiento pueden reportar reasoning dentro de total_tokens
    pero fuera de completion_tokens visibles. Por eso la salida facturable se
    deriva como total_reportado - prompt_tokens.
    """
    prompt = int(row.get("diagnosis_prompt_tokens") or 0) + int(row.get("agent_prompt_tokens") or 0)
    total = int(row.get("total_tokens") or 0)
    output_billed = max(0, total - prompt)
    return prompt, output_billed


def _apply_retroactive_cost(rows):
    try:
        input_rate = float(os.getenv("GROK_INPUT_USD_PER_MILLION", ""))
        output_rate = float(os.getenv("GROK_OUTPUT_USD_PER_MILLION", ""))
    except ValueError:
        return rows
    for row in rows:
        if row.get("estimated_cost_usd") is not None:
            continue
        prompt, output_billed = _billing_tokens(row)
        row["estimated_cost_usd"] = (
            prompt * input_rate / 1_000_000
            + output_billed * output_rate / 1_000_000
        )
    return rows


def _reduction_pct(new_value, baseline_value):
    if not isinstance(new_value, (int, float)) or not isinstance(baseline_value, (int, float)) or baseline_value == 0:
        return None
    return round((baseline_value - new_value) / baseline_value * 100, 2)


def evaluation_report(*, include_invalid=False, db_path=None):
    ensure_evaluation_schema(db_path=db_path)
    with closing(connect(db_path)) as c:
        rows = [dict(r) for r in c.execute(
            """
            SELECT e.benchmark_case_id, e.benchmark_status, e.flow_type,
                   e.expected_behavior, e.observed_behavior, e.quality_pass,
                   e.notes, t.*
            FROM s3_evaluations e
            JOIN task_runs t ON t.task_id=e.task_id
            ORDER BY t.finished_at ASC
            """
        ).fetchall()]
        baseline = [dict(r) for r in c.execute(
            """
            SELECT * FROM task_runs
            WHERE status='success' AND cost_optimized=0
            ORDER BY finished_at ASC
            """
        ).fetchall()]
        unmarked_optimized = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM task_runs t
            LEFT JOIN s3_evaluations e ON e.task_id=t.task_id
            WHERE t.status='success' AND t.cost_optimized=1 AND e.task_id IS NULL
            """
        ).fetchone()["n"]

    _apply_retroactive_cost(rows)
    _apply_retroactive_cost(baseline)
    valid = [r for r in rows if r["benchmark_status"] == "valid" and r.get("status") == "success"]
    invalid = [r for r in rows if r["benchmark_status"] == "invalid"]
    by_flow = {}
    for flow in sorted({r["flow_type"] for r in valid}):
        by_flow[flow] = _summarize([r for r in valid if r["flow_type"] == flow])

    valid_summary = _summarize(valid)
    baseline_summary = _summarize(baseline)
    report = {
        "valid_benchmark": valid_summary,
        "by_flow": by_flow,
        "legacy_or_baseline": baseline_summary,
        "comparison_vs_baseline": {
            "reported_tokens_avg_reduction_pct": _reduction_pct(
                valid_summary["reported_tokens"]["avg"], baseline_summary["reported_tokens"]["avg"]
            ),
            "visible_tokens_avg_reduction_pct": _reduction_pct(
                valid_summary["visible_tokens"]["avg"], baseline_summary["visible_tokens"]["avg"]
            ),
            "latency_avg_reduction_pct": _reduction_pct(
                valid_summary["latency_ms"]["avg"], baseline_summary["latency_ms"]["avg"]
            ),
            "tool_calls_avg_reduction_pct": _reduction_pct(
                valid_summary["tool_calls"]["avg"], baseline_summary["tool_calls"]["avg"]
            ),
        },
        "marked_valid": len(valid),
        "marked_invalid": len(invalid),
        "invalid_excluded": len(invalid),
        "unmarked_optimized_excluded": int(unmarked_optimized or 0),
        "note": (
            "El benchmark principal usa solo s3_evaluations con benchmark_status=valid. "
            "Las ejecuciones de desarrollo no marcadas o inválidas quedan fuera."
        ),
    }
    if include_invalid:
        report["invalid_cases"] = [
            {
                "benchmark_case_id": r["benchmark_case_id"],
                "task_id": r["task_id"],
                "flow_type": r["flow_type"],
                "notes": r.get("notes"),
            }
            for r in invalid
        ]
    return report


def report_json(*, include_invalid=False, db_path=None):
    return json.dumps(
        evaluation_report(include_invalid=include_invalid, db_path=db_path),
        ensure_ascii=False,
        indent=2,
    )
