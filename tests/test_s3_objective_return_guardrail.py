import unittest
from unittest.mock import patch

from s3.intake import LearningIntake, resolve_objective


class ObjectiveReturnGuardrailTests(unittest.TestCase):
    def _intake(self):
        return LearningIntake(
            turn_type="metacognitive",
            interaction_need="reassessment",
            should_diagnose=False,
            diagnosis_target=None,
            has_activity_context=False,
        )

    def _state(self):
        return {
            "current_objective_id": "obj-triangle",
            "current_objective": "Comprender: cómo calcular el área de un triángulo",
            "active_episode": {
                "episode_id": "ep-triangle",
                "objective_id": "obj-triangle",
                "objective": "Comprender: cómo calcular el área de un triángulo",
                "objective_source": "inferred",
                "status": "awaiting_evidence",
            },
            "pending_intervention": {
                "event_id": "event-triangle",
                "episode_id": "ep-triangle",
                "objective_id": "obj-triangle",
                "objective": "Comprender: cómo calcular el área de un triángulo",
                "objective_source": "inferred",
                "strategy_type": "worked_example",
            },
        }

    def _episodes(self):
        return [
            {
                "episode_id": "ep-triangle",
                "objective_id": "obj-triangle",
                "objective": "Comprender: cómo calcular el área de un triángulo",
                "objective_source": "inferred",
                "status": "awaiting_evidence",
            },
            {
                "episode_id": "ep-photo",
                "objective_id": "obj-photo",
                "objective": "Comprender: por qué las plantas necesitan luz para hacer la fotosíntesis",
                "objective_source": "inferred",
                "status": "suspended",
            },
        ]

    @patch("s3.intake.list_recent_episodes")
    def test_explicit_return_resumes_suspended_named_topic(self, mocked):
        mocked.return_value = self._episodes()
        resolved = resolve_objective(
            student_id="student_cost_002",
            message="Volvamos a lo de fotosíntesis. No recuerdo bien por qué la planta necesita luz.",
            intake=self._intake(),
            state=self._state(),
        )
        self.assertEqual(resolved.objective_id, "obj-photo")
        self.assertEqual(resolved.action, "resume_suspended")
        self.assertEqual(resolved.matched_episode_id, "ep-photo")
        self.assertGreaterEqual(resolved.similarity, 0.10)

    @patch("s3.intake.list_recent_episodes")
    def test_plain_no_recuerdo_can_still_continue_current_topic(self, mocked):
        mocked.return_value = self._episodes()
        resolved = resolve_objective(
            student_id="student_cost_002",
            message="No recuerdo bien, ¿me lo explicas otra vez?",
            intake=self._intake(),
            state=self._state(),
        )
        self.assertEqual(resolved.objective_id, "obj-triangle")
        self.assertEqual(resolved.action, "continue_existing")

    @patch("s3.intake.list_recent_episodes")
    def test_unknown_explicit_return_never_sticks_to_current_on_zero_similarity(self, mocked):
        mocked.return_value = self._episodes()
        resolved = resolve_objective(
            student_id="student_cost_002",
            message="Volvamos a geología volcánica; no recuerdo ese tema.",
            intake=self._intake(),
            state=self._state(),
        )
        self.assertNotEqual(resolved.action, "continue_existing")
        self.assertNotEqual(resolved.objective_id, "obj-triangle")


if __name__ == "__main__":
    unittest.main()
