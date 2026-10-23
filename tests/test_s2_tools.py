from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from s2.storage import connect, ensure_database
from s2.tools import (
    execute_tool_call,
    get_learning_state,
    list_teaching_strategies,
    record_learning_event,
)


class TestS2Tools(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "nexa-test.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def _record(
        self,
        *,
        student_id="student_demo",
        source="inferred",
        gap="misconception",
        strategy="analogy",
        result="helped",
        outcome="partial",
        evidence="El estudiante identifica parte del proceso.",
        objective="Comprender el ciclo del agua",
    ):
        return record_learning_event(
            student_id=student_id,
            objective=objective,
            objective_source=source,
            activity="water_cycle_q1",
            gap=gap,
            strategy_type=strategy,
            strategy_result=result,
            diagnostic_outcome=outcome,
            evidence=evidence,
            db_path=self.db,
        )

    def test_database_seeds_nine_strategies(self):
        with closing(connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM teaching_strategies"
            ).fetchone()[0]
        self.assertEqual(count, 9)

    def test_empty_learning_state_is_explicit_and_does_not_create_student(self):
        state = get_learning_state("student_new", db_path=self.db)

        self.assertFalse(state["has_history"])
        self.assertEqual(state["attempts_count"], 0)
        self.assertEqual(state["previous_gaps"], [])
        self.assertEqual(state["strategies_tried"], [])
        self.assertFalse(state["can_cite_as_teacher_objective"])

        with closing(connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM students WHERE student_id = ?",
                ("student_new",),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_record_event_writes_real_event_and_returns_id(self):
        result = self._record()

        self.assertTrue(result["ok"])
        self.assertTrue(result["event_id"])
        self.assertIn("+00:00", result["recorded_at"])

        with closing(connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM learning_events"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_learning_state_reads_recorded_history(self):
        self._record()
        state = get_learning_state("student_demo", db_path=self.db)

        self.assertTrue(state["has_history"])
        self.assertEqual(state["attempts_count"], 1)
        self.assertEqual(state["current_objective"], "Comprender el ciclo del agua")
        self.assertEqual(state["objective_source"], "inferred")
        self.assertFalse(state["can_cite_as_teacher_objective"])
        self.assertEqual(state["previous_gaps"], ["misconception"])
        self.assertEqual(state["strategies_tried"][0]["type"], "analogy")

    def test_teacher_objective_is_citable_only_when_source_teacher(self):
        self._record(source="teacher")
        state = get_learning_state("student_demo", db_path=self.db)
        self.assertTrue(state["can_cite_as_teacher_objective"])

    def test_failed_strategy_can_be_excluded_from_catalog(self):
        result = list_teaching_strategies(
            "misconception",
            exclude_types=["analogy"],
            db_path=self.db,
        )

        eligible_types = {item["type"] for item in result["eligible"]}
        self.assertNotIn("analogy", eligible_types)
        self.assertIn(
            {"type": "analogy", "reason": "previously_failed"},
            result["excluded"],
        )

    def test_catalog_returns_multiple_options_not_one_decision(self):
        result = list_teaching_strategies(
            "misconception",
            db_path=self.db,
        )
        self.assertGreaterEqual(len(result["eligible"]), 2)

    def test_unknown_gap_does_not_invent_strategy(self):
        result = list_teaching_strategies(
            "unmapped_gap",
            db_path=self.db,
        )
        self.assertEqual(result["eligible"], [])
        self.assertTrue(result["catalog_incomplete"])

    def test_record_rejects_unknown_strategy_without_writing_event(self):
        result = record_learning_event(
            student_id="student_demo",
            objective="Objetivo",
            objective_source="inferred",
            activity="a1",
            gap="misconception",
            strategy_type="invented_strategy",
            strategy_result="helped",
            diagnostic_outcome="partial",
            evidence="evidencia",
            db_path=self.db,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "validation_error")

        state = get_learning_state("student_demo", db_path=self.db)
        self.assertFalse(state["has_history"])

    def test_dispatcher_rejects_mastered_as_extra_field(self):
        result = execute_tool_call(
            "record_learning_event",
            {
                "student_id": "student_demo",
                "objective": "Objetivo",
                "objective_source": "inferred",
                "activity": "a1",
                "gap": "misconception",
                "strategy_type": "analogy",
                "strategy_result": "helped",
                "diagnostic_outcome": "correct",
                "evidence": "evidencia",
                "mastered": True,
            },
            db_path=self.db,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "validation_error")

    def test_evidence_is_deterministically_capped_at_500_chars(self):
        result = self._record(evidence="x" * 900)
        self.assertTrue(result["ok"])

        with closing(connect(self.db)) as connection:
            stored = connection.execute(
                "SELECT evidence FROM learning_events WHERE event_id = ?",
                (result["event_id"],),
            ).fetchone()[0]
        self.assertEqual(len(stored), 500)

    def test_recent_state_deduplicates_gaps_and_strategies(self):
        self._record(gap="misconception", strategy="analogy", result="failed")
        self._record(gap="misconception", strategy="analogy", result="helped")
        self._record(
            gap="incomplete_procedure",
            strategy="guided_practice",
            result="helped",
        )

        state = get_learning_state("student_demo", db_path=self.db)

        self.assertEqual(state["attempts_count"], 3)
        self.assertEqual(
            set(state["previous_gaps"]),
            {"misconception", "incomplete_procedure"},
        )
        self.assertEqual(len(state["strategies_tried"]), 2)

    def test_validation_error_for_invalid_student_id(self):
        result = get_learning_state("student id with spaces", db_path=self.db)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "validation_error")

    def test_storage_error_is_explicit(self):
        bad_db_path = Path(self.tempdir.name)  # directory, not database file
        result = get_learning_state("student_demo", db_path=bad_db_path)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "storage_error")

    def test_invalid_tool_arguments_do_not_raise_stack_trace(self):
        result = execute_tool_call(
            "get_learning_state",
            "{not-json}",
            db_path=self.db,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
