from __future__ import annotations
import json
from pathlib import Path
from s3_icfes_prepare import CACHE, MANIFEST, download, extract_question, pdf_text

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "data" / "S3_ICFES_INPUT_QUALITY_AUDIT_V1.json"
OUTPUT = ROOT / "data" / "S3_REAL_DOMAIN_ICFES_REPLACEMENTS_V2.jsonl"

def distractor(answer):
    order=["A","B","C","D"]
    return order[(order.index(answer)+1)%4]

def main():
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    math=next(s for s in manifest["sources"] if s["source_id"]=="ICFES_MAT_2026")
    pdf_path=CACHE/"ICFES_MAT_2026.pdf"
    download(math["url"],pdf_path)
    full=pdf_text(pdf_path)
    cases=[]
    for item in audit["replacement_questions"]:
        official=item["official_answer"]; mode=item["response_mode"]
        chosen=official if mode=="correct" else distractor(official)
        cases.append({
            "case_id":item["case_id"],
            "replacement_for":item["replacement_for"],
            "student_id":item["case_id"].lower().replace("-","_"),
            "flow_type":"diagnosis_required",
            "subject":"Matemáticas",
            "source_id":"ICFES_MAT_2026",
            "source_url":math["url"],
            "question_number":item["question"],
            "source_kind":"official_released_previous_exam_question",
            "activity":extract_question(full,int(item["question"])),
            "message":f"Mi respuesta es la opción {chosen}.",
            "response_mode":mode,
            "official_answer":official,
            "chosen_answer":chosen,
            "expected":{
                "should_diagnose":True,
                "evidence_result":"meets" if mode=="correct" else "does_not_meet",
                "gap_type":"none" if mode=="correct" else None,
                "forbid_mastery":True,
            }
        })
    OUTPUT.write_text("\n".join(json.dumps(c,ensure_ascii=False) for c in cases)+"\n",encoding="utf-8")
    print("Reemplazos preparados:",OUTPUT)
    for c in cases:
        print(c["case_id"],"reemplaza",c["replacement_for"],"Pregunta",c["question_number"],c["response_mode"])
if __name__=="__main__":
    main()
