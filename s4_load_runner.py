from __future__ import annotations
import argparse,json,signal,time,uuid
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timedelta,timezone
from pathlib import Path
from s3.session import run_student_turn
from s4.queue import claim_unit,counts,create_run,ensure_schema,finish_run,heartbeat,mark_completed,mark_retry_or_failed,recover_stale_running,seed_units,start_run,get_run
ROOT=Path(__file__).resolve().parent
DEFAULT_WORKLOAD=ROOT/'data'/'S4_WORKLOAD.jsonl'
DEFAULT_DB=ROOT/'data'/'s4_load.db'
BACKOFF=(15,60,180)

def utcnow(): return datetime.now(timezone.utc)
def load_units(path): return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]

def process_unit(unit,db_path,max_attempts):
    task_id=f"s4-task-{unit['unit_id'].lower()}"
    try:
        result=run_student_turn(student_id=unit['student_id'],activity=unit.get('activity'),message=unit['message'],task_id=task_id,subject_family='icfes',objective_family=f"load_q{unit.get('source_question')}",cost_optimized=True)
        mark_completed(db_path,unit['unit_id'],task_id=task_id,metrics=result.metrics)
        return ('completed',unit['unit_id'],None)
    except Exception as e:
        attempt=int(unit.get('attempts') or 1); delay=BACKOFF[min(max(attempt-1,0),len(BACKOFF)-1)]
        status=mark_retry_or_failed(db_path,unit['unit_id'],error=e,next_attempt_at=time.time()+delay,max_attempts=max_attempts)
        return (status,unit['unit_id'],f'{type(e).__name__}: {e}')

def main():
    p=argparse.ArgumentParser(description='NEXA S4 unattended load runner.')
    p.add_argument('--run-id',required=True); p.add_argument('--workload',default=str(DEFAULT_WORKLOAD)); p.add_argument('--db',default=str(DEFAULT_DB)); p.add_argument('--workers',type=int,default=3); p.add_argument('--duration-hours',type=float,default=12.25); p.add_argument('--target-completed',type=int,default=1100); p.add_argument('--rate-per-hour',type=float,default=105.0); p.add_argument('--max-attempts',type=int,default=3); p.add_argument('--heartbeat-seconds',type=int,default=60); p.add_argument('--dry-run',action='store_true'); a=p.parse_args()
    units=load_units(a.workload)
    if len(units)<a.target_completed: raise SystemExit('Workload menor que target-completed.')
    ensure_schema(a.db); create_run(a.db,run_id=a.run_id,target_units=a.target_completed,duration_hours=a.duration_hours,workers=a.workers,rate_per_hour=a.rate_per_hour); seed_units(a.db,a.run_id,units); recovered=recover_stale_running(a.db,a.run_id)
    if a.dry_run:
        print('DRY RUN OK'); print('run_id:',a.run_id); print('units:',len(units)); print('workers:',a.workers); print('duration_hours:',a.duration_hours); print('target_completed:',a.target_completed); print('rate_per_hour:',a.rate_per_hour); print('recovered_running:',recovered); print('counts:',counts(a.db,a.run_id)); return
    proposed_start=utcnow()
    proposed_min_end=proposed_start+timedelta(hours=a.duration_hours)
    start_run(
        a.db,a.run_id,
        started_at=proposed_start.isoformat(),
        min_end_at=proposed_min_end.isoformat()
    )
    persisted_run=get_run(a.db,a.run_id)
    start=datetime.fromisoformat(persisted_run["started_at"])
    min_end=datetime.fromisoformat(persisted_run["min_end_at"])
    process_instance=str(uuid.uuid4())
    launch_interval=3600.0/a.rate_per_hour
    next_launch=time.monotonic()
    next_hb=time.monotonic()
    stopping=False
    def stop_handler(*_):
        nonlocal stopping; stopping=True
    signal.signal(signal.SIGINT,stop_handler)
    if hasattr(signal,'SIGTERM'): signal.signal(signal.SIGTERM,stop_handler)
    inflight={}; worker_counter=0
    print('S4 RUN START',a.run_id,start.isoformat(),'min_end',min_end.isoformat()); print('process_instance',process_instance)
    with ThreadPoolExecutor(max_workers=a.workers,thread_name_prefix='nexa-s4') as pool:
        while True:
            now_mono=time.monotonic(); now=utcnow()
            if now_mono>=next_hb:
                d=heartbeat(a.db,a.run_id,process_instance); print('HEARTBEAT',now.isoformat(),d,flush=True); next_hb=now_mono+a.heartbeat_seconds
            if inflight:
                done,_=wait(list(inflight),timeout=0,return_when=FIRST_COMPLETED)
                for fut in done:
                    wid=inflight.pop(fut)
                    try:
                        status,unit_id,error=fut.result(); print('UNIT',unit_id,status,(error or ''),flush=True)
                    except Exception as e: print('WORKER_FUTURE_ERROR',wid,type(e).__name__,str(e),flush=True)
            d=counts(a.db,a.run_id); target_met=d['completed']>=a.target_completed; duration_met=now>=min_end
            if stopping:
                finish_run(a.db,a.run_id,'stopped','Signal recibido; corrida reanudable.'); print('S4 RUN STOPPED; reanudar con el mismo --run-id.'); return
            if duration_met and target_met and not inflight:
                finish_run(a.db,a.run_id,'completed',f"Target {a.target_completed} y duración mínima cumplidos."); heartbeat(a.db,a.run_id,process_instance); print('S4 RUN COMPLETE',counts(a.db,a.run_id)); return
            if len(inflight)<a.workers and now_mono>=next_launch:
                worker_counter+=1; worker_id=f"{process_instance[:8]}-w{worker_counter%a.workers+1}"; unit=claim_unit(a.db,a.run_id,worker_id=worker_id,now_epoch=time.time())
                if unit:
                    inflight[pool.submit(process_unit,unit,a.db,a.max_attempts)]=worker_id; next_launch=now_mono+launch_interval
                else:
                    if d['pending']==0 and d['retry_wait']==0 and not inflight and not target_met:
                        finish_run(a.db,a.run_id,'target_not_met',f"Queue exhausted with {d['completed']} completed."); print('S4 TARGET NOT MET',d); raise SystemExit(2)
                    time.sleep(1.0)
            else: time.sleep(0.25)
if __name__=='__main__': main()
