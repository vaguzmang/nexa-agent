from __future__ import annotations
import json,re
from pathlib import Path
import httpx
try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit('Falta pypdf. Ejecuta: pip install -r requirements-s3-realdata.txt')
ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'data'/'S3_REAL_DOMAIN_ICFES_MANIFEST_V2.json'
CACHE=ROOT/'data'/'_icfes_cache'
OUTPUT=ROOT/'data'/'S3_REAL_DOMAIN_ICFES_V2.jsonl'

def download(url,path):
    if path.exists() and path.stat().st_size>10000: return
    path.parent.mkdir(parents=True,exist_ok=True)
    print('Descargando fuente oficial:',url)
    with httpx.Client(follow_redirects=True,timeout=120) as c:
        r=c.get(url); r.raise_for_status(); path.write_bytes(r.content)

def normalize(text):
    text=text.replace('\u00ad','')
    text=re.sub(r'Cuadernillo de preguntas\s+Prueba [^\n]+\s+\d+\s*',' ',text,flags=re.I)
    text=re.sub(r'\n\s*\.\s*\n','\n',text)
    text=re.sub(r'[ \t]+',' ',text)
    text=re.sub(r'\n{3,}','\n\n',text)
    return text.strip()

def pdf_text(path):
    return normalize('\n'.join((p.extract_text() or '') for p in PdfReader(str(path)).pages))

def extract_question(full_text,n):
    start=re.search(rf'(?:^|\n)\s*Pregunta\s+{n}\b',full_text,re.I)
    if not start: raise ValueError(f'No se encontró Pregunta {n}')
    nxt=re.search(rf'(?:^|\n)\s*Pregunta\s+{n+1}\b',full_text[start.end():],re.I)
    end=start.end()+nxt.start() if nxt else len(full_text)
    block=full_text[start.start():end].strip()
    block=re.sub(r'\n\s*\d{1,2}\s*\n','\n',block)
    return re.sub(r'\n{3,}','\n\n',block).strip()

def distractor(a):
    x=['A','B','C','D']; return x[(x.index(a)+1)%4]

def main():
    m=json.loads(MANIFEST.read_text(encoding='utf-8')); cases=[]; counter=0
    for src in m['sources']:
        pdf=CACHE/f"{src['source_id']}.pdf"; download(src['url'],pdf); full=pdf_text(pdf)
        for item in src['selected_questions']:
            counter+=1; q=int(item['question']); official=item['official_answer']; activity=extract_question(full,q)
            mode='correct' if counter%2 else 'incorrect'; chosen=official if mode=='correct' else distractor(official)
            cases.append({
                'case_id':f'ICFES-{counter:02d}','student_id':f'icfes_real_{counter:02d}',
                'flow_type':'diagnosis_required','subject':src['subject'],'source_id':src['source_id'],
                'source_title':src['title'],'source_url':src['url'],'question_number':q,
                'source_kind':'official_released_previous_exam_question','activity':activity,
                'message':f'Mi respuesta es la opción {chosen}.','response_mode':mode,
                'official_answer':official,'chosen_answer':chosen,
                'expected':{'should_diagnose':True,'evidence_result':'meets' if mode=='correct' else 'does_not_meet','gap_type':'none' if mode=='correct' else None,'forbid_mastery':True}
            })
    OUTPUT.write_text('\n'.join(json.dumps(c,ensure_ascii=False) for c in cases)+'\n',encoding='utf-8')
    print('Dataset preparado:',OUTPUT); print('Casos:',len(cases))
    for s in sorted({c['subject'] for c in cases}): print(f"  {s}: {sum(c['subject']==s for c in cases)}")
    print('Archivo generado localmente; no se versiona.')
if __name__=='__main__': main()
