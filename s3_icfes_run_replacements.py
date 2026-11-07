from __future__ import annotations
import argparse,json
from contextlib import closing
from pathlib import Path
from s2.storage import connect
from s3.evaluation import ensure_evaluation_schema,upsert_evaluation
from s3.session import run_student_turn

ROOT=Path(__file__).resolve().parent
CASES=ROOT/"data"/"S3_REAL_DOMAIN_ICFES_REPLACEMENTS_V2.jsonl"
FAILURES=ROOT/"artifacts"/"S3_ICFES_VALIDATION_FAILURES.jsonl"

def load_cases():
    if not CASES.exists(): raise SystemExit("Ejecuta primero: python s3_icfes_prepare_replacements.py")
    return [json.loads(x) for x in CASES.read_text(encoding="utf-8").splitlines() if x.strip()]

def diag_dict(v):
    return v.model_dump() if hasattr(v,"model_dump") else (v if isinstance(v,dict) else {})

def already(case_id):
    ensure_evaluation_schema()
    with closing(connect()) as c:
        return c.execute("SELECT task_id FROM s3_evaluations WHERE benchmark_case_id=?",(case_id,)).fetchone()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--list",action="store_true"); p.add_argument("--count",type=int); a=p.parse_args()
    cases=load_cases()
    if a.list:
        for c in cases: print(c["case_id"],"Pregunta",c["question_number"],c["response_mode"])
        return
    executed=passes=tech_errors=0
    for c in cases:
        if a.count is not None and executed>=a.count: break
        if already(c["case_id"]): print("SKIP",c["case_id"],"ya registrado"); continue
        try:
            result=run_student_turn(
                student_id=c["student_id"],activity=c["activity"],message=c["message"],
                task_id=f"task-{c['case_id'].lower()}",
                subject_family="matemáticas",objective_family=f"icfes_q{c['question_number']}",
                cost_optimized=True)
            d=diag_dict(result.diagnosis)
            actual=(d.get("evidence") or {}).get("result"); expected=c["expected"]["evidence_result"]
            ok=actual==expected and int(result.metrics.get("errors") or 0)==0
            obs={"evidence_result":actual,"gap_type":(d.get("gap") or {}).get("type"),
                 "should_diagnose":bool(result.intake.should_diagnose),
                 "errors":result.metrics.get("errors"),"repairs":result.metrics.get("repairs")}
            upsert_evaluation(
                task_id=result.metrics["task_id"],benchmark_case_id=c["case_id"],
                benchmark_status="valid",flow_type="diagnosis_required",
                expected_behavior=json.dumps(c["expected"],ensure_ascii=False),
                observed_behavior=json.dumps(obs,ensure_ascii=False),
                quality_pass=ok,
                notes=(("PASS replacement real-domain ICFES." if ok else f"FAIL replacement expected={expected} actual={actual}")+
                       f" REPLACES={c['replacement_for']} SOURCE_Q={c['question_number']}"),
                source="s3_real_domain_icfes_v2_replacement")
            print(f"{c['case_id']} {'PASS' if ok else 'FAIL'} expected={expected} actual={actual} tokens={result.metrics.get('total_tokens')}")
            passes+=int(ok); executed+=1
        except Exception as e:
            tech_errors+=1; executed+=1
            FAILURES.parent.mkdir(parents=True,exist_ok=True)
            with FAILURES.open("a",encoding="utf-8") as f:
                f.write(json.dumps({"case_id":c["case_id"],"replacement_for":c["replacement_for"],
                                    "error_type":type(e).__name__,"error":str(e)},ensure_ascii=False)+"\n")
            print(f"{c['case_id']} ERROR {type(e).__name__}: {e}")
    print("\n=== VALIDACIÓN DE REEMPLAZOS ===")
    print("ejecutados:",executed); print("quality_pass:",passes); print("errores técnicos:",tech_errors)
if __name__=="__main__":
    main()
