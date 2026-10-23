import json
import unittest

from prompt import SYSTEM_PROMPT, crear_prompt


class TestPromptWithoutStudentReferenceAnswer(unittest.TestCase):
    def test_prompt_contains_only_question_and_student_answer_as_input(self):
        prompt = crear_prompt(
            "¿Por qué llueve?",
            "Las nubes están llenas.",
        )

        self.assertIn('"question": "¿Por qué llueve?"', prompt)
        self.assertIn('"student_answer": "Las nubes están llenas."', prompt)
        self.assertNotIn('"reference_answer"', prompt)

    def test_system_prompt_forbids_inventing_missing_reference_context(self):
        self.assertIn("No recibes una \"respuesta correcta\"", SYSTEM_PROMPT)
        self.assertIn("no inventes el referente", SYSTEM_PROMPT.lower())
        self.assertIn("insufficient_evidence", SYSTEM_PROMPT)
        self.assertIn("ask_clarifying", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
