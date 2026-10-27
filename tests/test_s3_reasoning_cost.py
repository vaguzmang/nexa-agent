import os,unittest
from unittest.mock import patch
from s3.metrics import build_task_metrics
class Call:
    def __init__(self,prompt_tokens,completion_tokens,total_tokens,kind='normal'):
        self.prompt_tokens=prompt_tokens; self.completion_tokens=completion_tokens; self.total_tokens=total_tokens; self.kind=kind
class Meta:
    def __init__(self,calls,total_tokens=None,total_latency_ms=10,tools=None):
        self.calls=calls; self.total_tokens=total_tokens; self.total_latency_ms=total_latency_ms; self.tools=tools or []
class S3ReasoningCostTests(unittest.TestCase):
    def test_reasoning_tokens_are_billed_as_output(self):
        d=Meta([Call(1000,100,1400)],1400); a=Meta([Call(2000,200,2800)],2800)
        with patch.dict(os.environ,{'GROK_INPUT_USD_PER_MILLION':'2','GROK_OUTPUT_USD_PER_MILLION':'6'}):
            m=build_task_metrics(task_id='t1',diagnosis_meta=d,agent_meta=a,diagnosis_skipped=False,cost_optimized=True)
        self.assertAlmostEqual(m['estimated_cost_usd'],3000*2/1_000_000+1200*6/1_000_000,places=9)
    def test_visible_completion_does_not_hide_reasoning_cost(self):
        a=Meta([Call(1000,100,2000)],2000)
        with patch.dict(os.environ,{'GROK_INPUT_USD_PER_MILLION':'2','GROK_OUTPUT_USD_PER_MILLION':'6'}):
            m=build_task_metrics(task_id='t2',diagnosis_meta=None,agent_meta=a,diagnosis_skipped=True,cost_optimized=True)
        self.assertAlmostEqual(m['estimated_cost_usd'],0.008,places=9)
if __name__=='__main__': unittest.main()
