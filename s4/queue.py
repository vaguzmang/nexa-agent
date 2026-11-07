from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def ensure_schema(path):
    with closing(connect(path)) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS s4_runs(
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            started_at TEXT,
            min_end_at TEXT,
            finished_at TEXT,
            status TEXT NOT NULL,
            target_units INTEGER NOT NULL,
            duration_hours REAL NOT NULL,
            workers INTEGER NOT NULL,
            rate_per_hour REAL NOT NULL,
            last_heartbeat TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS s4_units(
            unit_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            source_id TEXT,
            source_question INTEGER,
            mode TEXT NOT NULL,
            student_id TEXT NOT NULL,
            activity TEXT,
            message TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            worker_id TEXT,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            next_attempt_at REAL NOT NULL DEFAULT 0,
            task_id TEXT,
            total_tokens INTEGER,
            latency_ms INTEGER,
            llm_calls INTEGER,
            tool_calls INTEGER,
            error_type TEXT,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_s4_units_run_status
        ON s4_units(run_id,status,next_attempt_at,sequence_no);
        CREATE TABLE IF NOT EXISTS s4_heartbeats(
            heartbeat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            completed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            pending INTEGER NOT NULL,
            retry_wait INTEGER NOT NULL,
            in_flight INTEGER NOT NULL,
            process_instance TEXT NOT NULL
        );
        ''')
        c.commit()


def create_run(path, *, run_id, target_units, duration_hours, workers, rate_per_hour):
    ensure_schema(path)
    with closing(connect(path)) as c:
        c.execute('''INSERT OR IGNORE INTO s4_runs(
            run_id,created_at,status,target_units,duration_hours,workers,rate_per_hour
        ) VALUES (?,?,?,?,?,?,?)''',
        (run_id, utcnow(), 'prepared', target_units, duration_hours, workers, rate_per_hour))
        c.commit()


def seed_units(path, run_id, units):
    ensure_schema(path)
    with closing(connect(path)) as c:
        for u in units:
            c.execute('''INSERT OR IGNORE INTO s4_units(
                unit_id,run_id,sequence_no,status,source_id,source_question,mode,
                student_id,activity,message,queued_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                u['unit_id'], run_id, int(u['sequence_no']), 'pending', u.get('source_id'),
                u.get('source_question'), u['mode'], u['student_id'], u.get('activity'),
                u['message'], utcnow()))
        c.commit()


def recover_stale_running(path, run_id):
    with closing(connect(path)) as c:
        c.execute('''UPDATE s4_units SET status='retry_wait',worker_id=NULL,next_attempt_at=0,
                     error_type='recovered_running',error_message='Recovered automatically after runner restart.'
                     WHERE run_id=? AND status='running' ''', (run_id,))
        n = c.total_changes
        c.commit()
    return n


def claim_unit(path, run_id, *, worker_id, now_epoch):
    with closing(connect(path)) as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('''SELECT * FROM s4_units
                           WHERE run_id=? AND (status='pending' OR (status='retry_wait' AND next_attempt_at<=?))
                           ORDER BY sequence_no LIMIT 1''', (run_id, now_epoch)).fetchone()
        if not row:
            c.rollback()
            return None
        c.execute('''UPDATE s4_units SET status='running',worker_id=?,started_at=?,attempts=attempts+1
                     WHERE unit_id=? AND status IN ('pending','retry_wait')''',
                  (worker_id, utcnow(), row['unit_id']))
        c.commit()
        data = dict(row)
        data['attempts'] = int(data['attempts']) + 1
        data['worker_id'] = worker_id
        return data


def mark_completed(path, unit_id, *, task_id, metrics):
    with closing(connect(path)) as c:
        c.execute('''UPDATE s4_units SET status='completed',finished_at=?,task_id=?,
                     total_tokens=?,latency_ms=?,llm_calls=?,tool_calls=?,error_type=NULL,error_message=NULL
                     WHERE unit_id=?''',
                  (utcnow(), task_id, metrics.get('total_tokens'), metrics.get('total_latency_ms'),
                   metrics.get('llm_calls'), metrics.get('tool_calls'), unit_id))
        c.commit()


def mark_retry_or_failed(path, unit_id, *, error, next_attempt_at, max_attempts):
    with closing(connect(path)) as c:
        row = c.execute('SELECT attempts FROM s4_units WHERE unit_id=?', (unit_id,)).fetchone()
        attempts = int(row['attempts']) if row else max_attempts
        status = 'dead_letter' if attempts >= max_attempts else 'retry_wait'
        c.execute('''UPDATE s4_units SET status=?,finished_at=?,worker_id=NULL,next_attempt_at=?,
                     error_type=?,error_message=? WHERE unit_id=?''',
                  (status, utcnow(), float(next_attempt_at), type(error).__name__, str(error)[:1000], unit_id))
        c.commit()
    return status


def counts(path, run_id):
    with closing(connect(path)) as c:
        rows = c.execute('SELECT status,COUNT(*) n FROM s4_units WHERE run_id=? GROUP BY status', (run_id,)).fetchall()
    d = {r['status']: int(r['n']) for r in rows}
    for k in ('pending','running','retry_wait','completed','dead_letter'):
        d.setdefault(k, 0)
    return d


def heartbeat(path, run_id, process_instance):
    d = counts(path, run_id)
    with closing(connect(path)) as c:
        c.execute('''INSERT INTO s4_heartbeats(
            run_id,recorded_at,completed,failed,pending,retry_wait,in_flight,process_instance
        ) VALUES (?,?,?,?,?,?,?,?)''',
        (run_id, utcnow(), d['completed'], d['dead_letter'], d['pending'], d['retry_wait'], d['running'], process_instance))
        c.execute('UPDATE s4_runs SET last_heartbeat=? WHERE run_id=?', (utcnow(), run_id))
        c.commit()
    return d


def start_run(path, run_id, *, started_at, min_end_at):
    with closing(connect(path)) as c:
        c.execute('''UPDATE s4_runs SET status='running',started_at=COALESCE(started_at,?),
                     min_end_at=COALESCE(min_end_at,?) WHERE run_id=?''',
                  (started_at, min_end_at, run_id))
        c.commit()


def finish_run(path, run_id, status, note=None):
    with closing(connect(path)) as c:
        c.execute('UPDATE s4_runs SET status=?,finished_at=?,note=? WHERE run_id=?',
                  (status, utcnow(), note, run_id))
        c.commit()


def get_run(path, run_id):
    with closing(connect(path)) as c:
        r = c.execute('SELECT * FROM s4_runs WHERE run_id=?', (run_id,)).fetchone()
    return dict(r) if r else None
