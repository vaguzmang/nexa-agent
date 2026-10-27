from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from s2.storage import connect
from s3.evaluation import evaluation_report, ensure_evaluation_schema

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "REPORTE_TECNICO_S3.md"
FAILURES = ROOT / "artifacts" / "S3_BATCH_FAILURES.jsonl"


def fmt(value, suffix=""):
    return "N/D" if value is None else f"{value}{suffix}"


def pct(num, den):
    if not den:
        return None
    return round(100.0 * num / den, 2)


def load_technical_failures():
    rows = []
    if not FAILURES.exists():
        return rows
    for line in FAILURES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"case_id": "unknown", "error_type": "invalid_jsonl", "error": line[:300]})
    return rows


def main():
    ensure_evaluation_schema()
    r = evaluation_report()
    v = r["valid_benchmark"]
    b = r["legacy_or_baseline"]
    c = r["comparison_vs_baseline"]

    with closing(connect()) as connection:
        eval_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT benchmark_case_id, quality_pass, flow_type,
                       expected_behavior, observed_behavior, notes
                FROM s3_evaluations
                WHERE benchmark_status='valid'
                ORDER BY benchmark_case_id
                """
            ).fetchall()
        ]

    valid_ids = {row["benchmark_case_id"] for row in eval_rows}
    quality_fail_rows = [row for row in eval_rows if int(row.get("quality_pass") or 0) == 0]
    quality_pass_count = sum(1 for row in eval_rows if int(row.get("quality_pass") or 0) == 1)

    failure_attempts = load_technical_failures()
    technical_failure_ids = sorted(
        {
            row.get("case_id")
            for row in failure_attempts
            if row.get("case_id") and row.get("case_id") not in valid_ids
        }
    )
    technical_failure_attempts = [
        row for row in failure_attempts if row.get("case_id") in technical_failure_ids
    ]

    completed = len(eval_rows)
    technical_failed_cases = len(technical_failure_ids)
    target_cases = completed + technical_failed_cases
    technical_completion_rate = pct(completed, target_cases)
    quality_rate_completed = pct(quality_pass_count, completed)
    integral_success_rate = pct(quality_pass_count, target_cases)

    lines = [
        "# NEXA — REPORTE TÉCNICO S3",
        "",
        "## 1. Objetivo",
        "",
        "S3 valida NEXA con ejecuciones end-to-end, una evaluación propia reproducible y medición de costo por tarea.",
        "",
        "## 2. Naturaleza y cobertura de los datos",
        "",
        f"- Escenarios objetivo del set controlado: **{target_cases}**.",
        f"- Ejecuciones end-to-end completadas y registradas: **{completed}**.",
        f"- Escenarios con fallo técnico persistente sin `task_run`: **{technical_failed_cases}**.",
        f"- Intentos técnicos fallidos registrados para esos escenarios: **{len(technical_failure_attempts)}**.",
        f"- Ejecuciones optimizadas de desarrollo no marcadas y excluidas: **{r['unmarked_optimized_excluded']}**.",
        "- Los casos son **ejecuciones reales del agente contra el modelo/gateway**, diseñadas de forma controlada.",
        "- No se presentan como una cohorte natural ni como datos personales de estudiantes reales.",
        "- Los bancos sintéticos previos se usan solo para diseño adversarial y no se contabilizan como datos reales de S3.",
        "",
        "## 3. Evaluación propia",
        "",
        "La evaluación contract-based revisa por caso la clasificación del turno, necesidad de diagnóstico, resultado/gap cuando aplica, continuidad de objetivo/episodio, señales de retrieval/transfer, ausencia de pseudo-tool-calls, ausencia de mastery no sustentado y ejecución sin errores.",
        "",
        f"- Quality pass entre ejecuciones completas: **{quality_pass_count}/{completed} ({fmt(quality_rate_completed, '%')})**.",
        f"- Completitud técnica del set: **{completed}/{target_cases} ({fmt(technical_completion_rate, '%')})**.",
        f"- Éxito integral del set (quality pass / todos los escenarios objetivo): **{quality_pass_count}/{target_cases} ({fmt(integral_success_rate, '%')})**.",
        f"- Quality fails conservados en el benchmark: **{len(quality_fail_rows)}**.",
        f"- Repairs acumulados en ejecuciones completas: **{v['repairs']}**.",
        "",
        "### Casos que no pasaron la evaluación",
        "",
    ]

    if quality_fail_rows:
        for row in quality_fail_rows:
            try:
                expected = json.loads(row.get("expected_behavior") or "{}")
            except json.JSONDecodeError:
                expected = row.get("expected_behavior")
            try:
                observed = json.loads(row.get("observed_behavior") or "{}")
            except json.JSONDecodeError:
                observed = row.get("observed_behavior")
            lines += [
                f"- **{row['benchmark_case_id']}** ({row.get('flow_type')}): quality fail.",
                f"  - esperado: `{json.dumps(expected, ensure_ascii=False)}`",
                f"  - observado: `{json.dumps(observed, ensure_ascii=False)}`",
            ]
    else:
        lines.append("- Ninguno.")

    if technical_failure_ids:
        lines += ["", "### Fallos técnicos persistentes", ""]
        for case_id in technical_failure_ids:
            attempts = [row for row in technical_failure_attempts if row.get("case_id") == case_id]
            lines.append(f"- **{case_id}**: {len(attempts)} intento(s) técnico(s) fallido(s).")
            for attempt in attempts:
                lines.append(
                    f"  - `{attempt.get('error_type', 'Error')}`: {attempt.get('error', 'sin detalle')}"
                )

    lines += [
        "",
        "## 4. Costo y rendimiento por tarea completada",
        "",
        f"- Tokens reportados promedio: **{fmt(v['reported_tokens']['avg'])}**",
        f"- Mediana: **{fmt(v['reported_tokens']['median'])}**",
        f"- p95: **{fmt(v['reported_tokens']['p95'])}**",
        f"- Tokens visibles promedio: **{fmt(v['visible_tokens']['avg'])}**",
        f"- Latencia promedio: **{fmt(v['latency_ms']['avg'], ' ms')}**",
        f"- LLM calls promedio: **{fmt(v['llm_calls']['avg'])}**",
        f"- Tool calls promedio: **{fmt(v['tool_calls']['avg'])}**",
        f"- Costo USD estimado promedio: **{fmt(v['estimated_cost_usd']['avg'])}**",
        f"- Costo USD estimado mediana: **{fmt(v['estimated_cost_usd']['median'])}**",
        f"- Costo USD estimado p95: **{fmt(v['estimated_cost_usd']['p95'])}**",
        "",
        "El costo USD se calcula con las tarifas configuradas. Para la estimación de referencia de esta evaluación se usaron US$2/M input y US$6/M output; los reasoning tokens se tratan como output facturable. Esta estimación no equivale ni pretende reconstruir los créditos internos del gateway del reto.",
        "",
        "## 5. Comparación con baseline",
        "",
        f"- Baseline tokens promedio: **{fmt(b['reported_tokens']['avg'])}**",
        f"- Reducción de tokens reportados: **{fmt(c['reported_tokens_avg_reduction_pct'], '%')}**",
        f"- Reducción de tokens visibles: **{fmt(c['visible_tokens_avg_reduction_pct'], '%')}**",
        f"- Reducción observada de latencia: **{fmt(c['latency_avg_reduction_pct'], '%')}**",
        f"- Reducción de tool calls: **{fmt(c['tool_calls_avg_reduction_pct'], '%')}**",
        "",
        "## 6. Resultados por flujo",
        "",
    ]

    for flow, item in r["by_flow"].items():
        lines += [
            f"### {flow}",
            f"- tareas completadas: {item['tasks']}",
            f"- tokens avg / median / p95: {item['reported_tokens']['avg']} / {item['reported_tokens']['median']} / {item['reported_tokens']['p95']}",
            f"- latencia promedio: {item['latency_ms']['avg']} ms",
            f"- quality success rate: {item['quality_success_rate']}",
            f"- costo USD promedio: {item['estimated_cost_usd']['avg']}",
            "",
        ]

    lines += [
        "## 7. Controles metodológicos",
        "",
        "- Un fallo de calidad del agente **no se elimina** del benchmark: permanece como caso válido con `quality_pass=false`.",
        "- Un fallo técnico que impide producir `task_run` se conserva en `artifacts/S3_BATCH_FAILURES.jsonl` y se contabiliza en la cobertura integral del set.",
        "- Solo se excluyen pruebas de desarrollo/montaje explícitamente fuera del benchmark.",
        "- `meets` no se interpreta como mastery.",
        "- Una interrupción por cambio de tema no se registra como fracaso de estrategia.",
        "- La analítica poblacional no interviene en el ranking pedagógico individual.",
        "",
        "## 8. Limitaciones",
        "",
        "- El benchmark controlado no sustituye una validación longitudinal con una cohorte natural de estudiantes.",
        "- La latencia depende también del gateway y del proveedor.",
        "- El costo USD de referencia usa tarifas configuradas; los créditos internos del reto pueden seguir otra regla.",
        "- El escenario técnico fallido se reporta como limitación reproducible y no se oculta del resultado integral.",
        "",
        "## 9. Evidencias reproducibles",
        "",
        "- `python -m unittest discover -s tests -v`",
        "- `python s3_eval_report.py`",
        "- `python s3_eval_export.py`",
        "- `python s3_build_report.py`",
        "- `artifacts/S3_BATCH_FAILURES.jsonl`",
        "",
    ]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)
    print(f"Escenarios objetivo: {target_cases}")
    print(f"Completados: {completed}")
    print(f"Quality pass: {quality_pass_count}")
    print(f"Fallos técnicos persistentes: {technical_failed_cases}")
    print(f"Éxito integral: {fmt(integral_success_rate, '%')}")


if __name__ == "__main__":
    main()
