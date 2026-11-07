from __future__ import annotations
import argparse,json
from pathlib import Path
from s4.workload import generate,load_base_cases
ROOT=Path(__file__).resolve().parent
DEFAULT_SOURCE=ROOT/'data'/'S3_REAL_DOMAIN_ICFES_V2.jsonl'
DEFAULT_OUTPUT=ROOT/'data'/'S4_WORKLOAD.jsonl'

def main():
    p=argparse.ArgumentParser(); p.add_argument('--source',default=str(DEFAULT_SOURCE)); p.add_argument('--output',default=str(DEFAULT_OUTPUT)); p.add_argument('--units',type=int,default=1300); a=p.parse_args()
    base=load_base_cases(a.source); units=generate(base,a.units)
    Path(a.output).write_text('\n'.join(json.dumps(u,ensure_ascii=False) for u in units)+'\n',encoding='utf-8')
    modes={}
    for u in units:modes[u['mode']]=modes.get(u['mode'],0)+1
    print('Workload:',a.output); print('unidades:',len(units)); print('preguntas base utilizables:',len(base)); print('distribución:',modes)
if __name__=='__main__': main()
