import tempfile
import unittest
from pathlib import Path

from s2.storage import ensure_database
from s2.tools import list_teaching_strategies, record_learning_event
from s3.effectiveness import build_strategy_effectiveness_profile
from s3.governor import govern_student_response
from s3.identity import evaluate_agent_boundary
from s3.pedagogy import plan_strategy_candidates
from s3.safeguarding import assess_safeguarding


class TestS3CorePolicyPedagogy(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "nexa.db"
        ensure_database(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def _episode_pair(self, student, strategy, result, objective_id="obj-math", task_type="procedural"):
        applied = record_learning_event(
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
            difficulty_relation="same_context",
            db_path=self.db,
        )
        self.assertTrue(applied["ok"])
        terminal = record_learning_event(
            student_id=student,
            objective="Resolver ecuaciones lineales",
            objective_source="inferred",
            activity=f"b-{student}-{strategy}",
            gap="incomplete_procedure",
            strategy_type=strategy,
            strategy_result=result,
            diagnostic_outcome="correct" if result == "helped" else "incorrect",
            evidence="Evidencia posterior.",
            event_type="strategy_evaluated",
            objective_id=objective_id,
            evaluates_event_id=applied["event_id"],
            result_reason="partial_improvement" if result == "helped" else "same_error_persists",
            episode_id=f"ep-{student}",
            turn_type="attempt",
            task_type=task_type,
            evidence_mode="independent",
            support_level="none",
            difficulty_relation="same_context",
            db_path=self.db,
        )
        self.assertTrue(terminal["ok"])

    def test_agent_identity_rejects_becoming_lms(self):
        decision = evaluate_agent_boundary("lms_course_management")
        self.assertFalse(decision.allowed_in_agent_core)
        self.assertIn("integración externa", decision.reason)

    def test_agent_identity_allows_using_authorized_resources(self):
        decision = evaluate_agent_boundary("use_authorized_learning_resources")
        self.assertTrue(decision.allowed_in_agent_core)

    def test_governor_blocks_mastery_claim(self):
        result = govern_student_response("Ya dominaste el tema. Vamos al siguiente.")
        self.assertTrue(result.changed)
        self.assertNotIn("dominaste", result.text.lower())
        self.assertIn("blocked_mastery_claim", result.interventions)

    def test_governor_blocks_false_teacher_attribution(self):
        result = govern_student_response(
            "Tu profesora quiere que memorices esto.",
            objective_source="inferred",
        )
        self.assertTrue(result.changed)
        self.assertNotIn("tu profesora", result.text.lower())

    def test_governor_blocks_clinical_diagnosis(self):
        result = govern_student_response("Tienes depresión y por eso no aprendes.")
        self.assertTrue(result.changed)
        self.assertNotIn("tienes depresión", result.text.lower())

    def test_safeguarding_supportive_signal_does_not_diagnose(self):
        result = assess_safeguarding("Soy bruto, nunca voy a aprender matemáticas")
        self.assertEqual(result.level, "supportive_learning")
        self.assertFalse(result.requires_human_review)
        self.assertNotIn("depres", result.rationale.lower())

    def test_safeguarding_explicit_safety_signal_requests_human_review(self):
        result = assess_safeguarding("No quiero vivir y me quiero matar")
        self.assertEqual(result.level, "urgent")
        self.assertTrue(result.requires_human_review)
        self.assertTrue(result.pause_academic_flow)

    def test_collective_effectiveness_is_anonymous_aggregate(self):
        self._episode_pair("s1", "guided_practice", "helped")
        self._episode_pair("s2", "guided_practice", "helped")
        self._episode_pair("s3", "worked_example", "failed")
        profile = build_strategy_effectiveness_profile(task_type="procedural", db_path=self.db)
        self.assertEqual(profile["individual"], {})
        self.assertEqual(profile["aggregate"]["guided_practice"]["exposures"], 2)
        self.assertNotIn("student_id", str(profile["aggregate"]))

    def test_individual_evidence_can_outweigh_aggregate_candidate(self):
        # Global guided_practice is strong.
        for student in ["g1", "g2", "g3", "g4", "g5"]:
            self._episode_pair(student, "guided_practice", "helped")
        # This student repeatedly succeeds with worked_example.
        for i in range(3):
            self._episode_pair("target", "worked_example", "helped", objective_id=f"obj-{i}")
        eligible = [
            {"type": "guided_practice", "summary": "guided"},
            {"type": "worked_example", "summary": "worked"},
        ]
        plan = plan_strategy_candidates(
            eligible=eligible,
            student_id="target",
            task_type="procedural",
            db_path=self.db,
        )
        self.assertEqual(plan[0]["strategy_type"], "worked_example")

    def test_list_strategy_tool_returns_ranked_evidence_metadata(self):
        self._episode_pair("s1", "guided_practice", "helped")
        result = list_teaching_strategies(
            "incomplete_procedure",
            interaction_need="practice",
            student_id="new-student",
            objective_id="obj-new",
            task_type="procedural",
            support_level="medium",
            db_path=self.db,
        )
        self.assertTrue(result["eligible"])
        first = result["eligible"][0]
        self.assertIn("priority_score", first)
        self.assertIn("evidence_basis", first)

    def test_agent_prompt_keeps_agent_identity_and_nonclinical_boundary(self):
        from s2.agent import SYSTEM_PROMPT
        self.assertIn("AGENTE educativo", SYSTEM_PROMPT)
        self.assertIn("No diagnostiques depresión", SYSTEM_PROMPT)
        self.assertIn("LMS, recursos, analítica y apoyo humano son integraciones externas", SYSTEM_PROMPT)

    def test_agent_injects_planner_context_into_strategy_tool(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import Mock
        from s2.agent import run_learning_agent

        def usage():
            return SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        def tool_call(cid, name, args):
            return SimpleNamespace(id=cid, type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
        def response(tool_calls=None, content=None):
            return SimpleNamespace(
                model="grok-4.6", usage=usage(),
                choices=[SimpleNamespace(
                    finish_reason="tool_calls" if tool_calls else "stop",
                    message=SimpleNamespace(content=content, tool_calls=tool_calls),
                )],
            )

        client = Mock()
        client.chat.completions.create.side_effect = [
            response(tool_calls=[tool_call("c1", "list_teaching_strategies", {"gap": "incomplete_procedure", "exclude_types": []})]),
            response(tool_calls=[tool_call("c2", "record_learning_event", {
                "student_id": "student-x", "objective": "Resolver ecuación", "objective_source": "inferred",
                "activity": "a", "gap": "incomplete_procedure", "strategy_type": "guided_practice",
                "strategy_result": "inconclusive", "diagnostic_outcome": "partial", "evidence": "evidencia",
                "event_type": "strategy_applied", "objective_id": "obj-math"
            })]),
            response(content="Estrategia: práctica guiada. Intenta el siguiente paso."),
        ]
        diagnosis = {
            "schema_version": "diag.v1.1",
            "objective": {"domain": "Matemáticas", "skill": "Resolver ecuación"},
            "evidence": {"type": "open_ended", "result": "partial", "summary": "Falta un paso.", "criteria": None},
            "understanding": {"demonstrated": "Inicia bien.", "missing": "Despeje."},
            "gap": {"present": True, "type": "incomplete_procedure", "description": "Falta despeje."},
            "next_step": "teach",
        }
        _, meta = run_learning_agent(
            student_id="student-x", activity="Resuelve 2(x+3)=10", student_answer="x+3=10",
            diagnosis=diagnosis, objective_id="obj-math", objective_source="inferred",
            task_type="procedural", support_level="medium", client=client, db_path=self.db,
        )
        trace = next(t for t in meta.tools if t.name == "list_teaching_strategies")
        self.assertEqual(trace.arguments["student_id"], "student-x")
        self.assertEqual(trace.arguments["objective_id"], "obj-math")
        self.assertEqual(trace.arguments["task_type"], "procedural")
        self.assertEqual(trace.arguments["support_level"], "medium")


if __name__ == "__main__":
    unittest.main()
