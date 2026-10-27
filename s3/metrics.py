import os
from contextlib import closing
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from s2.storage import connect, ensure_database


def _as_dict(value):
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return value.__dict__ if hasattr(value, "__dict__") else {}


def _calls(meta):
    raw = getattr(meta, "calls", None)
    if raw is None and isinstance(meta, dict):
        raw = meta.get("calls")
    return list(raw or [])


def _sum_call_field(calls, field):
    if not calls:
        return 0
    values = []
    for call in calls:
        data = _as_dict(call)
        value = data.get(field)
        if isinstance(value, int) and value >= 0:
            values.append(value)
        else:
            return None
    return sum(values)


def _optional_sum(a, b):
    return a + b if a is not None and b is not None else None


def _rate(name):
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _reported_total(meta, calls):
    if meta is None:
        return 0
    value = getattr(meta, "total_tokens", None)
    if value is None and isinstance(meta, dict):
        value = meta.get("total_tokens")
    if isinstance(value, int) and value >= 0:
        return value
    return _sum_call_field(calls, "total_tokens")


def _latency(meta):
    if meta is None:
        return 0
    value = getattr(meta, "total_latency_ms", None)
    if value is None and isinstance(meta, dict):
        value = meta.get("total_latency_ms")
    return value if isinstance(value, int) and value >= 0 else None


def build_task_metrics(
    *,
    task_id,
    diagnosis_meta,
    agent_meta,
    student_id=None,
    episode_id=None,
    objective_id=None,
    started_at=None,
    diagnosis_skipped=False,
    errors=0,
    status="success",
    cost_optimized=False,
):
    diagnosis_calls = _calls(diagnosis_meta)
    agent_calls = _calls(agent_meta)

    d_prompt = _sum_call_field(diagnosis_calls, "prompt_tokens")
    d_completion = _sum_call_field(diagnosis_calls, "completion_tokens")
    a_prompt = _sum_call_field(agent_calls, "prompt_tokens")
    a_completion = _sum_call_field(agent_calls, "completion_tokens")

    d_reported = _reported_total(diagnosis_meta, diagnosis_calls)
    a_reported = _reported_total(agent_meta, agent_calls)
    d_visible = _optional_sum(d_prompt, d_completion)
    a_visible = _optional_sum(a_prompt, a_completion)

    d_latency = _latency(diagnosis_meta)
    a_latency = _latency(agent_meta)

    prompt_total = _optional_sum(d_prompt, a_prompt)
    reported_total = _optional_sum(d_reported, a_reported)
    # Reasoning puede estar en total_tokens y no en completion_tokens visibles.
    # El proveedor factura reasoning como output, por lo que derivamos la salida
    # facturable como total reportado menos prompt.
    billed_output_total = (
        max(0, reported_total - prompt_total)
        if reported_total is not None and prompt_total is not None
        else None
    )
    input_rate = _rate("GROK_INPUT_USD_PER_MILLION")
    output_rate = _rate("GROK_OUTPUT_USD_PER_MILLION")
    estimated_cost = None
    if (
        input_rate is not None
        and output_rate is not None
        and prompt_total is not None
        and billed_output_total is not None
    ):
        estimated_cost = (
            prompt_total * input_rate / 1_000_000
            + billed_output_total * output_rate / 1_000_000
        )

    repair_count = sum(
        1 for call in diagnosis_calls if _as_dict(call).get("kind") == "repair"
    )
    tools = getattr(agent_meta, "tools", None)
    if tools is None and isinstance(agent_meta, dict):
        tools = agent_meta.get("tools")

    now = datetime.now(timezone.utc).isoformat()
    return {
        "task_id": task_id,
        "student_id": student_id,
        "episode_id": episode_id,
        "objective_id": objective_id,
        "started_at": started_at or now,
        "finished_at": now,
        "diagnosis_skipped": bool(diagnosis_skipped),
        "diagnosis_prompt_tokens": d_prompt,
        "diagnosis_completion_tokens": d_completion,
        # Backward-compatible field: reported total from gateway/SDK.
        "diagnosis_tokens": d_reported,
        "diagnosis_visible_tokens": d_visible,
        "agent_prompt_tokens": a_prompt,
        "agent_completion_tokens": a_completion,
        # Backward-compatible field: reported total from gateway/SDK.
        "agent_tokens": a_reported,
        "agent_visible_tokens": a_visible,
        "total_tokens": _optional_sum(d_reported, a_reported),
        "visible_token_sum": _optional_sum(d_visible, a_visible),
        "diagnosis_latency_ms": d_latency,
        "agent_latency_ms": a_latency,
        "total_latency_ms": _optional_sum(d_latency, a_latency),
        "llm_calls": len(diagnosis_calls) + len(agent_calls),
        "tool_calls": len(list(tools or [])),
        "repairs": repair_count,
        "errors": int(errors),
        "estimated_cost_usd": estimated_cost,
        "status": status,
        "cost_optimized": bool(cost_optimized),
    }


def persist_task_metrics(metrics, *, db_path=None):
    ensure_database(db_path)
    columns = [
        "task_id", "student_id", "episode_id", "objective_id", "started_at", "finished_at",
        "diagnosis_prompt_tokens", "diagnosis_completion_tokens", "diagnosis_tokens",
        "agent_prompt_tokens", "agent_completion_tokens", "agent_tokens", "total_tokens",
        "diagnosis_latency_ms", "agent_latency_ms", "total_latency_ms", "llm_calls",
        "tool_calls", "repairs", "errors", "estimated_cost_usd", "status",
        "diagnosis_skipped", "diagnosis_visible_tokens", "agent_visible_tokens", "visible_token_sum",
        "cost_optimized",
    ]
    values = [metrics.get(column) for column in columns]
    placeholders = ",".join("?" for _ in columns)
    assignments = ",".join(f"{column}=excluded.{column}" for column in columns[1:])
    with closing(connect(db_path)) as connection:
        connection.execute(
            f"""
            INSERT INTO task_runs({','.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(task_id) DO UPDATE SET {assignments}
            """,
            values,
        )
        connection.commit()
    return metrics
