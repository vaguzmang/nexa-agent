import unittest

import s2_e2e_10


class S2E2EHarnessTests(unittest.TestCase):
    def test_exactly_ten_cases(self):
        self.assertEqual(10, len(s2_e2e_10.CASES))

    def test_case_ids_are_unique(self):
        ids = [case["case_id"] for case in s2_e2e_10.CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_cases_have_activity_and_student_answer(self):
        for case in s2_e2e_10.CASES:
            self.assertTrue(case["activity"].strip())
            self.assertTrue(case["student_answer"].strip())


if __name__ == "__main__":
    unittest.main()
