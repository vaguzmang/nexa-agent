from __future__ import annotations
import json
from pathlib import Path

INVALID_BASE_CASES={'ICFES-07','ICFES-12','ICFES-13','ICFES-29'}

def load_base_cases(path):
    p=Path(path)
    if not p.exists():
        raise FileNotFoundError(f'No existe {p}. Debe prepararse antes con s3_icfes_prepare.py.')
    rows=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
    usable=[r for r in rows if r.get('case_id') not in INVALID_BASE_CASES]
    if not usable: raise ValueError('No hay casos ICFES utilizables para generar carga.')
    return usable

def answer_option(seq):
    return ['A','B','C','D'][seq%4]

def make_unit(base,index):
    bucket=index%10
    if bucket in (0,1):
        mode='attempt'; message=f'Mi respuesta es la opción {answer_option(index)}.'
    elif bucket in (2,3,4,5,6):
        mode='learning_request'; message='Quiero aprender a resolver preguntas de este tipo. Explícame cómo abordarla sin decirme directamente la opción correcta.'
    else:
        mode='request_hint'; message='Dame una pista para esta pregunta sin decirme la opción correcta.'
    return {
        'unit_id':f'S4-U{index+1:05d}','sequence_no':index+1,
        'source_id':base.get('source_id'),'source_question':base.get('question_number'),
        'mode':mode,'student_id':f's4_student_{index+1:05d}',
        'activity':base.get('activity'),'message':message}

def generate(base_cases,total=1300):
    return [make_unit(base_cases[i%len(base_cases)],i) for i in range(total)]
