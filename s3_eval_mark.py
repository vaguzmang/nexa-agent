from __future__ import annotations

import argparse
import json

from s3.evaluation import FLOW_TYPES, latest_task_id, upsert_evaluation


def main():
    parser = argparse.ArgumentParser(
        description="Marca una ejecución S3 para el benchmark limpio de evaluación."
    )
    parser.add_argument("--case", required=True, help="ID del caso, ej. S3-009")
    parser.add_argument("--task-id", help="task_id; si se omite usa la última tarea optimizada exitosa")
    parser.add_argument("--flow", choices=sorted(FLOW_TYPES), default="other")
    status = parser.add_mutually_exclusive_group(required=True)
    status.add_argument("--valid", action="store_true")
    status.add_argument("--invalid", action="store_true")
    quality = parser.add_mutually_exclusive_group()
    quality.add_argument("--pass-quality", action="store_true")
    quality.add_argument("--fail-quality", action="store_true")
    parser.add_argument("--expected", default=None)
    parser.add_argument("--observed", default=None)
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    task_id = args.task_id or latest_task_id()
    if not task_id:
        raise SystemExit("No se encontró una tarea reciente para marcar.")

    quality_pass = None
    if args.pass_quality:
        quality_pass = True
    elif args.fail_quality:
        quality_pass = False

    row = upsert_evaluation(
        task_id=task_id,
        benchmark_case_id=args.case,
        benchmark_status="valid" if args.valid else "invalid",
        flow_type=args.flow,
        expected_behavior=args.expected,
        observed_behavior=args.observed,
        quality_pass=quality_pass,
        notes=args.notes,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
