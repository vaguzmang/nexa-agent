from __future__ import annotations

import argparse
import json

from s3.evaluation import evaluation_report


def _print_stats(label, item):
    print(label)
    print(f"  tareas: {item['tasks']}")
    for metric in [
        "reported_tokens", "visible_tokens", "latency_ms",
        "llm_calls", "tool_calls", "estimated_cost_usd",
    ]:
        d = item[metric]
        print(f"  {metric}: avg={d['avg']} median={d['median']} p95={d['p95']}")
    print(f"  diagnosis_skipped_rate: {item['diagnosis_skipped_rate']}")
    print(f"  quality_success_rate: {item['quality_success_rate']}")
    print(f"  errors: {item['errors']}")
    print(f"  repairs: {item['repairs']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Reporte S3 limpio: solo benchmark marcado.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--include-invalid", action="store_true")
    args = parser.parse_args()

    report = evaluation_report(include_invalid=args.include_invalid)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("\nNEXA S3 — EVALUATION HARNESS\n")
    import os
    if os.getenv("GROK_INPUT_USD_PER_MILLION") and os.getenv("GROK_OUTPUT_USD_PER_MILLION"):
        print(f"Costo estimado: input=${os.getenv('GROK_INPUT_USD_PER_MILLION')}/1M, output=${os.getenv('GROK_OUTPUT_USD_PER_MILLION')}/1M (reasoning incluido como output).\n")
    print(f"Marcados válidos: {report['marked_valid']}")
    print(f"Marcados inválidos/excluidos: {report['marked_invalid']}")
    print(f"Optimizados sin marcar/excluidos: {report['unmarked_optimized_excluded']}\n")
    _print_stats("VALID BENCHMARK", report["valid_benchmark"])

    print("POR TIPO DE FLUJO")
    for flow, item in report["by_flow"].items():
        print(f"\n[{flow}]")
        _print_stats("", item)

    _print_stats("LEGACY / BASELINE", report["legacy_or_baseline"])
    c = report["comparison_vs_baseline"]
    print("COMPARACIÓN VS BASELINE")
    print(f"  reducción tokens reportados promedio: {c['reported_tokens_avg_reduction_pct']}%")
    print(f"  reducción tokens visibles promedio: {c['visible_tokens_avg_reduction_pct']}%")
    print(f"  reducción latencia promedio: {c['latency_avg_reduction_pct']}%")
    print(f"  reducción tool calls promedio: {c['tool_calls_avg_reduction_pct']}%")
    print()
    print(report["note"])


if __name__ == "__main__":
    main()
