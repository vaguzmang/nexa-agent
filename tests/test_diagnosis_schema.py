import unittest

from pydantic import ValidationError

from schemas.diagnosis import DiagnosisResult


class TestDiagnosisResult(unittest.TestCase):

    def test_valid_closed_ended_gap(self):
        result = DiagnosisResult(
            objective={
                "domain": "mathematics",
                "skill": "multiplicación mediante descomposición",
            },
            evidence={
                "type": "closed_ended",
                "result": "does_not_meet",
                "summary": (
                    "El estudiante respondió 84 "
                    "cuando debía resolver 12 x 8."
                ),
            },
            understanding={
                "demonstrated": (
                    "Reconoce que debe realizar "
                    "una multiplicación."
                ),
                "missing": (
                    "No aplica correctamente "
                    "la relación entre los factores."
                ),
            },
            gap={
                "present": True,
                "type": "misconception",
                "description": (
                    "Posible confusión entre "
                    "12 x 7 y 12 x 8."
                ),
            },
            next_step="teach",
        )

        self.assertEqual(
            result.schema_version,
            "diag.v1.1",
        )

        self.assertTrue(
            result.gap.present
        )

    def test_valid_rubric(self):
        result = DiagnosisResult(
            objective={
                "domain": "language",
                "skill": "construcción de argumentos",
            },
            evidence={
                "type": "rubric",
                "result": "partial",
                "summary": (
                    "La respuesta presenta una tesis "
                    "pero evidencia insuficiente."
                ),
                "criteria": [
                    {
                        "name": "Tesis clara",
                        "result": "meets",
                    },
                    {
                        "name": "Uso de evidencia",
                        "result": "does_not_meet",
                    },
                ],
            },
            understanding={
                "demonstrated": (
                    "Formula una posición clara."
                ),
                "missing": (
                    "No sustenta las afirmaciones "
                    "con evidencia."
                ),
            },
            gap={
                "present": True,
                "type": "missing_prerequisite",
                "description": (
                    "Falta integrar evidencia "
                    "al argumento."
                ),
            },
            next_step="teach",
        )

        self.assertEqual(
            result.evidence.result,
            "partial",
        )

    def test_rubric_all_partial_reduces_to_partial(self):
        result = DiagnosisResult(
            objective={
                "domain": "language",
                "skill": "argumentación escrita",
            },
            evidence={
                "type": "rubric",
                "result": "partial",
                "summary": "Todos los criterios se cumplen parcialmente.",
                "criteria": [
                    {"name": "Tesis", "result": "partial"},
                    {"name": "Evidencia", "result": "partial"},
                ],
            },
            understanding={
                "demonstrated": "Avanza parcialmente en ambos criterios.",
                "missing": "Debe completar la tesis y su sustento.",
            },
            gap={
                "present": True,
                "type": "incomplete_procedure",
                "description": "La respuesta está incompleta.",
            },
            next_step="practice",
        )

        self.assertEqual(result.evidence.result, "partial")

    def test_rubric_insufficient_evidence_needs_no_criteria(self):
        result = DiagnosisResult(
            objective={
                "domain": "language",
                "skill": "argumentación escrita",
            },
            evidence={
                "type": "rubric",
                "result": "insufficient_evidence",
                "summary": "La entrega está en blanco.",
            },
            understanding={
                "demonstrated": None,
                "missing": None,
            },
            gap={
                "present": False,
                "type": "none",
                "description": None,
            },
            next_step="ask_clarifying",
        )

        self.assertIsNone(result.evidence.criteria)
        self.assertIsNone(result.understanding.demonstrated)

    def test_rubric_insufficient_evidence_rejects_scored_criteria(self):
        with self.assertRaises(ValidationError):
            DiagnosisResult(
                objective={
                    "domain": "language",
                    "skill": "argumentación escrita",
                },
                evidence={
                    "type": "rubric",
                    "result": "insufficient_evidence",
                    "summary": "La entrega está en blanco.",
                    "criteria": [
                        {"name": "Tesis", "result": "does_not_meet"},
                    ],
                },
                understanding={
                    "demonstrated": None,
                    "missing": None,
                },
                gap={
                    "present": False,
                    "type": "none",
                    "description": None,
                },
                next_step="ask_clarifying",
            )

    def test_insufficient_evidence_requires_clarification(self):
        result = DiagnosisResult(
            objective={
                "domain": "science",
                "skill": "explicar la fotosíntesis",
            },
            evidence={
                "type": "open_ended",
                "result": "insufficient_evidence",
                "summary": (
                    "La respuesta es demasiado breve "
                    "para evaluar comprensión."
                ),
            },
            understanding={
                "demonstrated": (
                    "No hay evidencia suficiente."
                ),
                "missing": (
                    "No puede determinarse todavía."
                ),
            },
            gap={
                "present": False,
                "type": "none",
                "description": None,
            },
            next_step="ask_clarifying",
        )

        self.assertFalse(
            result.gap.present
        )

    def test_rubric_requires_criteria(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "history",
                    "skill": "argumentación histórica",
                },
                evidence={
                    "type": "rubric",
                    "result": "partial",
                    "summary": "Respuesta incompleta.",
                },
                understanding={
                    "demonstrated": "Presenta una idea.",
                    "missing": "Falta evidencia.",
                },
                gap={
                    "present": True,
                    "type": "missing_prerequisite",
                    "description": "Falta evidencia.",
                },
                next_step="teach",
            )

    def test_meets_does_not_mean_mastery(self):
        result = DiagnosisResult(
            objective={
                "domain": "programming",
                "skill": "usar una condición if",
            },
            evidence={
                "type": "open_ended",
                "result": "meets",
                "summary": (
                    "El estudiante resolvió correctamente "
                    "este ejercicio."
                ),
            },
            understanding={
                "demonstrated": (
                    "Aplica correctamente una condición."
                ),
                "missing": None,
            },
            gap={
                "present": False,
                "type": "none",
                "description": None,
            },
            next_step="practice",
        )

        self.assertEqual(
            result.next_step,
            "practice",
        )

        self.assertFalse(
            hasattr(result, "mastery_state")
        )

    def test_meets_with_missing_understanding_is_rejected(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "programming",
                    "skill": "usar una condición if",
                },
                evidence={
                    "type": "open_ended",
                    "result": "meets",
                    "summary": (
                        "El ejercicio produce "
                        "el resultado esperado."
                    ),
                },
                understanding={
                    "demonstrated": (
                        "Construye correctamente "
                        "la condición."
                    ),
                    "missing": (
                        "Todavía confunde cuándo "
                        "usar elif."
                    ),
                },
                gap={
                    "present": False,
                    "type": "none",
                    "description": None,
                },
                next_step="practice",
            )

    def test_extra_mastery_field_is_rejected(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "mathematics",
                    "skill": "fracciones",
                },
                evidence={
                    "type": "closed_ended",
                    "result": "meets",
                    "summary": (
                        "La evidencia del turno "
                        "cumple el objetivo."
                    ),
                },
                understanding={
                    "demonstrated": (
                        "Resuelve correctamente."
                    ),
                    "missing": None,
                },
                gap={
                    "present": False,
                    "type": "none",
                    "description": None,
                },
                next_step="practice",
                mastery_state="MASTERED",
            )

    def test_uncertain_gap_requires_clarification(self):
        result = DiagnosisResult(
            objective={
                "domain": "mathematics",
                "skill": "resolver ecuaciones lineales",
            },
            evidence={
                "type": "open_ended",
                "result": "partial",
                "summary": (
                    "El estudiante inicia correctamente "
                    "pero llega a un resultado incorrecto."
                ),
            },
            understanding={
                "demonstrated": (
                    "Reconoce que debe aislar la variable."
                ),
                "missing": (
                    "No hay evidencia suficiente para "
                    "determinar la causa exacta del error."
                ),
            },
            gap={
                "present": True,
                "type": "uncertain",
                "description": (
                    "Existe una dificultad, pero todavía "
                    "no puede clasificarse con evidencia."
                ),
            },
            next_step="ask_clarifying",
        )

        self.assertEqual(
            result.gap.type,
            "uncertain",
        )

        self.assertEqual(
            result.next_step,
            "ask_clarifying",
        )

    def test_uncertain_gap_cannot_go_directly_to_teach(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "science",
                    "skill": "explicar la gravedad",
                },
                evidence={
                    "type": "open_ended",
                    "result": "partial",
                    "summary": (
                        "La explicación contiene "
                        "una afirmación incorrecta."
                    ),
                },
                understanding={
                    "demonstrated": (
                        "Relaciona gravedad "
                        "con atracción."
                    ),
                    "missing": (
                        "La causa exacta de la confusión "
                        "todavía no está clara."
                    ),
                },
                gap={
                    "present": True,
                    "type": "uncertain",
                    "description": (
                        "Se necesita más evidencia "
                        "antes de clasificar la brecha."
                    ),
                },
                next_step="teach",
            )

    def test_uncertain_gap_cannot_go_directly_to_practice(self):
        with self.assertRaises(ValidationError):
            DiagnosisResult(
                objective={
                    "domain": "mathematics",
                    "skill": "resolver ecuaciones lineales",
                },
                evidence={
                    "type": "open_ended",
                    "result": "partial",
                    "summary": "Hay un error cuya causa aún no está clara.",
                },
                understanding={
                    "demonstrated": "Inicia el procedimiento correctamente.",
                    "missing": "No puede determinarse aún la causa del error.",
                },
                gap={
                    "present": True,
                    "type": "uncertain",
                    "description": "Se necesita más evidencia para clasificarlo.",
                },
                next_step="practice",
            )

    def test_demonstrated_is_required_when_evidence_is_sufficient(self):
        with self.assertRaises(ValidationError):
            DiagnosisResult(
                objective={
                    "domain": "mathematics",
                    "skill": "sumar enteros",
                },
                evidence={
                    "type": "closed_ended",
                    "result": "meets",
                    "summary": "La respuesta es correcta.",
                },
                understanding={
                    "demonstrated": None,
                    "missing": None,
                },
                gap={
                    "present": False,
                    "type": "none",
                    "description": None,
                },
                next_step="practice",
            )

    def test_rubric_global_result_must_match_criteria(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "language",
                    "skill": "argumentación escrita",
                },
                evidence={
                    "type": "rubric",
                    "result": "meets",
                    "summary": (
                        "La respuesta presenta fortalezas "
                        "y una debilidad."
                    ),
                    "criteria": [
                        {
                            "name": "Tesis",
                            "result": "meets",
                        },
                        {
                            "name": "Evidencia",
                            "result": "does_not_meet",
                        },
                    ],
                },
                understanding={
                    "demonstrated": (
                        "Presenta una tesis clara."
                    ),
                    "missing": (
                        "No sustenta la tesis "
                        "con evidencia."
                    ),
                },
                gap={
                    "present": True,
                    "type": "missing_prerequisite",
                    "description": (
                        "Falta fundamentar "
                        "las afirmaciones."
                    ),
                },
                next_step="teach",
            )

    def test_criteria_outside_rubric_is_rejected(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "science",
                    "skill": "explicar evaporación",
                },
                evidence={
                    "type": "open_ended",
                    "result": "partial",
                    "summary": (
                        "La explicación es incompleta."
                    ),
                    "criteria": [
                        {
                            "name": "Concepto",
                            "result": "partial",
                        }
                    ],
                },
                understanding={
                    "demonstrated": (
                        "Reconoce un cambio de estado."
                    ),
                    "missing": (
                        "No relaciona correctamente "
                        "temperatura y evaporación."
                    ),
                },
                gap={
                    "present": True,
                    "type": "missing_prerequisite",
                    "description": (
                        "Falta comprender el efecto "
                        "de la energía térmica."
                    ),
                },
                next_step="teach",
            )

    def test_invalid_mastery_next_step_is_rejected(self):
        with self.assertRaises(
            ValidationError
        ):
            DiagnosisResult(
                objective={
                    "domain": "history",
                    "skill": "explicar una causa histórica",
                },
                evidence={
                    "type": "open_ended",
                    "result": "meets",
                    "summary": (
                        "La explicación cumple "
                        "el objetivo observado."
                    ),
                },
                understanding={
                    "demonstrated": (
                        "Relaciona correctamente "
                        "causa y consecuencia."
                    ),
                    "missing": None,
                },
                gap={
                    "present": False,
                    "type": "none",
                    "description": None,
                },
                next_step="MASTERED",
            )


if __name__ == "__main__":
    unittest.main()
