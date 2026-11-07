from __future__ import annotations
import argparse,json
from contextlib import closing
from pathlib import Path
from s2.storage import connect
from s3.evaluation import ensure_evaluation_schema,upsert_evaluation
from s3.session import run_student_turn
ROOT=Path(__file__).resolve().parent; CASES=ROOT/'data'/'S3_REAL_DOMAIN_ICFES_V2.jsonl'; FAILURES=ROOT/'artifacts'/'S3_ICFES_FAILURES.jsonl'
def load_cases():
    if not CASES.exists(): raise SystemExit('Ejecuta primero: python s3_icfes_prepare.py')
    return [json.loads(x) for x in CASES.read_text(encoding='utf-8').splitlines() if x.strip()]
def diag_dict(v): return v.model_dump() if hasattr(v,'model_dump') else (v if isinstance(v,dict) else {})
def selected(meta):
    for t in reversed(list(meta.tools or [])):
        if t.name=='record_learning_event' and isinstance(t.arguments,dict) and isinstance(t.result,dict) and t.result.get('ok'): return t.arguments.get('strategy_type')
def observed(r):
    d=diag_dict(r.diagnosis); o=r.agent_meta.learning_observation or {}
    return {'turn_type':r.intake.turn_type,'should_diagnose':bool(r.intake.should_diagnose),'evidence_result':(d.get('evidence') or {}).get('result'),'gap_type':(d.get('gap') or {}).get('type'),'task_type':o.get('task_type'),'response_format':o.get('response_format'),'objective_action':r.objective_resolution.action,'selected_strategy':selected(r.agent_meta),'errors':r.metrics.get('errors'),'repairs':r.metrics.get('repairs')}
def evaluate(c,r):
    e=c['expected']; o=observed(r); f=[]
    for k in ('should_diagnose','evidence_result'):
        if o.get(k)!=e.get(k): f.append(f'{k}: esperado={e.get(k)!r}, observado={o.get(k)!r}')
    if e.get('gap_type') is not None and o.get('gap_type')!=e.get('gap_type'): f.append(f"gap_type: esperado={e.get('gap_type')!r}, observado={o.get('gap_type')!r}")
    resp=(r.response or '').strip(); low=resp.lower()
    if not resp: f.append('respuesta vacía')
    if resp.startswith('{"name"') or '"arguments"' in resp[:180]: f.append('pseudo-tool-call visible')
    if any(x in low for x in ('ya dominaste','has dominado','dominas completamente','mastery','dominio confirmado')): f.append('mastery no sustentado')
    if int(r.metrics.get('errors') or 0): f.append(f"errors={r.metrics.get('errors')}")
    return not f,o,f
def already(case_id):
    ensure_evaluation_schema()
    with closing(connect()) as c: return c.execute('SELECT task_id FROM s3_evaluations WHERE benchmark_case_id=?',(case_id,)).fetchone()
def append_failure(x):
    FAILURES.parent.mkdir(parents=True,exist_ok=True)
    with FAILURES.open('a',encoding='utf-8') as f: f.write(json.dumps(x,ensure_ascii=False)+'\n')
def main():
    p=argparse.ArgumentParser(); p.add_argument('--count',type=int); p.add_argument('--case'); p.add_argument('--from-case',dest='from_case'); p.add_argument('--list',action='store_true'); a=p.parse_args(); cases=load_cases()
    if a.case: cases=[c for c in cases if c['case_id']==a.case]
    elif a.from_case:
        ids=[c['case_id'] for c in cases]
        if a.from_case not in ids: raise SystemExit(f'No existe {a.from_case}')
        cases=cases[ids.index(a.from_case):]
    if a.list:
        for c in cases: print(c['case_id'],'|',c['subject'],'|',f"Pregunta {c['question_number']}",'|',c['response_mode'],'|',c['source_id'])
        return
    executed=skipped=passes=tech=0
    for c in cases:
        found=already(c['case_id'])
        if found: print(f"SKIP {c['case_id']}: ya registrado ({found['task_id']})"); skipped+=1; continue
        if a.count is not None and executed>=a.count: break
        print(f"\n=== {c['case_id']} · {c['subject']} · Pregunta {c['question_number']} · {c['response_mode']} ===")
        try:
            r=run_student_turn(student_id=c['student_id'],activity=c['activity'],message=c['message'],task_id=f"task-{c['case_id'].lower()}",subject_family=c['subject'].lower().replace(' ','_'),objective_family=f"icfes_q{c['question_number']}",cost_optimized=True)
            ok,obs,why=evaluate(c,r); sm={'source_kind':c['source_kind'],'source_id':c['source_id'],'source_url':c['source_url'],'question_number':c['question_number'],'response_mode':c['response_mode'],'official_answer':c['official_answer'],'chosen_answer':c['chosen_answer']}
            upsert_evaluation(task_id=r.metrics['task_id'],benchmark_case_id=c['case_id'],benchmark_status='valid',flow_type='diagnosis_required',expected_behavior=json.dumps(c['expected'],ensure_ascii=False),observed_behavior=json.dumps(obs,ensure_ascii=False),quality_pass=ok,notes=('PASS real-domain ICFES.' if ok else 'FAIL: '+' | '.join(why))+' SOURCE='+json.dumps(sm,ensure_ascii=False),source='s3_real_domain_icfes_v2')
            print(f"{'PASS' if ok else 'FAIL'} tokens={r.metrics.get('total_tokens')} latency_ms={r.metrics.get('total_latency_ms')} llm={r.metrics.get('llm_calls')} tools={r.metrics.get('tool_calls')}")
            if not ok:
                for x in why: print('  -',x)
            passes+=int(ok); executed+=1
        except Exception as e:
            tech+=1; executed+=1; append_failure({'case_id':c['case_id'],'subject':c['subject'],'question_number':c['question_number'],'source_url':c['source_url'],'error_type':type(e).__name__,'error':str(e)}); print(f"ERROR {c['case_id']}: {type(e).__name__}: {e}")
    print('\n=== RESUMEN ICFES REAL-DOMAIN ==='); print('ejecutados:',executed); print('omitidos:',skipped); print('quality_pass:',passes); print('errores técnicos:',tech)
    if tech: print('detalle:',FAILURES)
if __name__=='__main__': main()
