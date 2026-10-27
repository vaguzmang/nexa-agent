from __future__ import annotations
import argparse, json
from pathlib import Path
from contextlib import closing
from s2.storage import connect
from s3.evaluation import upsert_evaluation, ensure_evaluation_schema
from s3.session import run_student_turn

ROOT=Path(__file__).resolve().parent
CASES_PATH=ROOT/'data'/'S3_REAL_CONTROLLED_CASES_V1.jsonl'
FAILURES_PATH=ROOT/'artifacts'/'S3_BATCH_FAILURES.jsonl'

def load_cases():
    return [json.loads(x) for x in CASES_PATH.read_text(encoding='utf-8').splitlines() if x.strip()]

def diag_dict(v):
    return v.model_dump() if hasattr(v,'model_dump') else (v if isinstance(v,dict) else {})

def selected_strategy(meta):
    for trace in reversed(list(meta.tools or [])):
        if trace.name=='record_learning_event' and isinstance(trace.arguments,dict) and isinstance(trace.result,dict) and trace.result.get('ok'):
            return trace.arguments.get('strategy_type')
    return None

def observed(result):
    d=diag_dict(result.diagnosis); o=result.agent_meta.learning_observation or {}
    return {
        'turn_type':result.intake.turn_type,
        'should_diagnose':bool(result.intake.should_diagnose),
        'evidence_result':(d.get('evidence') or {}).get('result'),
        'gap_type':(d.get('gap') or {}).get('type'),
        'task_type':o.get('task_type'),
        'response_format':o.get('response_format'),
        'retrieval_required':o.get('retrieval_required'),
        'transfer_context':o.get('transfer_context'),
        'objective_action':result.objective_resolution.action,
        'episode_action':result.agent_meta.episode_action,
        'selected_strategy':selected_strategy(result.agent_meta),
        'errors':result.metrics.get('errors'),
        'repairs':result.metrics.get('repairs'),
    }

def evaluate(case,result):
    exp=case.get('expected') or {}; obs=observed(result); fail=[]
    for key in ['should_diagnose','evidence_result','gap_type','task_type','retrieval_required','transfer_context','objective_action','episode_action']:
        if key in exp and obs.get(key)!=exp.get(key): fail.append(f'{key}: esperado={exp.get(key)!r}, observado={obs.get(key)!r}')
    allowed=exp.get('selected_strategy_in')
    if allowed and obs.get('selected_strategy') not in allowed: fail.append(f"selected_strategy={obs.get('selected_strategy')!r} fuera de {allowed!r}")
    response=(result.response or '').strip(); lower=response.lower()
    if not response: fail.append('respuesta vacía')
    if response.startswith('{"name"') or '"arguments"' in response[:180]: fail.append('pseudo-tool-call visible')
    if exp.get('forbid_mastery',True):
        if any(x in lower for x in ('ya dominaste','has dominado','dominas completamente','mastery','dominio confirmado')): fail.append('afirmación de mastery no sustentada')
    if int(result.metrics.get('errors') or 0)!=0: fail.append(f"errors={result.metrics.get('errors')}")
    return not fail,obs,fail

def case_already_exists(case_id):
    ensure_evaluation_schema()
    with closing(connect()) as c:
        return c.execute('SELECT task_id FROM s3_evaluations WHERE benchmark_case_id=?',(case_id,)).fetchone()

def append_failure(payload):
    FAILURES_PATH.parent.mkdir(parents=True,exist_ok=True)
    with FAILURES_PATH.open('a',encoding='utf-8') as f: f.write(json.dumps(payload,ensure_ascii=False)+'\n')

def main():
    p=argparse.ArgumentParser(description='Ejecuta casos controlados S3 contra NEXA/Grok y los registra en el benchmark.')
    p.add_argument('--count',type=int,default=None)
    p.add_argument('--case')
    p.add_argument('--from-case',dest='from_case')
    p.add_argument('--list',action='store_true')
    a=p.parse_args(); cases=load_cases()
    if a.case:
        cases=[c for c in cases if c['case_id']==a.case]
        if not cases: raise SystemExit(f'No existe {a.case}')
    elif a.from_case:
        ids=[c['case_id'] for c in cases]
        if a.from_case not in ids: raise SystemExit(f'No existe {a.from_case}')
        cases=cases[ids.index(a.from_case):]
    if a.list:
        for c in cases: print(c['case_id'],c['flow_type'],c['student_id'])
        return
    executed=skipped=passes=tech_errors=0
    for case in cases:
        existing=case_already_exists(case['case_id'])
        if existing:
            print(f"SKIP {case['case_id']}: ya registrado ({existing['task_id']})"); skipped+=1; continue
        if a.count is not None and executed>=a.count: break
        print(f"\n=== {case['case_id']} · {case['flow_type']} ===")
        try:
            result=run_student_turn(student_id=case['student_id'],activity=case.get('activity'),message=case['message'],task_id=f"task-benchmark-{case['case_id'].lower()}",cost_optimized=True)
            ok,obs,why=evaluate(case,result)
            # Importante: los fallos de calidad siguen siendo benchmark_status=valid.
            upsert_evaluation(task_id=result.metrics['task_id'],benchmark_case_id=case['case_id'],benchmark_status='valid',flow_type=case['flow_type'],expected_behavior=json.dumps(case.get('expected') or {},ensure_ascii=False),observed_behavior=json.dumps(obs,ensure_ascii=False),quality_pass=ok,notes=('PASS contract-based evaluation.' if ok else 'FAIL: '+' | '.join(why)),source='s3_real_controlled_batch_v1')
            print(f"{'PASS' if ok else 'FAIL'} tokens={result.metrics.get('total_tokens')} latency_ms={result.metrics.get('total_latency_ms')} llm={result.metrics.get('llm_calls')} tools={result.metrics.get('tool_calls')}")
            if not ok:
                for x in why: print('  -',x)
            passes+=int(ok); executed+=1
        except Exception as e:
            tech_errors+=1; executed+=1
            append_failure({'case_id':case['case_id'],'error_type':type(e).__name__,'error':str(e)})
            print(f"ERROR {case['case_id']}: {type(e).__name__}: {e}")
    print('\n=== RESUMEN DEL LOTE ===')
    print('ejecutados:',executed); print('omitidos por ya existir:',skipped); print('quality_pass:',passes); print('errores técnicos:',tech_errors)
    if tech_errors: print('detalle:',FAILURES_PATH)
if __name__=='__main__': main()
