import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.episodes import ensure_learning_episode, update_episode_projection
from s2.storage import connect, ensure_database
from s2.tools import get_learning_state, record_learning_event
from s3.intake import classify_learning_intake, resolve_objective
from s3.session import run_student_turn


def usage(total=100):
    return SimpleNamespace(prompt_tokens=70, completion_tokens=30, total_tokens=total)


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(*, tool_calls=None, content=None, total=100):
    return SimpleNamespace(
        model="grok-4.6",
        usage=usage(total),
        choices=[SimpleNamespace(
            finish_reason="tool_calls" if tool_calls else "stop",
            message=SimpleNamespace(content=content, tool_calls=tool_calls),
        )],
    )


class TestObjectiveSwitchGuardrails(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "switch.db"
        ensure_database(self.db)
        self.student = "student_switch"
        self.photo_obj = "obj-photosynthesis"
        self.photo_episode, self.photo_pending = self._seed_photosynthesis_pending()

    def tearDown(self):
        self.tempdir.cleanup()

    def _seed_photosynthesis_pending(self):
        episode = ensure_learning_episode(
            student_id=self.student,
            objective_id=self.photo_obj,
            objective="Comprender cómo funciona la fotosíntesis",
            objective_source="inferred",
            turn_type="learning_request",
            db_path=self.db,
        )
        update_episode_projection(
            episode_id=episode["episode_id"],
            status="awaiting_evidence",
            db_path=self.db,
        )
        event = record_learning_event(
            student_id=self.student,
            objective="Comprender cómo funciona la fotosíntesis",
            objective_source="inferred",
            activity="activity-photo",
            gap="none",
            strategy_type="concept_explanation",
            strategy_result="inconclusive",
            diagnostic_outcome="inconclusive",
            evidence="Explicación de fotosíntesis pendiente de evidencia.",
            event_type="strategy_applied",
            objective_id=self.photo_obj,
            episode_id=episode["episode_id"],
            db_path=self.db,
        )
        self.assertTrue(event["ok"])
        return episode, event

    def _seed_failed_photo_strategy(self):
        applied = record_learning_event(
            student_id=self.student,
            objective="Comprender cómo funciona la fotosíntesis",
            objective_source="inferred",
            activity="activity-photo-failed",
            gap="misconception",
            strategy_type="analogy",
            strategy_result="inconclusive",
            diagnostic_outcome="incorrect",
            evidence="Analogía aplicada.",
            event_type="strategy_applied",
            objective_id=self.photo_obj,
            episode_id=self.photo_episode["episode_id"],
            db_path=self.db,
        )
        evaluated = record_learning_event(
            student_id=self.student,
            objective="Comprender cómo funciona la fotosíntesis",
            objective_source="inferred",
            activity="activity-photo-failed",
            gap="misconception",
            strategy_type="analogy",
            strategy_result="failed",
            diagnostic_outcome="incorrect",
            evidence="La dificultad persistió.",
            event_type="strategy_evaluated",
            objective_id=self.photo_obj,
            evaluates_event_id=applied["event_id"],
            result_reason="same_error_persists",
            episode_id=self.photo_episode["episode_id"],
            db_path=self.db,
        )
        self.assertTrue(evaluated["ok"])

    def _math_client(self, *, force_missing_record_first=False):
        seq = [
            response(tool_calls=[tool_call("c1", "get_learning_state", {"student_id": self.student})]),
            response(tool_calls=[tool_call("c2", "list_teaching_strategies", {"gap": "none", "exclude_types": []})]),
        ]
        if force_missing_record_first:
            seq.append(response(content="Cambiamos a ecuaciones. Divide y luego despeja x."))
        seq.extend([
            response(tool_calls=[tool_call("c3", "record_learning_event", {
                "strategy_type": "worked_example",
                "evidence": "Se mostró un ejemplo resuelto de ecuación lineal.",
            })]),
            response(content="Cambiamos a ecuaciones. Prueba ahora 3(x+4)=21."),
        ])
        client = Mock()
        client.chat.completions.create.side_effect = seq
        return client

    def _resolve_math(self):
        state = get_learning_state(self.student, db_path=self.db)
        message = "Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10."
        intake = classify_learning_intake(message=message, state=state)
        return resolve_objective(
            student_id=self.student,
            message=message,
            intake=intake,
            state=state,
            db_path=self.db,
        )

    def test_photosynthesis_to_equations_switches_objective(self):
        resolved = self._resolve_math()
        self.assertEqual(resolved.action, "switch_objective")
        self.assertNotEqual(resolved.objective_id, self.photo_obj)
        self.assertIn("ecuaciones", resolved.objective.lower())

    def test_zero_similarity_never_continues_existing(self):
        resolved = self._resolve_math()
        self.assertEqual(resolved.similarity, 0.0)
        self.assertNotEqual(resolved.action, "continue_existing")

    def test_switch_suspends_previous_episode(self):
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        with closing(connect(self.db)) as connection:
            old = connection.execute(
                "SELECT status FROM learning_episodes WHERE episode_id=?",
                (self.photo_episode["episode_id"],),
            ).fetchone()
        self.assertEqual(old["status"], "suspended")
        self.assertEqual(result.objective_resolution.action, "switch_objective")

    def test_switch_interrupts_old_pending_with_topic_reason(self):
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        cycle = result.agent_meta.cycle_evaluation
        self.assertEqual(cycle.status, "interrupted")
        self.assertEqual(cycle.reason, "topic_switched_before_attempt")
        self.assertEqual(cycle.pending_event_id, self.photo_pending["event_id"])
        with closing(connect(self.db)) as connection:
            row = connection.execute(
                "SELECT event_type, result_reason FROM learning_events WHERE event_id=?",
                (cycle.evaluation_event_id,),
            ).fetchone()
        self.assertEqual(row["event_type"], "strategy_interrupted")
        self.assertEqual(row["result_reason"], "topic_switched_before_attempt")

    def test_math_gets_different_objective_and_episode_ids(self):
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        self.assertNotEqual(result.objective_resolution.objective_id, self.photo_obj)
        self.assertNotEqual(result.agent_meta.episode_id, self.photo_episode["episode_id"])

    def test_applied_math_strategy_is_persisted_under_math_objective(self):
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        record_trace = next(t for t in result.agent_meta.tools if t.name == "record_learning_event")
        self.assertEqual(record_trace.arguments["objective_id"], result.objective_resolution.objective_id)
        with closing(connect(self.db)) as connection:
            row = connection.execute(
                "SELECT objective_id, episode_id FROM learning_events WHERE event_id=?",
                (record_trace.result["event_id"],),
            ).fetchone()
        self.assertEqual(row["objective_id"], result.objective_resolution.objective_id)
        self.assertEqual(row["episode_id"], result.agent_meta.episode_id)

    def test_failed_history_from_photosynthesis_does_not_exclude_math_strategy(self):
        self._seed_failed_photo_strategy()
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        list_trace = next(t for t in result.agent_meta.tools if t.name == "list_teaching_strategies")
        self.assertEqual(list_trace.arguments["exclude_types"], [])

    def test_metrics_use_new_math_objective_id(self):
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        self.assertEqual(result.metrics["objective_id"], result.objective_resolution.objective_id)
        self.assertNotEqual(result.metrics["objective_id"], self.photo_obj)

    def test_agent_cannot_finalize_teaching_without_recording_current_intervention(self):
        client = self._math_client(force_missing_record_first=True)
        result = run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=client,
            db_path=self.db,
        )
        self.assertGreaterEqual(client.chat.completions.create.call_count, 5)
        records = [t for t in result.agent_meta.tools if t.name == "record_learning_event" and t.result.get("ok")]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].arguments["objective_id"], result.objective_resolution.objective_id)

    def test_return_to_photosynthesis_resumes_suspended_episode_without_duplicate(self):
        run_student_turn(
            student_id=self.student,
            message="Ahora quiero aprender cómo resolver ecuaciones como 2(x + 3) = 10.",
            client=self._math_client(),
            db_path=self.db,
        )
        state = get_learning_state(self.student, db_path=self.db)
        message = "Quiero volver a aprender cómo funciona la fotosíntesis."
        intake = classify_learning_intake(message=message, state=state)
        resolved = resolve_objective(
            student_id=self.student,
            message=message,
            intake=intake,
            state=state,
            db_path=self.db,
        )
        self.assertEqual(resolved.objective_id, self.photo_obj)
        self.assertEqual(resolved.action, "resume_suspended")
        self.assertEqual(resolved.matched_episode_id, self.photo_episode["episode_id"])
        with closing(connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM learning_episodes WHERE student_id=? AND objective_id=?",
                (self.student, self.photo_obj),
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
