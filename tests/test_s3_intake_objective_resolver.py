import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.episodes import ensure_learning_episode, update_episode_projection
from s2.storage import connect, ensure_database
from s2.tools import get_learning_state, list_teaching_strategies, record_learning_event
from s3.intake import classify_learning_intake, resolve_objective
from s3.metrics import build_task_metrics
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


class TestS3IntakeObjectiveResolver(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "intake.db"
        ensure_database(self.db)
        self.student = "student_intake"

    def tearDown(self):
        self.tempdir.cleanup()

    def _seed_pending(self, *, objective_id="obj-water", strategy="independent_practice"):
        episode = ensure_learning_episode(
            student_id=self.student,
            objective_id=objective_id,
            objective="Comprender la condensación en el ciclo del agua",
            objective_source="inferred",
            turn_type="attempt",
            db_path=self.db,
        )
        event = record_learning_event(
            student_id=self.student,
            objective="Comprender la condensación en el ciclo del agua",
            objective_source="inferred",
            activity="activity-water",
            gap="none",
            strategy_type=strategy,
            strategy_result="inconclusive",
            diagnostic_outcome="correct",
            evidence="Práctica pendiente.",
            event_type="strategy_applied",
            objective_id=objective_id,
            episode_id=episode["episode_id"],
            db_path=self.db,
        )
        return episode, event

    def test_free_learning_request_does_not_require_diagnosis(self):
        intake = classify_learning_intake(
            message="Quiero aprender fotosíntesis",
            activity=None,
            state={},
        )
        self.assertEqual(intake.turn_type, "learning_request")
        self.assertFalse(intake.should_diagnose)
        self.assertEqual(intake.interaction_need, "explanation")

    def test_plain_free_question_does_not_require_diagnosis(self):
        intake = classify_learning_intake(
            message="¿Por qué el cielo es azul?",
            activity=None,
            state={},
        )
        self.assertEqual(intake.turn_type, "question")
        self.assertFalse(intake.should_diagnose)

    def test_attempt_with_pending_uses_objective_as_diagnosis_target(self):
        self._seed_pending()
        state = get_learning_state(self.student, db_path=self.db)
        intake = classify_learning_intake(
            message="El vapor se enfría y forma gotitas.",
            activity=None,
            state=state,
        )
        self.assertTrue(intake.should_diagnose)
        self.assertIn("condensación", intake.diagnosis_target.lower())

    def test_objective_is_created_internally_for_free_question(self):
        intake = classify_learning_intake(message="¿Por qué el cielo es azul?", state={})
        resolved = resolve_objective(
            student_id=self.student,
            message="¿Por qué el cielo es azul?",
            intake=intake,
            state={},
            db_path=self.db,
        )
        self.assertTrue(resolved.objective_id.startswith("inferred-"))
        self.assertEqual(resolved.action, "create_inferred")
        self.assertEqual(resolved.objective_source, "inferred")

    def test_followup_help_continues_pending_objective(self):
        _, event = self._seed_pending()
        state = get_learning_state(self.student, db_path=self.db)
        intake = classify_learning_intake(
            message="¿Me lo explicas otra vez? No recuerdo esa parte.",
            state=state,
        )
        resolved = resolve_objective(
            student_id=self.student,
            message="¿Me lo explicas otra vez? No recuerdo esa parte.",
            intake=intake,
            state=state,
            db_path=self.db,
        )
        self.assertEqual(resolved.objective_id, "obj-water")
        self.assertEqual(resolved.action, "continue_existing")

    def test_new_subject_switches_objective_without_user_id(self):
        self._seed_pending()
        state = get_learning_state(self.student, db_path=self.db)
        intake = classify_learning_intake(
            message="¿Cómo despejo x en una ecuación lineal?",
            state=state,
        )
        resolved = resolve_objective(
            student_id=self.student,
            message="¿Cómo despejo x en una ecuación lineal?",
            intake=intake,
            state=state,
            db_path=self.db,
        )
        self.assertNotEqual(resolved.objective_id, "obj-water")
        self.assertEqual(resolved.action, "switch_objective")

    def test_return_to_confirmed_previous_objective_is_reopened(self):
        water = ensure_learning_episode(
            student_id=self.student,
            objective_id="obj-water",
            objective="Comprender condensación y formación de nubes",
            objective_source="inferred",
            turn_type="attempt",
            db_path=self.db,
        )
        update_episode_projection(
            episode_id=water["episode_id"],
            status="evidence_confirmed",
            db_path=self.db,
        )
        ensure_learning_episode(
            student_id=self.student,
            objective_id="obj-math",
            objective="Resolver ecuaciones lineales",
            objective_source="inferred",
            turn_type="attempt",
            db_path=self.db,
        )
        state = get_learning_state(self.student, db_path=self.db)
        intake = classify_learning_intake(
            message="¿Qué era la condensación?",
            state=state,
        )
        resolved = resolve_objective(
            student_id=self.student,
            message="¿Qué era la condensación?",
            intake=intake,
            state=state,
            db_path=self.db,
        )
        self.assertEqual(resolved.objective_id, "obj-water")
        self.assertEqual(resolved.action, "reopen_closed")

    def test_explanation_need_can_use_catalog_even_without_gap(self):
        result = list_teaching_strategies(
            "none",
            interaction_need="explanation",
            db_path=self.db,
        )
        eligible = {item["type"] for item in result["eligible"]}
        self.assertIn("concept_explanation", eligible)
        self.assertIn("analogy", eligible)
        self.assertNotIn("independent_practice", eligible)

    def test_interruption_is_terminal_but_not_evaluation(self):
        episode, applied = self._seed_pending()
        interrupted = record_learning_event(
            student_id=self.student,
            objective="Comprender la condensación en el ciclo del agua",
            objective_source="inferred",
            activity="activity-water",
            gap="none",
            strategy_type="independent_practice",
            strategy_result="inconclusive",
            diagnostic_outcome="inconclusive",
            evidence="Pidió ayuda antes de intentar.",
            event_type="strategy_interrupted",
            objective_id="obj-water",
            evaluates_event_id=applied["event_id"],
            result_reason="help_requested_before_attempt",
            episode_id=episode["episode_id"],
            db_path=self.db,
        )
        self.assertTrue(interrupted["ok"])
        later_eval = record_learning_event(
            student_id=self.student,
            objective="Comprender la condensación en el ciclo del agua",
            objective_source="inferred",
            activity="activity-water",
            gap="none",
            strategy_type="independent_practice",
            strategy_result="helped",
            diagnostic_outcome="correct",
            evidence="Intento posterior.",
            event_type="strategy_evaluated",
            objective_id="obj-water",
            evaluates_event_id=applied["event_id"],
            result_reason="objective_met",
            episode_id=episode["episode_id"],
            db_path=self.db,
        )
        self.assertFalse(later_eval["ok"])
        state = get_learning_state(self.student, db_path=self.db)
        self.assertIsNone(state["pending_intervention"])
        self.assertEqual(state["strategies_tried"][0]["terminal_event_type"], "strategy_interrupted")

    def test_real_support_flow_skips_diagnosis_interrupts_and_records_new_strategy(self):
        self._seed_pending()
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(tool_calls=[tool_call("c1", "get_learning_state", {"student_id": self.student})]),
            response(tool_calls=[tool_call("c2", "list_teaching_strategies", {"gap": "none", "exclude_types": []})]),
            response(tool_calls=[tool_call("c3", "record_learning_event", {
                "strategy_type": "concept_explanation",
                "evidence": "Se explicó condensación de forma breve.",
            })]),
            response(content="Condensación es el paso de vapor a gotitas. ¿Qué ocurre cuando el vapor se enfría?"),
        ]
        result = run_student_turn(
            student_id=self.student,
            message="¿Me puedes explicar otra vez qué significa condensación?",
            client=client,
            db_path=self.db,
            task_id="task-support-1",
            started_at="2026-10-25T01:00:00+00:00",
        )
        self.assertIsNone(result.diagnosis_meta)
        self.assertTrue(result.metrics["diagnosis_skipped"])
        self.assertEqual(result.agent_meta.cycle_evaluation.status, "interrupted")
        self.assertEqual(result.agent_meta.cycle_evaluation.reason, "help_requested_before_attempt")
        self.assertEqual(result.agent_meta.interaction_need, "explanation")
        state = get_learning_state(self.student, db_path=self.db)
        self.assertEqual(state["pending_intervention"]["strategy_type"], "concept_explanation")
        self.assertEqual(result.metrics["started_at"], "2026-10-25T01:00:00+00:00")
        self.assertEqual(result.metrics["diagnosis_tokens"], 0)
        self.assertEqual(result.metrics["llm_calls"], 4)

    def test_metrics_keep_reported_and_visible_token_totals_separate(self):
        agent_meta = SimpleNamespace(
            calls=(SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=180),),
            tools=(),
            total_tokens=180,
            total_latency_ms=100,
        )
        metrics = build_task_metrics(
            task_id="metrics-separate",
            diagnosis_meta=None,
            agent_meta=agent_meta,
            diagnosis_skipped=True,
            started_at="2026-10-25T00:00:00+00:00",
        )
        self.assertEqual(metrics["agent_tokens"], 180)
        self.assertEqual(metrics["agent_visible_tokens"], 120)
        self.assertEqual(metrics["visible_token_sum"], 120)
        self.assertEqual(metrics["total_tokens"], 180)
        self.assertTrue(metrics["diagnosis_skipped"])

    def test_demo_does_not_ask_student_for_objective_id(self):
        demo = Path(__file__).resolve().parent.parent / "s3_demo.py"
        text = demo.read_text(encoding="utf-8")
        self.assertNotIn("ID estable del objetivo", text)
        self.assertIn("Mensaje del estudiante", text)


if __name__ == "__main__":
    unittest.main()
