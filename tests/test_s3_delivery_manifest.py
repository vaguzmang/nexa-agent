import json,unittest
from pathlib import Path
class S3DeliveryManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[1]/'data'/'S3_REAL_CONTROLLED_CASES_V1.jsonl'
        cls.cases=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    def test_manifest_has_42_new_cases(self): self.assertEqual(len(self.cases),42)
    def test_ids_cover_09_to_50(self):
        ids=[x['case_id'] for x in self.cases]; self.assertEqual(len(ids),len(set(ids))); self.assertEqual(ids[0],'S3-R09'); self.assertEqual(ids[-1],'S3-R50')
    def test_every_case_has_contract(self):
        for c in self.cases:
            self.assertTrue(c['student_id']); self.assertTrue(c['message']); self.assertTrue(c['flow_type']); self.assertIsInstance(c['expected'],dict)
if __name__=='__main__': unittest.main()
