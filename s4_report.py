from __future__ import annotations
import argparse,statistics
from contextlib import closing
from datetime import datetime
from s4.queue import connect,ensure_schema,get_run,counts

def parse(s): return datetime.fromisoformat(s) if s else None

def main():
    p=argparse.ArgumentParser(); p.add_argument('--run-id',required=True); p.add_argument('--db',default='data/s4_load.db'); a=p.parse_args(); ensure_schema(a.db)
    run=get_run(a.db,a.run_id)
    if not run: raise SystemExit('run_id no existe.')
    d=counts(a.db,a.run_id)
    with closing(connect(a.db)) as c:
        hb=[dict(r) for r in c.execute('SELECT * FROM s4_heartbeats WHERE run_id=? ORDER BY recorded_at',(a.run_id,)).fetchall()]
        units=[dict(r) for r in c.execute('SELECT * FROM s4_units WHERE run_id=? ORDER BY sequence_no',(a.run_id,)).fetchall()]
    completed=[u for u in units if u['status']=='completed']; retries=[u for u in units if int(u['attempts'] or 0)>1]; starts=[parse(x['recorded_at']) for x in hb]
    max_gap=max([(b-a).total_seconds() for a,b in zip(starts,starts[1:])],default=None); elapsed=None
    if run.get('started_at'):
        end=parse(run.get('finished_at')) or (starts[-1] if starts else None)
        if end: elapsed=(end-parse(run['started_at'])).total_seconds()/3600
    print('\nNEXA S4 — LOAD REPORT\n'); print('run_id:',a.run_id); print('status:',run['status']); print('started_at:',run.get('started_at')); print('finished_at:',run.get('finished_at')); print('elapsed_hours:',round(elapsed,3) if elapsed is not None else None); print('target_units:',run['target_units']); print('counts:',d); print('heartbeats:',len(hb)); print('max_heartbeat_gap_seconds:',round(max_gap,2) if max_gap is not None else None); print('units_with_retry:',len(retries)); print('avg_tokens:',round(statistics.mean([u['total_tokens'] for u in completed if u['total_tokens'] is not None]),2) if completed else None); print('avg_latency_ms:',round(statistics.mean([u['latency_ms'] for u in completed if u['latency_ms'] is not None]),2) if completed else None); print('avg_llm_calls:',round(statistics.mean([u['llm_calls'] for u in completed if u['llm_calls'] is not None]),2) if completed else None); print('\nS4 CHECKS'); print('completed>=1000:',d['completed']>=1000); print('elapsed>=12h:',elapsed is not None and elapsed>=12.0); print('heartbeat_gap<=180s:',max_gap is not None and max_gap<=180)
if __name__=='__main__': main()
