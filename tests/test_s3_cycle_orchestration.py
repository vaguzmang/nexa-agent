import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.agent import (
    S2AgentError,
    classify_pending_intervention,
    derive_inferred_objective_id,
    run_learning_agent,
)
from s2.storage import ensure_database
from s2.tools import TOOL_DEFINITIONS, get_learning_state, record_learning_event


def diagnosis_dict(
    *,
    domain="Ciencias naturales",
    skill="Explicar el ciclo del agua que produce la lluvia",
    evidence_result="partial",
    summary="Menciona parte del proceso.",
    gap_type="incomplete_procedure",
    gap_present=True,
    next_step="teach",
):
    return {
        "schema_version": "diag.v1.1",
        "objective": {"domain": domain, "skill": skill},
        "evidence": {
            "type": "open_ended",
            "result": evidence_result,
            "summary": summary,
            "criteria": None,
        },
        "understanding": {
            "demonstrated": None if evidence_result == "insufficient_evidence" else "Evidencia observada.",
            "missing": None if evidence_result == "insufficient_evidence" else "Aún falta parte del objetivo.",
        },
        "gap": {
            "present": gap_present,
            "type": gap_type if gap_present else "none",
            "description": None if not gap_present else "Brecha observada.",
        },
        "next_step": next_step,
    }


def usage(total=100):
    return SimpleNamespace(prompt_tokens=70, completion_tokens=30, total_tokens=total)


def response(content="Continúa con una práctica breve."):
    return SimpleNamespace(
        model="grok-4.6",
        usage=usage(),
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=content, tool_calls=None),
            )
        ],
    )


class TestS3CycleOrchestration(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "cycle-orchestration.db"
        ensure_database(self.db)
        self.student = "student_cycle"
        self.objective_id = "water-cycle-001"

    def tearDown(self):
        self.tempdir.cleanup()

    def _seed_pending(
        self,
        *,
        objective_id=None,
        outcome="incorrect",
        gap="incomplete_procedure",
        strategy="guided_practice",
        source="inferred",
    ):
        return record_learning_event(
            student_id=self.student,
            objective="Explicar el ciclo del agua que produce la lluvia",
            objective_source=source,
            activity="activity-turn-1",
            gap=gap,
            strategy_type=strategy,
            strategy_result="inconclusive",
            diagnostic_outcome=outcome,
            evidence="Evidencia previa.",
            event_type="strategy_applied",
            objective_id=objective_id or self.objective_id,
            db_path=self.db,
        )

    def _run(self, diagnosis=None, objective_id=None, objective_source="inferred"):
        client = Mock()
        client.chat.completions.create.return_value = response()
        text, meta = run_learning_agent(
            student_id=self.student,
            activity="¿Qué pasa con el vapor antes de que llueva?",
            student_answer="Se enfría y forma gotas en las nubes.",
            diagnosis=diagnosis or diagnosis_dict(),
            objective_id=objective_id or self.objective_id,
            objective_source=objective_source,
            client=client,
            db_path=self.db,
        )
        return client, text, meta

    def test_no_pending_intervention_does_not_create_evaluation_event(self):
        _, _, meta = self._run()
        self.assertEqual(meta.cycle_evaluation.status, "no_pending")
        state = get_learning_state(self.student, db_path=self.db)
        self.assertFalse(state["has_history"])

    def test_partial_improvement_closes_pending_as_helped(self):
        applied = self._seed_pending(outcome="incorrect")
        _, _, meta = self._run(diagnosis=diagnosis_dict(evidence_result="partial"))

        self.assertEqual(meta.cycle_evaluation.status, "evaluated")
        self.assertEqual(meta.cycle_evaluation.pending_event_id, applied["event_id"])
        self.assertEqual(meta.cycle_evaluation.result, "helped")
        self.assertEqual(meta.cycle_evaluation.reason, "partial_improvement")

        state = get_learning_state(self.student, db_path=self.db)
        self.assertIsNone(state["pending_intervention"])
        self.assertEqual(state["strategies_tried"][0]["result"], "helped")

    def test_same_error_persists_closes_pending_as_failed(self):
        self._seed_pending(outcome="partial", gap="incomplete_procedure")
        _, _, meta = self._run(
            diagnosis=diagnosis_dict(
                evidence_result="partial",
                gap_type="incomplete_procedure",
            )
        )
        self.assertEqual(meta.cycle_evaluation.result, "failed")
        self.assertEqual(meta.cycle_evaluation.reason, "same_error_persists")

    def test_insufficient_evidence_preserves_pending_until_evaluable_attempt(self):
        self._seed_pending(outcome="partial")
        diag = diagnosis_dict(
            evidence_result="insufficient_evidence",
            gap_present=False,
            next_step="ask_clarifying",
        )
        _, _, meta = self._run(diagnosis=diag)
        self.assertEqual(meta.cycle_evaluation.status, "pending_preserved")
        self.assertIsNone(meta.cycle_evaluation.result)
        self.assertEqual(meta.cycle_evaluation.reason, "insufficient_evidence")
        state = get_learning_state(self.student, db_path=self.db)
        self.assertIsNotNone(state["pending_intervention"])

    def test_objective_change_interrupts_previous_strategy_without_evaluating_it(self):
        self._seed_pending(objective_id="objective-old")
        _, _, meta = self._run(objective_id="objective-new")

        self.assertEqual(meta.cycle_evaluation.status, "interrupted")
        self.assertIsNone(meta.cycle_evaluation.result)
        self.assertEqual(
            meta.cycle_evaluation.reason,
            "topic_switched_before_attempt",
        )

        from s2.storage import connect
        from contextlib import closing
        with closing(connect(self.db)) as connection:
            row = connection.execute(
                """
                SELECT event_type, diagnostic_outcome, result_reason
                FROM learning_events
                WHERE event_type = 'strategy_interrupted'
                ORDER BY recorded_at DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["event_type"], "strategy_interrupted")
        self.assertEqual(row["diagnostic_outcome"], "inconclusive")
        self.assertEqual(
            row["result_reason"],
            "topic_switched_before_attempt",
        )

    def test_newly_failed_strategy_is_immediately_exposed_for_exclusion(self):
        self._seed_pending(
            outcome="partial",
            gap="incomplete_procedure",
            strategy="guided_practice",
        )
        client, _, meta = self._run(
            diagnosis=diagnosis_dict(
                evidence_result="partial",
                gap_type="incomplete_procedure",
            )
        )
        self.assertEqual(meta.cycle_evaluation.result, "failed")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        payload = messages[1]["content"]
        self.assertIn(
            '"failed_strategy_types_for_current_objective": ["guided_practice"]',
            payload,
        )

    def test_tool_schema_only_allows_grok_to_record_strategy_applied(self):
        record_tool = next(
            tool for tool in TOOL_DEFINITIONS
            if tool["function"]["name"] == "record_learning_event"
        )
        params = record_tool["function"]["parameters"]
        self.assertEqual(params["properties"]["event_type"]["enum"], ["strategy_applied"])
        self.assertEqual(params["properties"]["strategy_result"]["enum"], ["inconclusive"])
        self.assertIn("objective_id", params["required"])
        self.assertNotIn("evaluates_event_id", params["properties"])

    def test_teacher_source_without_stable_objective_id_is_rejected(self):
        client = Mock()
        client.chat.completions.create.return_value = response()
        with self.assertRaises(S2AgentError):
            run_learning_agent(
                student_id=self.student,
                activity="Actividad",
                student_answer="Respuesta",
                diagnosis=diagnosis_dict(),
                objective_source="teacher",
                client=client,
                db_path=self.db,
            )
        self.assertEqual(client.chat.completions.create.call_count, 0)

    def test_explicit_teacher_objective_identity_is_passed_as_context_not_inferred(self):
        client, _, _ = self._run(
            objective_id="teacher-water-001",
            objective_source="teacher",
        )
        first_messages = client.chat.completions.create.call_args.kwargs["messages"]
        user_payload = first_messages[1]["content"]
        self.assertIn('"objective_id_for_record": "teacher-water-001"', user_payload)
        self.assertIn('"objective_source_for_record": "teacher"', user_payload)

    def test_inferred_objective_id_is_deterministic_but_not_teacher_attributed(self):
        diag = diagnosis_dict()
        first = derive_inferred_objective_id(diag)
        second = derive_inferred_objective_id(diag)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("inferred-"))

        client = Mock()
        client.chat.completions.create.return_value = response()
        _, meta = run_learning_agent(
            student_id=self.student,
            activity="Actividad",
            student_answer="Respuesta",
            diagnosis=diag,
            client=client,
            db_path=self.db,
        )
        self.assertEqual(meta.cycle_evaluation.objective_id, first)


if __name__ == "__main__":
    unittest.main()
