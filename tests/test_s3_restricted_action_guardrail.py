import unittest

from s2.agent import (
    SYSTEM_PROMPT_COMPACT_RESTRICTED,
    _looks_like_pseudo_tool_call,
    _restricted_action_instruction,
)


class RestrictedActionGuardrailTests(unittest.TestCase):
    def test_reassess_recall_prompt_forbids_tools_and_requires_recovery_question(self):
        text = (
            SYSTEM_PROMPT_COMPACT_RESTRICTED
            + " "
            + _restricted_action_instruction("reassess_recall")
        ).lower()
        self.assertIn("no", text)
        self.assertIn("herramient", text)
        self.assertIn("pregunta", text)
        self.assertIn("recuper", text)
        self.assertIn("no asumas", text)

    def test_visible_pseudo_tool_json_is_detected(self):
        payload = '{"name":"list_pedagogical_options","arguments":{"student_id":"s"}}'
        self.assertTrue(_looks_like_pseudo_tool_call(payload))

    def test_normal_pedagogical_response_is_not_flagged_as_tool(self):
        text = "Antes de explicarlo otra vez, ¿qué recuerdas sobre el papel de la luz en la fotosíntesis?"
        self.assertFalse(_looks_like_pseudo_tool_call(text))


if __name__ == "__main__":
    unittest.main()
