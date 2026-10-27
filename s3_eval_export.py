from __future__ import annotations
import csv,json
from contextlib import closing
from pathlib import Path
from s2.storage import connect
from s3.evaluation import ensure_evaluation_schema,evaluation_report
ROOT=Path(__file__).resolve().parent; ART=ROOT/'artifacts'
def main():
    ensure_evaluation_schema(); ART.mkdir(exist_ok=True)
    with closing(connect()) as c:
        rows=[dict(r) for r in c.execute('''
            SELECT e.benchmark_case_id,e.benchmark_status,e.flow_type,e.expected_behavior,e.observed_behavior,e.quality_pass,e.notes,e.source,
                   t.task_id,t.started_at,t.finished_at,t.diagnosis_skipped,t.diagnosis_prompt_tokens,t.diagnosis_completion_tokens,t.diagnosis_tokens,
                   t.agent_prompt_tokens,t.agent_completion_tokens,t.agent_tokens,t.total_tokens,t.visible_token_sum,t.total_latency_ms,t.llm_calls,t.tool_calls,
                   t.repairs,t.errors,t.estimated_cost_usd,t.status,t.cost_optimized
            FROM s3_evaluations e JOIN task_runs t ON t.task_id=e.task_id ORDER BY e.benchmark_case_id
        ''').fetchall()]
    jp=ART/'S3_EVALUATION_CASES.json'; jp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    cp=ART/'S3_EVALUATION_CASES.csv'
    if rows:
        with cp.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    sp=ART/'S3_EVALUATION_SUMMARY.json'; sp.write_text(json.dumps(evaluation_report(),ensure_ascii=False,indent=2),encoding='utf-8')
    print(jp); print(cp); print(sp)
if __name__=='__main__': main()
