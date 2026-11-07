from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time

from grok_client import DiagnosisGenerationError, analizar_respuesta
from s2.agent import S2AgentError, run_learning_agent
from s2.storage import ensure_database
from s2.tools import get_learning_state


CASES = [
    {
        "case_id": "S2-E2E-01",
        "activity": "¿Cuánto es 7 x 8?",
        "student_answer": "54",
    },
    {
        "case_id": "S2-E2E-02",
        "activity": "Explica brevemente qué ocurre con el agua durante la evaporación.",
        "student_answer": "El agua desaparece y después vuelve.",
    },
    {
        "case_id": "S2-E2E-03",
        "activity": "¿De dónde obtiene una planta la energía que usa en la fotosíntesis?",
        "student_answer": "De la tierra que absorbe por las raíces.",
    },
    {
        "case_id": "S2-E2E-04",
        "activity": "Calcula 1/2 + 1/4.",
        "student_answer": "2/6",
    },
    {
        "case_id": "S2-E2E-05",
        "activity": "Identifica el sujeto en la oración: 'Los perros corren por el parque'.",
        "student_answer": "corren",
    },
    {
        "case_id": "S2-E2E-06",
        "activity": "Un rectángulo mide 5 cm de largo y 3 cm de ancho. ¿Cuál es su área?",
        "student_answer": "8 cm cuadrados",
    },
    {
        "case_id": "S2-E2E-07",
        "activity": "¿Qué cambio de estado ocurre cuando el agua hierve?",
        "student_answer": "Se convierte en aire porque desaparece.",
    },
    {
        "case_id": "S2-E2E-08",
        "activity": "¿En qué año comenzó la Revolución Francesa?",
        "student_answer": "1776",
    },
    {
        "case_id": "S2-E2E-09",
        "activity": "Escribe el pasado simple en inglés del verbo 'go'.",
        "student_answer": "goed",
    },
    {
        "case_id": "S2-E2E-10",
        "activity": "Si sobre el mismo objeto aumenta la fuerza neta y la masa no cambia, ¿qué pasa con su aceleración?",
        "student_answer": "La aceleración disminuye porque el objeto se frena.",
    },
]


def _safe_error_meta(error):
    meta = getattr(error, "meta", None)
    if meta is None:
        return None
    try:
        return asdict(meta)
    except TypeError:
        return str(meta)


def _dump_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_summary(run_id: str, db_path: Path, rows: list[dict]) -> dict:
    completed = [row for row in rows if row.get("status") == "completed"]
    persisted = [row for row in completed if row.get("persistence_verified")]
    token_values = [row["total_tokens"] for row in completed if isinstance(row.get("total_tokens"), int)]
    latency_values = [row["total_latency_ms"] for row in completed if isinstance(row.get("total_latency_ms"), int)]

    return {
        "run_id": run_id,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(db_path),
        "target_e2e": 10,
        "attempted_e2e": len(rows),
        "completed_e2e": len(completed),
        "persistence_verified_e2e": len(persisted),
        "failed_e2e": len(rows) - len(completed),
        "total_llm_calls": sum(row.get("llm_calls_count", 0) or 0 for row in completed),
        "total_tool_calls": sum(row.get("tool_calls_count", 0) or 0 for row in completed),
        "average_tokens": round(statistics.mean(token_values), 2) if token_values else None,
        "average_latency_ms": round(statistics.mean(latency_values), 2) if latency_values else None,
        "requirements": {
            "ten_e2e_attempted": len(rows) == 10,
            "ten_e2e_completed": len(completed) == 10,
            "ten_e2e_persisted": len(persisted) == 10,
        },
    }


def _write_report(path: Path, summary: dict, rows: list[dict]):
    lines = [
        "# NEXA — Evidencia correctiva S2: 10 ejecuciones E2E",
        "",
        "Esta evidencia complementa `REPORTE_TECNICO_S2.md` sin reescribir ni ocultar las sesiones históricas allí documentadas.",
        "",
        "## Alcance",
        "",
        "Cada ejecución procesa una interacción educativa completa:",
        "",
        "`actividad + respuesta → diag.v1.1 → agente S2 → tool calling → respuesta → persistencia SQLite → verificación de estado`.",
        "",
        "Se ejecuta sobre el código actual de `main`, preservando el contrato de las tres herramientas S2:",
        "",
        "1. `get_learning_state`",
        "2. `list_teaching_strategies`",
        "3. `record_learning_event`",
        "",
        "## Resultado",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- Objetivo: **{summary['target_e2e']} E2E**",
        f"- Intentadas: **{summary['attempted_e2e']}**",
        f"- Completadas: **{summary['completed_e2e']}**",
        f"- Persistencia verificada: **{summary['persistence_verified_e2e']}**",
        f"- Fallidas: **{summary['failed_e2e']}**",
        f"- Llamadas LLM: **{summary['total_llm_calls']}**",
        f"- Tool calls observadas: **{summary['total_tool_calls']}**",
        f"- Tokens promedio: **{summary['average_tokens']}**",
        f"- Latencia promedio ms: **{summary['average_latency_ms']}**",
        "",
        "Checks:",
        "",
        "```text",
        f"ten_e2e_attempted: {summary['requirements']['ten_e2e_attempted']}",
        f"ten_e2e_completed: {summary['requirements']['ten_e2e_completed']}",
        f"ten_e2e_persisted: {summary['requirements']['ten_e2e_persisted']}",
        "```",
        "",
        "## Detalle por ejecución",
        "",
        "| Caso | Estado | Persistencia | LLM calls | Tool calls | Tools observadas |",
        "|---|---|---:|---:|---:|---|",
    ]

    for row in rows:
        tools = ", ".join(row.get("tool_names") or []) or "—"
        lines.append(
            f"| {row['case_id']} | {row['status']} | "
            f"{'sí' if row.get('persistence_verified') else 'no'} | "
            f"{row.get('llm_calls_count', 0)} | {row.get('tool_calls_count', 0)} | {tools} |"
        )

    lines += [
        "",
        "## Integridad metodológica",
        "",
        "- Los casos son ejercicios educativos sintéticos y estables; no son datos personales de estudiantes reales.",
        "- La corrida usa la pasarela configurada en `.env` y no simula respuestas del modelo.",
        "- La base de esta evidencia es independiente de la base normal de NEXA.",
        "- Un fallo permanece registrado como fallo; no se convierte en éxito por edición manual.",
        "- Esta corrección añade evidencia reproducible. No cambia la arquitectura ni aumenta el número de tools de S2.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_case(case: dict, *, run_id: str, db_path: Path) -> dict:
    student_id = f"{run_id.lower()}-{case['case_id'].lower()}"
    result = {
        "case_id": case["case_id"],
        "student_id": student_id,
        "activity": case["activity"],
        "student_answer": case["student_answer"],
        "status": "error",
        "stage": None,
    }

    try:
        diagnosis, diagnosis_meta = analizar_respuesta(case["activity"], case["student_answer"])
    except DiagnosisGenerationError as error:
        result["stage"] = "diagnosis"
        result["error"] = str(error)
        result["error_meta"] = _safe_error_meta(error)
        return result

    result["diagnosis"] = diagnosis.model_dump()
    result["diagnosis_tokens"] = diagnosis_meta.total_tokens
    result["diagnosis_latency_ms"] = diagnosis_meta.total_latency_ms

    try:
        final_response, agent_meta = run_learning_agent(
            student_id=student_id,
            activity=case["activity"],
            student_answer=case["student_answer"],
            diagnosis=diagnosis,
            task_id=f"{run_id}-{case['case_id']}",
            db_path=db_path,
            cost_optimized=False,
        )
    except S2AgentError as error:
        result["stage"] = "agent"
        result["error"] = str(error)
        result["error_meta"] = _safe_error_meta(error)
        return result

    tool_names = [trace.name for trace in agent_meta.tools]
    record_ok = any(
        trace.name == "record_learning_event"
        and isinstance(trace.result, dict)
        and trace.result.get("ok") is not False
        and bool(trace.result.get("event_id"))
        for trace in agent_meta.tools
    )

    state_after = get_learning_state(student_id, db_path=db_path)
    attempts_after = state_after.get("attempts_count") if isinstance(state_after, dict) else None
    persistence_verified = bool(
        record_ok
        and isinstance(attempts_after, int)
        and attempts_after >= 1
    )

    agent_tokens = agent_meta.total_tokens if isinstance(agent_meta.total_tokens, int) else 0
    diag_tokens = diagnosis_meta.total_tokens if isinstance(diagnosis_meta.total_tokens, int) else 0

    result.update(
        {
            "status": "completed",
            "stage": "complete",
            "final_response": final_response,
            "tool_names": tool_names,
            "tool_calls_count": len(agent_meta.tools),
            "llm_calls_count": len(agent_meta.calls) + len(diagnosis_meta.calls),
            "agent_llm_calls_count": len(agent_meta.calls),
            "diagnosis_llm_calls_count": len(diagnosis_meta.calls),
            "total_tokens": agent_tokens + diag_tokens,
            "total_latency_ms": agent_meta.total_latency_ms + diagnosis_meta.total_latency_ms,
            "record_learning_event_ok": record_ok,
            "attempts_after": attempts_after,
            "persistence_verified": persistence_verified,
            "episode_action": agent_meta.episode_action,
            "interaction_need": agent_meta.interaction_need,
        }
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="NEXA S2 corrective evidence: exactly 10 E2E executions.")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("s2-e2e10-%Y%m%dT%H%M%SZ"))
    parser.add_argument("--db", default=None)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    args = parser.parse_args()

    run_id = args.run_id.strip()
    db_path = Path(args.db) if args.db else Path("data") / f"{run_id}.db"
    results_path = Path("artifacts") / "S2_E2E_10_RESULTS.jsonl"
    summary_path = Path("artifacts") / "S2_E2E_10_SUMMARY.json"
    report_path = Path("REPORTE_TECNICO_S2_E2E_10.md")

    if db_path.exists():
        print(f"ERROR: la base de evidencia ya existe: {db_path}")
        print("Usa otro --run-id para no mezclar una corrida anterior.")
        return 2

    ensure_database(db_path)
    rows = []

    print("=== NEXA S2 — 10 E2E CORRECTIVOS ===")
    print(f"run_id={run_id}")
    print(f"db={db_path}")
    print("target=10")
    print()

    for index, case in enumerate(CASES, start=1):
        print(f"[{index}/10] {case['case_id']} ...")
        row = run_case(case, run_id=run_id, db_path=db_path)
        rows.append(row)
        _dump_jsonl(results_path, rows)

        if row["status"] == "completed":
            print(
                f"  completed | persisted={row['persistence_verified']} | "
                f"llm={row['llm_calls_count']} | tools={row['tool_calls_count']} | "
                f"tokens={row['total_tokens']}"
            )
        else:
            print(f"  ERROR stage={row.get('stage')}: {row.get('error')}")

        if index < len(CASES) and args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    summary = _build_summary(run_id, db_path, rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report_path, summary, rows)

    print()
    print("=== S2 E2E SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print(f"results={results_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")

    checks = summary["requirements"]
    ok = checks["ten_e2e_attempted"] and checks["ten_e2e_completed"] and checks["ten_e2e_persisted"]
    print(f"S2_E2E_10_OK={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
