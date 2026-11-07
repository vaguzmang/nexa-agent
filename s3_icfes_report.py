from __future__ import annotations
import json
from contextlib import closing
from pathlib import Path
from s2.storage import connect
from s3.evaluation import ensure_evaluation_schema
ROOT=Path(__file__).resolve().parent; FAIL=ROOT/'artifacts'/'S3_ICFES_FAILURES.jsonl'
def avg(v):
    x=[float(i) for i in v if i is not None]; return round(sum(x)/len(x),4) if x else None
def main():
    ensure_evaluation_schema()
    with closing(connect()) as c:
        rows=[dict(r) for r in c.execute("""SELECT e.benchmark_case_id,e.quality_pass,e.notes,t.total_tokens,t.visible_token_sum,t.total_latency_ms,t.llm_calls,t.tool_calls,t.estimated_cost_usd,t.status FROM s3_evaluations e JOIN task_runs t ON t.task_id=e.task_id WHERE e.source='s3_real_domain_icfes_v2' ORDER BY e.benchmark_case_id""").fetchall()]
    fails=[json.loads(x) for x in FAIL.read_text(encoding='utf-8').splitlines() if x.strip()] if FAIL.exists() else []
    complete=[r for r in rows if r['status']=='success']; qp=sum(r['quality_pass']==1 for r in complete)
    print('\nNEXA S3 V2 — REAL DOMAIN ICFES\n'); print('escenarios objetivo: 30'); print('ejecuciones completas:',len(complete)); print('quality_pass:',qp); print('quality_success_rate:',round(qp/len(complete),4) if complete else None); print('fallos técnicos registrados:',len(fails)); print('tokens promedio:',avg([r['total_tokens'] for r in complete])); print('latencia promedio ms:',avg([r['total_latency_ms'] for r in complete])); print('llm_calls promedio:',avg([r['llm_calls'] for r in complete])); print('tool_calls promedio:',avg([r['tool_calls'] for r in complete])); print('costo estimado USD promedio:',avg([r['estimated_cost_usd'] for r in complete])); print('\nFuente: preguntas oficiales liberadas de Saber 11 por el Icfes.'); print('Costo real del gateway: python s3_gateway_cost.py report')
if __name__=='__main__': main()
