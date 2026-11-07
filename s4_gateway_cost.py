from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
PATH=Path('artifacts/S4_GATEWAY_COST.json')
def load(): return {} if not PATH.exists() else json.loads(PATH.read_text(encoding='utf-8'))
def save(x): PATH.parent.mkdir(exist_ok=True); PATH.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True); s=sub.add_parser('snapshot'); s.add_argument('--label',choices=['before','after'],required=True); s.add_argument('--requests',type=int,required=True); s.add_argument('--cost',type=float,required=True); s.add_argument('--input-tokens',type=int); s.add_argument('--output-tokens',type=int); r=sub.add_parser('report'); r.add_argument('--completed',type=int,required=True); a=p.parse_args(); data=load()
    if a.cmd=='snapshot': data[a.label]={'requests':a.requests,'cost_usd':a.cost,'input_tokens':a.input_tokens,'output_tokens':a.output_tokens,'recorded_at':datetime.now(timezone.utc).isoformat()}; save(data); print('guardado',a.label,data[a.label]); return
    b,z=data.get('before'),data.get('after')
    if not b or not z: raise SystemExit('Faltan before/after.')
    dr=z['requests']-b['requests']; dc=z['cost_usd']-b['cost_usd']; print('peticiones incrementales:',dr); print('costo incremental USD:',round(dc,6)); print('costo real por unidad completada:',round(dc/a.completed,6)); print('peticiones por unidad completada:',round(dr/a.completed,4))
if __name__=='__main__':main()
