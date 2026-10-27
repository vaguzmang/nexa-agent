import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.agent import run_learning_agent
from s2.episodes import ensure_learning_episode, record_learning_observation
from s2.observation import observe_turn
from s2.storage import connect, ensure_database
from s2.tools import get_learning_state, record_learning_event


def diagnosis(
    *,
    skill="Explicar el ciclo del agua",
    domain="Ciencias",
    result="partial",
    gap="incomplete_procedure",
    next_step="teach",
    evidence_type="open_ended",
    criteria=None,
):
    return {
        "schema_version": "diag.v1.1",
        "objective": {"domain": domain, "skill": skill},
        "evidence": {
            "type": evidence_type,
            "result": result,
            "summary": "Resumen diagnóstico actual.",
            "criteria": criteria,
        },
        "understanding": {
            "demonstrated": None if result == "insufficient_evidence" else "Parte demostrada.",
            "missing": None if result in {"meets", "insufficient_evidence"} else "Parte faltante.",
        },
        "gap": {
            "present": gap != "none",
            "type": gap,
            "description": None if gap == "none" else "Brecha observada.",
        },
        "next_step": next_step,
    }


def usage(total=100):
    return SimpleNamespace(prompt_tokens=70, completion_tokens=30, total_tokens=total)


def tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(*, content="Respuesta final", tool_calls=None):
    return SimpleNamespace(
        model="grok-4.6",
        usage=usage(),
        choices=[SimpleNamespace(
            finish_reason="tool_calls" if tool_calls else "stop",
            message=SimpleNamespace(content=content if not tool_calls else None, tool_calls=tool_calls),
        )],
    )


class TestS3VNextArchitecture(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "vnext.db"
        ensure_database(self.db)
        self.student = "student-vnext"
        self.objective_id = "water-001"

    def tearDown(self):
        self.tempdir.cleanup()

    def _seed_pending(self, *, strategy="guided_practice", gap="incomplete_procedure", outcome="partial"):
        episode = ensure_learning_episode(
            student_id=self.student,
            objective_id=self.objective_id,
            objective="Explicar el ciclo del agua",
            objective_source="inferred",
            turn_type="attempt",
            db_path=self.db,
        )
        event = record_learning_event(
            student_id=self.student,
            objective="Explicar el ciclo del agua",
            objective_source="inferred",
            activity="activity-seed",
            gap=gap,
            strategy_type=strategy,
            strategy_result="inconclusive",
            diagnostic_outcome=outcome,
            evidence="Evidencia previa.",
            event_type="strategy_applied",
            objective_id=self.objective_id,
            episode_id=episode["episode_id"],
            db_path=self.db,
        )
        return episode, event

    def _simple_client(self, text="Respuesta pedagógica"):
        client = Mock()
        client.chat.completions.create.return_value = response(content=text)
        return client

    def test_turn_gate_does_not_treat_question_as_attempt(self):
        obs = observe_turn(
            activity="Explica la condensación",
            student_answer="¿Me lo puedes explicar otra vez?",
            diagnosis=diagnosis(result="insufficient_evidence", gap="none", next_step="ask_clarifying"),
        )
        self.assertEqual(obs.turn_type, "request_explanation")
        self.assertFalse(obs.evidence_eligible)

    def test_help_request_never_marks_previous_strategy_failed(self):
        self._seed_pending(strategy="worked_example")
        client = self._simple_client("Te ayudaré con una aclaración breve.")
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Explica el ciclo del agua",
            student_answer="¿Me lo explicas otra vez?",
            diagnosis=diagnosis(result="insufficient_evidence", gap="none", next_step="ask_clarifying"),
            objective_id=self.objective_id,
            client=client,
            db_path=self.db,
        )
        self.assertEqual(meta.cycle_evaluation.status, "interrupted")
        self.assertIsNone(meta.cycle_evaluation.result)
        self.assertEqual(meta.cycle_evaluation.reason, "help_requested_before_attempt")
        self.assertNotEqual(meta.cycle_evaluation.result, "failed")
        state = get_learning_state(self.student, db_path=self.db)
        self.assertIsNone(state["pending_intervention"])
        self.assertEqual(state["strategies_tried"][0]["terminal_event_type"], "strategy_interrupted")

    def test_insufficient_attempt_preserves_pending_and_uses_no_tools(self):
        _, event = self._seed_pending()
        client = self._simple_client("Necesito una respuesta más concreta.")
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Explica el ciclo del agua",
            student_answer="No sé",
            diagnosis=diagnosis(result="insufficient_evidence", gap="none", next_step="ask_clarifying"),
            objective_id=self.objective_id,
            client=client,
            db_path=self.db,
        )
        self.assertEqual(meta.cycle_evaluation.status, "pending_preserved")
        self.assertEqual(meta.episode_action, "clarify_evidence")
        state = get_learning_state(self.student, db_path=self.db)
        self.assertEqual(state["pending_intervention"]["applied_event_id"], event["event_id"])
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("tools", kwargs)

    def test_repeated_same_activity_reuses_inferred_objective_id_despite_rephrased_skill(self):
        first_client = self._simple_client()
        _, first_meta = run_learning_agent(
            student_id=self.student,
            activity="¿Qué ocurre con el vapor antes de llover?",
            student_answer="Se enfría.",
            diagnosis=diagnosis(skill="Explicar qué ocurre con el vapor antes de llover"),
            client=first_client,
            db_path=self.db,
        )
        second_client = self._simple_client()
        _, second_meta = run_learning_agent(
            student_id=self.student,
            activity="¿Qué ocurre con el vapor antes de llover?",
            student_answer="Se condensa.",
            diagnosis=diagnosis(skill="Describir el proceso atmosférico previo a la precipitación"),
            client=second_client,
            db_path=self.db,
        )
        self.assertEqual(first_meta.cycle_evaluation.objective_id, second_meta.cycle_evaluation.objective_id)

    def test_new_domain_creates_different_inferred_objective_when_activity_changes(self):
        first_client = self._simple_client()
        _, first_meta = run_learning_agent(
            student_id=self.student,
            activity="Explica la condensación",
            student_answer="Respuesta",
            diagnosis=diagnosis(skill="Explicar la condensación", domain="Ciencias"),
            client=first_client,
            db_path=self.db,
        )
        second_client = self._simple_client()
        _, second_meta = run_learning_agent(
            student_id=self.student,
            activity="Resuelve una ecuación lineal",
            student_answer="x=2",
            diagnosis=diagnosis(skill="Resolver ecuaciones lineales", domain="Matemáticas", gap="factual_error"),
            client=second_client,
            db_path=self.db,
        )
        self.assertNotEqual(first_meta.cycle_evaluation.objective_id, second_meta.cycle_evaluation.objective_id)

    def test_independent_success_confirms_episode_without_mastery_loop(self):
        self._seed_pending(strategy="independent_practice", gap="none", outcome="correct")
        client = self._simple_client("Hay evidencia independiente suficiente para cerrar este episodio.")
        text, meta = run_learning_agent(
            student_id=self.student,
            activity="Aplica el concepto sin ayuda",
            student_answer="El vapor se enfría, se condensa y forma nubes.",
            diagnosis=diagnosis(result="meets", gap="none", next_step="practice"),
            objective_id=self.objective_id,
            client=client,
            db_path=self.db,
        )
        self.assertEqual(meta.episode_status, "evidence_confirmed")
        self.assertEqual(meta.episode_action, "close_episode")
        self.assertEqual(meta.cycle_evaluation.result, "helped")
        self.assertNotIn("tools", client.chat.completions.create.call_args.kwargs)
        self.assertNotIn("mastery", text.lower())

    def test_question_after_confirmed_episode_reopens_for_reassessment(self):
        self._seed_pending(strategy="independent_practice", gap="none", outcome="correct")
        close_client = self._simple_client("Cierre de episodio.")
        run_learning_agent(
            student_id=self.student,
            activity="Aplica el concepto sin ayuda",
            student_answer="El vapor se enfría, se condensa y forma nubes.",
            diagnosis=diagnosis(result="meets", gap="none", next_step="practice"),
            objective_id=self.objective_id,
            client=close_client,
            db_path=self.db,
        )
        question_client = self._simple_client("Antes de explicarlo, dime qué recuerdas.")
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Explica el ciclo del agua",
            student_answer="¿Qué pasaba cuando el vapor se enfriaba?",
            diagnosis=diagnosis(result="insufficient_evidence", gap="none", next_step="ask_clarifying"),
            objective_id=self.objective_id,
            client=question_client,
            db_path=self.db,
        )
        self.assertEqual(meta.episode_status, "reopened")
        self.assertEqual(meta.episode_action, "reassess_recall")
        self.assertEqual(meta.learning_delta, "no_evaluable_attempt")
        self.assertNotIn("tools", question_client.chat.completions.create.call_args.kwargs)

    def test_partial_response_after_confirmed_episode_is_partial_recall(self):
        self._seed_pending(strategy="independent_practice", gap="none", outcome="correct")
        run_learning_agent(
            student_id=self.student,
            activity="Aplica el concepto sin ayuda",
            student_answer="El vapor se enfría, se condensa y forma nubes.",
            diagnosis=diagnosis(result="meets", gap="none", next_step="practice"),
            objective_id=self.objective_id,
            client=self._simple_client("Cierre."),
            db_path=self.db,
        )
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Explica el ciclo del agua de nuevo",
            student_answer="Se enfría y luego pasa algo con las nubes.",
            diagnosis=diagnosis(result="partial", gap="incomplete_procedure"),
            objective_id=self.objective_id,
            client=self._simple_client(),
            db_path=self.db,
        )
        self.assertEqual(meta.learning_delta, "partial_recall")

    def test_transfer_context_failure_is_transfer_gap_not_forgetting(self):
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Aplica el concepto en un caso distinto",
            student_answer="No logro aplicarlo aquí.",
            diagnosis=diagnosis(result="does_not_meet", gap="misconception"),
            objective_id=self.objective_id,
            difficulty_relation="transfer_context",
            client=self._simple_client(),
            db_path=self.db,
        )
        self.assertEqual(meta.learning_delta, "transfer_gap")

    def test_rubric_components_are_projected_into_learning_state(self):
        criteria = [
            {"name": "Concepto", "result": "meets"},
            {"name": "Ejemplo", "result": "partial"},
        ]
        run_learning_agent(
            student_id=self.student,
            activity="Explica y ejemplifica",
            student_answer="Explicación con ejemplo parcial.",
            diagnosis=diagnosis(result="partial", gap="misconception", evidence_type="rubric", criteria=criteria),
            objective_id=self.objective_id,
            client=self._simple_client(),
            db_path=self.db,
        )
        state = get_learning_state(self.student, db_path=self.db)
        self.assertEqual(state["component_progress"], criteria)

    def test_record_tool_is_enriched_with_episode_and_observation_metadata(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            response(tool_calls=[tool_call("c1", "record_learning_event", {
                "student_id": self.student,
                "objective": "Explicar el ciclo del agua",
                "objective_source": "inferred",
                "activity": "activity-model",
                "gap": "incomplete_procedure",
                "strategy_type": "guided_practice",
                "strategy_result": "inconclusive",
                "diagnostic_outcome": "partial",
                "evidence": "Evidencia breve.",
                "event_type": "strategy_applied",
                "objective_id": self.objective_id,
            })]),
            response(content="Continúa."),
        ]
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Explica el ciclo del agua",
            student_answer="Respuesta parcial.",
            diagnosis=diagnosis(),
            objective_id=self.objective_id,
            client=client,
            db_path=self.db,
        )
        trace = meta.tools[0]
        self.assertTrue(trace.arguments["episode_id"].startswith("episode-"))
        self.assertEqual(trace.arguments["turn_type"], "attempt")
        self.assertEqual(trace.arguments["evidence_mode"], "independent")
        with closing(connect(self.db)) as connection:
            row = connection.execute(
                "SELECT episode_id, turn_type, task_type FROM learning_events WHERE event_id=?",
                (trace.result["event_id"],),
            ).fetchone()
        self.assertEqual(row["episode_id"], trace.arguments["episode_id"])
        self.assertEqual(row["turn_type"], "attempt")

    def test_observation_task_id_is_idempotent_for_future_load_harness(self):
        episode = ensure_learning_episode(
            student_id=self.student,
            objective_id=self.objective_id,
            objective="Objetivo",
            objective_source="inferred",
            turn_type="attempt",
            db_path=self.db,
        )
        kwargs = dict(
            task_id="task-fixed",
            student_id=self.student,
            episode_id=episode["episode_id"],
            objective_id=self.objective_id,
            activity_id="activity-test",
            turn_type="attempt",
            evidence_eligible=True,
            task_type="conceptual",
            evidence_mode="independent",
            support_level="none",
            difficulty_relation="same_context",
            diagnostic_outcome="partial",
            gap="misconception",
            learning_delta=None,
            evidence_summary="Evidencia",
            evidence_profile=None,
            db_path=self.db,
        )
        record_learning_observation(**kwargs)
        record_learning_observation(**kwargs)
        with closing(connect(self.db)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM learning_observations WHERE task_id='task-fixed'"
            ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
