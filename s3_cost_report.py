from __future__ import annotations

import argparse
import json
import os
import statistics
from contextlib import closing

from s2.storage import connect, ensure_database


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def stats(values):
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {"count": 0, "avg": None, "median": None, "p95": None}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": round(percentile(values, 0.95), 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Reporte local S3: tokens, latencia y costo por tarea.")
    parser.add_argument("--limit", type=int, default=500, help="Máximo de task_runs recientes.")
    parser.add_argument("--json", action="store_true", help="Salida JSON.")
    args = parser.parse_args()

    ensure_database()
    with closing(connect()) as c:
        rows = c.execute(
            """
            SELECT task_id, total_tokens, visible_token_sum, total_latency_ms,
                   diagnosis_prompt_tokens, diagnosis_completion_tokens,
                   agent_prompt_tokens, agent_completion_tokens,
                   llm_calls, tool_calls, estimated_cost_usd,
                   diagnosis_skipped, cost_optimized, status
            FROM task_runs
            ORDER BY finished_at DESC
            LIMIT ?
            """,
            (max(1, min(args.limit, 5000)),),
        ).fetchall()

    rows = [dict(r) for r in rows if r["status"] == "success"]

    # Si se configuran tarifas después de ejecutar las tareas, el reporte puede
    # estimar retroactivamente el costo a partir de prompt/completion tokens.
    try:
        input_rate = float(os.getenv("GROK_INPUT_USD_PER_MILLION", ""))
        output_rate = float(os.getenv("GROK_OUTPUT_USD_PER_MILLION", ""))
    except ValueError:
        input_rate = output_rate = None
    if input_rate is not None and output_rate is not None:
        for r in rows:
            if r.get("estimated_cost_usd") is not None:
                continue
            prompt = sum(int(r.get(k) or 0) for k in ("diagnosis_prompt_tokens", "agent_prompt_tokens"))
            completion = sum(int(r.get(k) or 0) for k in ("diagnosis_completion_tokens", "agent_completion_tokens"))
            r["estimated_cost_usd"] = prompt * input_rate / 1_000_000 + completion * output_rate / 1_000_000
    optimized = [r for r in rows if r.get("cost_optimized")]
    legacy = [r for r in rows if not r.get("cost_optimized")]

    def summarize(group):
        return {
            "tasks": len(group),
            "reported_tokens": stats([r.get("total_tokens") for r in group]),
            "visible_tokens": stats([r.get("visible_token_sum") for r in group]),
            "latency_ms": stats([r.get("total_latency_ms") for r in group]),
            "llm_calls": stats([r.get("llm_calls") for r in group]),
            "tool_calls": stats([r.get("tool_calls") for r in group]),
            "estimated_cost_usd": stats([r.get("estimated_cost_usd") for r in group]),
            "diagnosis_skipped_rate": (
                round(sum(1 for r in group if r.get("diagnosis_skipped")) / len(group), 4)
                if group else None
            ),
        }

    report = {
        "all": summarize(rows),
        "cost_optimized": summarize(optimized),
        "legacy_or_baseline": summarize(legacy),
        "note": (
            "estimated_cost_usd requiere GROK_INPUT_USD_PER_MILLION y "
            "GROK_OUTPUT_USD_PER_MILLION. Compare tareas equivalentes; no mezcle "
            "casos de dificultad muy distinta al evaluar ahorro."
        ),
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("\nNEXA S3 — COSTO POR TAREA\n")
    for label in ["all", "cost_optimized", "legacy_or_baseline"]:
        item = report[label]
        print(label.upper())
        print(f"  tareas: {item['tasks']}")
        for metric in ["reported_tokens", "visible_tokens", "latency_ms", "llm_calls", "tool_calls", "estimated_cost_usd"]:
            d = item[metric]
            print(f"  {metric}: avg={d['avg']} median={d['median']} p95={d['p95']}")
        print(f"  diagnosis_skipped_rate: {item['diagnosis_skipped_rate']}")
        print()


if __name__ == "__main__":
    main()
