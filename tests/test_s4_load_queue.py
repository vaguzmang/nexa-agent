import tempfile,time,unittest
from pathlib import Path
from s4.queue import create_run,seed_units,claim_unit,mark_completed,mark_retry_or_failed,counts,recover_stale_running,heartbeat,get_run
from s4.workload import generate

class S4LoadQueueTests(unittest.TestCase):
    def setUp(self):
        f=tempfile.NamedTemporaryFile(suffix='.db',delete=False); f.close(); self.path=Path(f.name)
        create_run(self.path,run_id='r1',target_units=2,duration_hours=12,workers=3,rate_per_hour=100)
        seed_units(self.path,'r1',[
            {'unit_id':'u1','sequence_no':1,'mode':'learning_request','student_id':'s1','activity':'a','message':'m'},
            {'unit_id':'u2','sequence_no':2,'mode':'attempt','student_id':'s2','activity':'a2','message':'m2'}])
    def tearDown(self):
        try:self.path.unlink()
        except PermissionError:pass
    def test_claim_is_atomic_and_status_running(self):
        u=claim_unit(self.path,'r1',worker_id='w1',now_epoch=time.time()); self.assertEqual(u['unit_id'],'u1'); self.assertEqual(counts(self.path,'r1')['running'],1)
    def test_completed_counts_once(self):
        u=claim_unit(self.path,'r1',worker_id='w1',now_epoch=time.time()); mark_completed(self.path,u['unit_id'],task_id='t1',metrics={'total_tokens':10,'total_latency_ms':20,'llm_calls':1,'tool_calls':0}); self.assertEqual(counts(self.path,'r1')['completed'],1)
    def test_retry_then_dead_letter(self):
        u=claim_unit(self.path,'r1',worker_id='w1',now_epoch=time.time()); self.assertEqual(mark_retry_or_failed(self.path,u['unit_id'],error=RuntimeError('x'),next_attempt_at=0,max_attempts=2),'retry_wait'); u=claim_unit(self.path,'r1',worker_id='w2',now_epoch=time.time()); self.assertEqual(mark_retry_or_failed(self.path,u['unit_id'],error=RuntimeError('x'),next_attempt_at=0,max_attempts=2),'dead_letter')
    def test_recover_running_is_automatic(self):
        claim_unit(self.path,'r1',worker_id='w1',now_epoch=time.time()); self.assertEqual(recover_stale_running(self.path,'r1'),1); self.assertEqual(counts(self.path,'r1')['retry_wait'],1)
    def test_heartbeat_records_progress(self):
        d=heartbeat(self.path,'r1','p1'); self.assertEqual(d['pending'],2)
    def test_run_metadata_exists(self): self.assertEqual(get_run(self.path,'r1')['target_units'],2)

class S4WorkloadTests(unittest.TestCase):
    def test_generate_1300_unique_units(self):
        base=[{'case_id':'ICFES-01','source_id':'s','question_number':1,'activity':'q'}]; units=generate(base,1300); self.assertEqual(len(units),1300); self.assertEqual(len({u['unit_id'] for u in units}),1300)
    def test_mix_contains_attempt_explanation_and_hint(self):
        base=[{'case_id':'ICFES-01','source_id':'s','question_number':1,'activity':'q'}]; self.assertEqual({u['mode'] for u in generate(base,20)},{'attempt','learning_request','request_hint'})
if __name__=='__main__':unittest.main()
