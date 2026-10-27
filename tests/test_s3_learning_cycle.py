from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from s2.storage import connect, ensure_database
from s2.tools import get_learning_state, record_learning_event


class TestLearningCycleFoundation(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "cycle.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def apply(
        self,
        *,
        student="student_cycle",
        objective_id="obj-fracciones-001",
        objective="Sumar fracciones con distinto denominador",
        strategy="contrast_example",
        outcome="incorrect",
        gap="misconception",
    ):
        return record_learning_event(
            student_id=student,
            objective=objective,
            objective_source="inferred",
            activity="fraction-turn-1",
            gap=gap,
            strategy_type=strategy,
            strategy_result="inconclusive",
            diagnostic_outcome=outcome,
            evidence="El alumno suma numeradores y denominadores directamente.",
            event_type="strategy_applied",
            objective_id=objective_id,
            db_path=self.db,
        )

    def evaluate(
        self,
        applied_event_id,
        *,
        result,
        reason,
        objective_id="obj-fracciones-001",
        objective="Sumar fracciones con distinto denominador",
        student="student_cycle",
        strategy="contrast_example",
        outcome="partial",
        gap="misconception",
    ):
        return record_learning_event(
            student_id=student,
            objective=objective,
            objective_source="inferred",
            activity="fraction-turn-2",
            gap=gap,
            strategy_type=strategy,
            strategy_result=result,
            diagnostic_outcome=outcome,
            evidence="Nueva evidencia posterior a la intervención.",
            event_type="strategy_evaluated",
            objective_id=objective_id,
            evaluates_event_id=applied_event_id,
            result_reason=reason,
            db_path=self.db,
        )

    def test_strategy_applied_rejects_helped_or_failed(self):
        result = record_learning_event(
            student_id="student_cycle",
            objective="Objetivo",
            objective_source="inferred",
            activity="a1",
            gap="misconception",
            strategy_type="contrast_example",
            strategy_result="helped",
            diagnostic_outcome="partial",
            evidence="evidencia",
            event_type="strategy_applied",
            objective_id="obj-1",
            db_path=self.db,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "validation_error")

    def test_evaluation_is_append_only_and_does_not_mutate_applied(self):
        applied = self.apply()
        evaluated = self.evaluate(
            applied["event_id"],
            result="helped",
            reason="partial_improvement",
        )

        self.assertTrue(evaluated["ok"])

        with closing(connect(self.db)) as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, strategy_result, evaluates_event_id
                FROM learning_events
                ORDER BY recorded_at
                """
            ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["event_type"], "strategy_applied")
        self.assertEqual(rows[0]["strategy_result"], "inconclusive")
        self.assertEqual(rows[1]["event_type"], "strategy_evaluated")
        self.assertEqual(rows[1]["evaluates_event_id"], rows[0]["event_id"])

    def test_objective_changed_can_close_as_inconclusive_without_calling_it_failed(self):
        applied = self.apply()
        evaluated = self.evaluate(
            applied["event_id"],
            result="inconclusive",
            reason="objective_changed",
            objective_id="obj-fracciones-001",
            gap="none",
            outcome="inconclusive",
        )
        self.assertTrue(evaluated["ok"])

        state = get_learning_state("student_cycle", db_path=self.db)
        self.assertIsNone(state["pending_intervention"])
        self.assertEqual(state["strategies_tried"][0]["result"], "inconclusive")
        self.assertEqual(
            state["strategies_tried"][0]["result_reason"],
            "objective_changed",
        )

    def test_failed_projection_is_scoped_to_objective(self):
        applied = self.apply()
        self.evaluate(
            applied["event_id"],
            result="failed",
            reason="same_error_persists",
        )

        other = record_learning_event(
            student_id="student_cycle",
            objective="Comprender la fotosíntesis",
            objective_source="inferred",
            activity="science-1",
            gap="factual_error",
            strategy_type="hint",
            strategy_result="inconclusive",
            diagnostic_outcome="partial",
            evidence="Evidencia de otro objetivo.",
            event_type="strategy_applied",
            objective_id="obj-science-001",
            db_path=self.db,
        )
        self.assertTrue(other["ok"])

        state = get_learning_state("student_cycle", db_path=self.db)
        failed = [
            item for item in state["strategies_tried"]
            if item["result"] == "failed"
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["objective_id"], "obj-fracciones-001")

    def test_helped_does_not_create_mastery_state(self):
        applied = self.apply()
        self.evaluate(
            applied["event_id"],
            result="helped",
            reason="partial_improvement",
        )

        state = get_learning_state("student_cycle", db_path=self.db)
        self.assertEqual(state["strategies_tried"][0]["result"], "helped")
        self.assertNotIn("mastery", state)
        self.assertNotIn("mastered", str(state).lower())

    def test_same_applied_event_cannot_be_evaluated_twice(self):
        applied = self.apply()
        first = self.evaluate(
            applied["event_id"],
            result="helped",
            reason="partial_improvement",
        )
        second = self.evaluate(
            applied["event_id"],
            result="failed",
            reason="same_error_persists",
        )
        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["error_code"], "validation_error")

    def test_get_learning_state_exposes_pending_intervention(self):
        applied = self.apply()
        state = get_learning_state("student_cycle", db_path=self.db)

        self.assertEqual(
            state["pending_intervention"]["applied_event_id"],
            applied["event_id"],
        )
        self.assertEqual(
            state["pending_intervention"]["objective_id"],
            "obj-fracciones-001",
        )

    def test_audit_reconstructs_applied_and_evaluated_events(self):
        applied = self.apply()
        evaluated = self.evaluate(
            applied["event_id"],
            result="failed",
            reason="same_error_persists",
        )

        with closing(connect(self.db)) as connection:
            applied_row = connection.execute(
                "SELECT * FROM learning_events WHERE event_id = ?",
                (applied["event_id"],),
            ).fetchone()
            evaluated_row = connection.execute(
                "SELECT * FROM learning_events WHERE event_id = ?",
                (evaluated["event_id"],),
            ).fetchone()

        self.assertEqual(applied_row["strategy_result"], "inconclusive")
        self.assertEqual(evaluated_row["strategy_result"], "failed")
        self.assertEqual(
            evaluated_row["evaluates_event_id"],
            applied_row["event_id"],
        )


if __name__ == "__main__":
    unittest.main()
