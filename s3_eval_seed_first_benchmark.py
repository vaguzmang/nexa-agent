from __future__ import annotations

from s3.evaluation import task_exists, upsert_evaluation


CASES = [
    {
        "case": "S3-B01",
        "task_id": "task-35419bcf-754e-46a1-bcc1-ab51cb3c555a",
        "flow": "learning_request",
        "expected": "Nueva solicitud procedural sin diagnóstico; elegir estrategia pedagógica elegible.",
        "observed": "worked_example; diagnóstico omitido; respuesta seguida de práctica.",
    },
    {
        "case": "S3-B02",
        "task_id": "task-eb49ddf5-95c5-494d-a272-50a713b35fb2",
        "flow": "learning_request",
        "expected": "Nueva solicitud conceptual sin diagnóstico.",
        "observed": "concept_explanation; diagnóstico omitido; pregunta de comprobación.",
    },
    {
        "case": "S3-B03",
        "task_id": "task-8318d476-dc95-4daf-a439-8154297a3d40",
        "flow": "diagnosis_required",
        "expected": "Detectar intento parcial y brecha de procedimiento.",
        "observed": "partial/incomplete_procedure; hint de bajo apoyo.",
    },
    {
        "case": "S3-B04",
        "task_id": "task-a958b6e0-7ef1-4a3e-86bc-f3d258ab646b",
        "flow": "diagnosis_required",
        "expected": "Detectar misconception en distributiva y enseñar el punto exacto.",
        "observed": "does_not_meet/misconception; contrast_example.",
    },
    {
        "case": "S3-B05",
        "task_id": "task-536d4ea8-3b32-43a3-b0be-8f34e3d2e651",
        "flow": "help_request",
        "expected": "Solicitud de explicación sin diagnosticar un intento inexistente.",
        "observed": "diagnóstico omitido; concept_explanation; nueva pregunta.",
    },
    {
        "case": "S3-B06",
        "task_id": "task-99824655-5a8e-47a8-a224-eeab825a0ff4",
        "flow": "objective_switch",
        "expected": "Cambiar de fotosíntesis a matemáticas sin marcar la estrategia previa como failed.",
        "observed": "switch_objective; topic_switched_before_attempt; nuevo episodio.",
    },
    {
        "case": "S3-B07",
        "task_id": "task-31747e07-f7b4-4259-9380-e6e479f2bd1e",
        "flow": "resume_reassessment",
        "expected": "Reanudar objetivo suspendido y preguntar qué conserva antes de reenseñar.",
        "observed": "resume_suspended; reassess_recall; 1 LLM call, 0 tools.",
    },
    {
        "case": "S3-B08",
        "task_id": "task-e3948d8d-5065-46c5-99db-35b301c1d11a",
        "flow": "independent_correct",
        "expected": "Reconocer respuesta correcta independiente sin declarar mastery.",
        "observed": "meets; independent_practice; sin afirmación de mastery.",
    },
]


def main():
    inserted = 0
    missing = []
    for item in CASES:
        if not task_exists(item["task_id"]):
            missing.append((item["case"], item["task_id"]))
            continue
        upsert_evaluation(
            task_id=item["task_id"],
            benchmark_case_id=item["case"],
            benchmark_status="valid",
            flow_type=item["flow"],
            expected_behavior=item["expected"],
            observed_behavior=item["observed"],
            quality_pass=True,
            notes="Primera batería controlada S3 validada durante desarrollo.",
            source="seed_first_benchmark",
        )
        inserted += 1

    print(f"Casos válidos cargados: {inserted}/{len(CASES)}")
    if missing:
        print("No encontrados en esta base:")
        for case, task_id in missing:
            print(f"  {case}: {task_id}")
        raise SystemExit(2)
    print("OK: primera batería S3 marcada como benchmark válido.")


if __name__ == "__main__":
    main()
