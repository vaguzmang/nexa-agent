from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PATH=ROOT/"artifacts"/"S3_GATEWAY_COST_SNAPSHOTS.json"

def load():
    return [] if not PATH.exists() else json.loads(PATH.read_text(encoding="utf-8"))
def save(rows):
    PATH.parent.mkdir(parents=True,exist_ok=True)
    PATH.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")

def snapshot(a):
    rows=[r for r in load() if r["label"]!=a.label]
    row={"label":a.label,"requests":a.requests,"cost_usd":a.cost,
         "input_tokens":a.input_tokens,"output_tokens":a.output_tokens,
         "recorded_at":datetime.now(timezone.utc).isoformat(),
         "source":"Platika challenge gateway panel (manual transcription)"}
    rows.append(row); save(rows); print("Snapshot guardado:",row)

def report(a):
    rows={r["label"]:r for r in load()}
    if a.before not in rows or a.after not in rows: raise SystemExit("Faltan snapshots solicitados.")
    b,z=rows[a.before],rows[a.after]
    dr=z["requests"]-b["requests"]; dc=round(z["cost_usd"]-b["cost_usd"],6)
    di=None if b.get("input_tokens") is None or z.get("input_tokens") is None else z["input_tokens"]-b["input_tokens"]
    do=None if b.get("output_tokens") is None or z.get("output_tokens") is None else z["output_tokens"]-b["output_tokens"]
    print("\nCOSTO REAL GATEWAY\n")
    print("from:",a.before,b); print("to:",a.after,z)
    print("peticiones incrementales:",dr)
    print("input tokens incrementales:",di)
    print("output tokens incrementales:",do)
    print("costo incremental USD:",dc)
    if a.tasks:
        print("costo real por escenario objetivo:",round(dc/a.tasks,6))
        print("peticiones por escenario objetivo:",round(dr/a.tasks,4))
    if a.completed:
        print("costo real por ejecución completa:",round(dc/a.completed,6))
    if dr>0: print("costo real por petición:",round(dc/dr,6))

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("snapshot")
    s.add_argument("--label",required=True); s.add_argument("--requests",type=int,required=True); s.add_argument("--cost",type=float,required=True)
    s.add_argument("--input-tokens",type=int); s.add_argument("--output-tokens",type=int); s.set_defaults(func=snapshot)
    r=sub.add_parser("report")
    r.add_argument("--before",default="before"); r.add_argument("--after",default="after")
    r.add_argument("--tasks",type=int); r.add_argument("--completed",type=int); r.set_defaults(func=report)
    a=p.parse_args(); a.func(a)
if __name__=="__main__":
    main()
