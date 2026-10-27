import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from s2.observation import observe_turn
from s2.storage import ensure_database
from s2.tools import get_learning_state, list_teaching_strategies, record_learning_event
from s3.effectiveness import build_strategy_effectiveness_profile
from s3.pedagogy import plan_strategy_candidates


class TestS3PedagogyRefinement(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "nexa.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def _diag(self, result="insufficient_evidence", gap="none"):
        return {
            "schema_version": "diag.v1.1",
            "objective": {"domain": "Conversación de aprendizaje", "skill": "Aprender"},
            "evidence": {"type": "open_ended", "result": result, "summary": "contexto", "criteria": None},
            "understanding": {"demonstrated": None if result == "insufficient_evidence" else "algo", "missing": None},
            "gap": {"present": gap != "none", "type": gap, "description": None if gap == "none" else "gap"},
            "next_step": "ask_clarifying" if result == "insufficient_evidence" else "teach",
        }

    def _apply(self, student, strategy, *, task_type="procedural", support="medium", objective_id="obj-math", institution_id=None, subject_family=None, objective_family=None):
        return record_learning_event(
            student_id=student,
            objective="Resolver ecuaciones lineales",
            objective_source="inferred",
            activity=f"a-{student}-{strategy}",
            gap="incomplete_procedure",
            strategy_type=strategy,
            strategy_result="inconclusive",
            diagnostic_outcome="partial",
            evidence="Intento inicial.",
            event_type="strategy_applied",
            objective_id=objective_id,
            episode_id=f"ep-{student}",
            turn_type="attempt",
            task_type=task_type,
            evidence_mode="independent",
            support_level="none",
            intervention_support_level=support,
            institution_id=institution_id,
            subject_family=subject_family,
            objective_family=objective_family,
            db_path=self.db,
        )

    def _close(self, student, applied_id, strategy, result, *, task_type="procedural", objective_id="obj-math", independent=True):
        return record_learning_event(
            student_id=student,
            objective="Resolver ecuaciones lineales",
            objective_source="inferred",
            activity=f"b-{student}-{strategy}",
            gap="none" if result == "helped" else "incomplete_procedure",
            strategy_type=strategy,
            strategy_result=result,
            diagnostic_outcome="correct" if result == "helped" else "incorrect",
            evidence="Evidencia posterior.",
            event_type="strategy_evaluated",
            objective_id=objective_id,
            evaluates_event_id=applied_id,
            result_reason="objective_met" if result == "helped" else "same_error_persists",
            episode_id=f"ep-{student}",
            turn_type="attempt",
            task_type=task_type,
            evidence_mode="independent" if independent else "guided",
            independent_evidence_eligible=bool(independent),
            support_level="none" if independent else "medium",
            db_path=self.db,
        )

    def test_learning_request_to_solve_equations_is_procedural(self):
        observation = observe_turn(
            activity="Comprender cómo resolver ecuaciones con paréntesis",
            student_answer="Quiero aprender a resolver ecuaciones como 3(x + 2) = 18.",
            diagnosis=self._diag(),
            turn_type_override="learning_request",
        )
        self.assertEqual(observation.task_type, "procedural")
        self.assertEqual(observation.support_level, "not_applicable")

    def test_transfer_and_retrieval_are_flags_not_task_types(self):
        transfer = observe_turn(
            activity="Aplica el mismo método en un problema nuevo",
            student_answer="Quiero aplicarlo en otro contexto.",
            diagnosis=self._diag(),
            turn_type_override="learning_request",
        )
        retrieval = observe_turn(
            activity="Recuerda la definición trabajada",
            student_answer="Quiero recordar cuál es la definición.",
            diagnosis=self._diag(),
            turn_type_override="learning_request",
        )
        self.assertTrue(transfer.transfer_context)
        self.assertTrue(retrieval.retrieval_required)
        self.assertIn(transfer.task_type, {"conceptual", "mixed", "unknown"})
        self.assertIn(retrieval.task_type, {"conceptual", "mixed", "unknown"})

    def test_sparse_aggregate_evidence_does_not_change_ranking(self):
        applied = self._apply("other", "concept_explanation", task_type="conceptual")
        self._close("other", applied["event_id"], "concept_explanation", "helped", task_type="conceptual")
        plan = plan_strategy_candidates(
            eligible=[
                {"type": "analogy", "summary": "a"},
                {"type": "concept_explanation", "summary": "c"},
            ],
            student_id="new",
            task_type="conceptual",
            db_path=self.db,
        )
        by_type = {x["strategy_type"]: x for x in plan}
        self.assertEqual(by_type["analogy"]["priority_score"], by_type["concept_explanation"]["priority_score"])
        self.assertEqual(by_type["concept_explanation"]["evidence_basis"], "sin evidencia utilizable para ranking")

    def test_institutional_evidence_can_influence_only_in_advisory_mode(self):
        import os
        old = os.environ.get("NEXA_INSTITUTIONAL_EVIDENCE_MODE")
        os.environ["NEXA_INSTITUTIONAL_EVIDENCE_MODE"] = "advisory"
        try:
            for i in range(5):
                applied = self._apply(
                    f"other-{i}", "concept_explanation", task_type="conceptual",
                    institution_id="school-1", subject_family="science", objective_family="photosynthesis",
                )
                self._close(f"other-{i}", applied["event_id"], "concept_explanation", "helped", task_type="conceptual")
            plan = plan_strategy_candidates(
                eligible=[
                    {"type": "analogy", "summary": "a"},
                    {"type": "concept_explanation", "summary": "c"},
                ],
                student_id="new", task_type="conceptual",
                institution_id="school-1", subject_family="science", objective_family="photosynthesis",
                db_path=self.db,
            )
            self.assertEqual(plan[0]["strategy_type"], "concept_explanation")
            self.assertEqual(plan[0]["institutional_confidence"], "emerging_pattern")
        finally:
            if old is None:
                os.environ.pop("NEXA_INSTITUTIONAL_EVIDENCE_MODE", None)
            else:
                os.environ["NEXA_INSTITUTIONAL_EVIDENCE_MODE"] = old

    def test_aggregate_profile_excludes_current_student(self):
        applied = self._apply("target", "worked_example")
        self._close("target", applied["event_id"], "worked_example", "helped")
        profile = build_strategy_effectiveness_profile(
            student_id="target",
            task_type="procedural",
            db_path=self.db,
        )
        self.assertIn("worked_example", profile["individual"])
        self.assertNotIn("worked_example", profile["aggregate"])

    def test_incoming_and_intervention_support_are_persisted_separately(self):
        result = record_learning_event(
            student_id="s1",
            objective="Resolver ecuaciones",
            objective_source="inferred",
            activity="a1",
            gap="none",
            strategy_type="worked_example",
            strategy_result="inconclusive",
            diagnostic_outcome="inconclusive",
            evidence="Inicio de aprendizaje.",
            event_type="strategy_applied",
            objective_id="obj-1",
            episode_id="ep-1",
            turn_type="learning_request",
            task_type="procedural",
            evidence_mode="not_applicable",
            support_level="not_applicable",
            intervention_support_level="high",
            planner_top_strategy="worked_example",
            selection_mode="planner_top",
            selection_reason="Primer candidato.",
            db_path=self.db,
        )
        self.assertTrue(result["ok"])
        state = get_learning_state("s1", db_path=self.db)
        tried = state["strategies_tried"][0]
        self.assertEqual(tried["incoming_evidence_support"], "not_applicable")
        self.assertEqual(tried["intervention_support_level"], "high")
        self.assertEqual(tried["selection_mode"], "planner_top")

    def test_procedural_explanation_ranks_worked_example_over_conceptual_options(self):
        result = list_teaching_strategies(
            "none",
            interaction_need="explanation",
            student_id="new",
            objective_id="obj-new",
            task_type="procedural",
            support_level="not_applicable",
            db_path=self.db,
        )
        self.assertEqual(result["eligible"][0]["type"], "worked_example")
        self.assertEqual(result["eligible"][0]["recommended_support_level"], "high")

    def test_agent_records_override_and_intervention_support(self):
        # Import here so the test remains isolated from transport concerns.
        from s2.agent import run_learning_agent

        def usage():
            return SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        def tool_call(cid, name, args):
            return SimpleNamespace(
                id=cid,
                type="function",
                function=SimpleNamespace(name=name, arguments=json.dumps(args)),
            )

        def response(tool_calls=None, content=None):
            return SimpleNamespace(
                model="grok-4.6",
                usage=usage(),
                choices=[SimpleNamespace(
                    finish_reason="tool_calls" if tool_calls else "stop",
                    message=SimpleNamespace(content=content, tool_calls=tool_calls),
                )],
            )

        client = Mock()
        client.chat.completions.create.side_effect = [
            response(tool_calls=[tool_call("c1", "list_teaching_strategies", {
                "gap": "none", "interaction_need": "explanation", "exclude_types": []
            })]),
            response(tool_calls=[tool_call("c2", "record_learning_event", {
                "student_id": "student-override",
                "objective": "Resolver ecuaciones",
                "objective_source": "inferred",
                "activity": "a",
                "gap": "none",
                "strategy_type": "concept_explanation",
                "strategy_result": "inconclusive",
                "diagnostic_outcome": "inconclusive",
                "evidence": "Inicio.",
                "event_type": "strategy_applied",
                "objective_id": "obj-math",
            })]),
            response(content="Primero entendamos la igualdad y luego intenta un ejercicio."),
        ]
        diagnosis = self._diag()
        _, meta = run_learning_agent(
            student_id="student-override",
            activity="Comprender cómo resolver ecuaciones",
            student_answer="Quiero aprender a resolver ecuaciones como 3(x+2)=18",
            diagnosis=diagnosis,
            objective_id="obj-math",
            objective_source="inferred",
            turn_type_override="learning_request",
            interaction_need_override="explanation",
            objective_action="create_inferred",
            client=client,
            db_path=self.db,
        )
        record_trace = next(t for t in meta.tools if t.name == "record_learning_event")
        self.assertEqual(record_trace.arguments["task_type"], "procedural")
        self.assertEqual(record_trace.arguments["planner_top_strategy"], "worked_example")
        self.assertEqual(record_trace.arguments["selection_mode"], "agent_override")
        self.assertEqual(record_trace.arguments["intervention_support_level"], "medium")
        self.assertEqual(record_trace.arguments["support_level"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
