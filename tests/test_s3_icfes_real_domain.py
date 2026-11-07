import json,unittest
from pathlib import Path
class TestIcfesManifest(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.data=json.loads((Path(__file__).resolve().parents[1]/'data'/'S3_REAL_DOMAIN_ICFES_MANIFEST_V2.json').read_text(encoding='utf-8'))
 def test_30_references(self): self.assertEqual(sum(len(s['selected_questions']) for s in self.data['sources']),30)
 def test_official_sources(self):
  self.assertEqual(len(self.data['sources']),2)
  for s in self.data['sources']: self.assertIn('icfes.gov.co',s['url'])
 def test_answer_keys(self):
  for s in self.data['sources']:
   for q in s['selected_questions']: self.assertIn(q['official_answer'],{'A','B','C','D'})
if __name__=='__main__': unittest.main()
