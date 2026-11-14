"""本机采集任务：仅处理获准保存的 JSON 来源，不抓取地图候选。"""
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone

from import_places import import_dataset, validate_dataset


MAX_BYTES = 65536


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ensure_tables(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS collection_jobs (
            id INTEGER PRIMARY KEY,
            source_type TEXT NOT NULL CHECK(source_type IN ('upload','local_json')),
            source_path TEXT,
            interval_minutes INTEGER,
            status TEXT NOT NULL CHECK(status IN ('pending','running','success','failed')),
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            next_run_at TEXT,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            run_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS collection_candidates (
            id INTEGER PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES collection_jobs(id),
            source_url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            dataset_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','accepted','rejected')),
            created_at TEXT NOT NULL,
            reviewed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS collection_candidates_status ON collection_candidates(status);
    ''')


def create_file_job(db, source_path, interval_minutes=None):
    path = Path(source_path).resolve()
    if path.suffix.lower() != '.json':
        raise ValueError('采集来源必须是本机 JSON 文件。')
    if interval_minutes is not None and not 1 <= interval_minutes <= 10080:
        raise ValueError('采集间隔必须在 1 至 10080 分钟之间。')
    now = utc_now()
    with db:
        result = db.execute('''INSERT INTO collection_jobs
            (source_type,source_path,interval_minutes,status,created_at,next_run_at)
            VALUES ('local_json',?,?,?,?,?)''', (str(path), interval_minutes, 'pending', now, now))
    return result.lastrowid


def create_upload_job(db, dataset):
    now = utc_now()
    with db:
        result = db.execute('''INSERT INTO collection_jobs
            (source_type,status,created_at) VALUES ('upload','pending',?)''', (now,))
    run_job(db, result.lastrowid, dataset)
    return result.lastrowid


def _stage(db, job_id, dataset):
    metadata, rows = validate_dataset(dataset)
    source = metadata[0]
    originals = {item['source_id'].strip(): item for item in dataset['places']}
    count = 0
    for external_id, kind, name, address, longitude, latitude in rows:
        item = dict(originals[external_id])
        item.update(source_id=external_id, kind=kind, name=name, address=address,
                    longitude=longitude, latitude=latitude)
        one = dict(dataset, places=[item])
        payload = json.dumps(one, ensure_ascii=False, sort_keys=True)
        latest = db.execute('''SELECT id,dataset_json,status FROM collection_candidates
            WHERE source_url=? AND source_id=? ORDER BY id DESC LIMIT 1''',
            (source, external_id)).fetchone()
        if latest and latest['dataset_json'] == payload:
            continue
        if latest and latest['status'] == 'pending':
            if latest['dataset_json'] != payload:
                db.execute('UPDATE collection_candidates SET dataset_json=?,job_id=?,created_at=? WHERE id=?',
                           (payload, job_id, utc_now(), latest['id']))
                count += 1
            continue
        db.execute('''INSERT INTO collection_candidates
            (job_id,source_url,source_id,dataset_json,created_at) VALUES (?,?,?,?,?)''',
            (job_id, source, external_id, payload, utc_now()))
        count += 1
    return count


def run_job(db, job_id, dataset=None):
    job = db.execute('SELECT * FROM collection_jobs WHERE id=?', (job_id,)).fetchone()
    if job is None:
        raise ValueError('采集任务不存在。')
    if job['status'] == 'running':
        raise ValueError('采集任务正在执行。')
    with db:
        db.execute('''UPDATE collection_jobs SET status='running',started_at=?,finished_at=NULL,
            error=NULL,run_count=run_count+1 WHERE id=?''', (utc_now(), job_id))
    try:
        if job['source_type'] == 'local_json':
            path = Path(job['source_path'])
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('来源文件超过 64 KB。')
            dataset = json.loads(path.read_text(encoding='utf-8-sig'))
        elif dataset is None:
            raise ValueError('上传任务重试需重新提交文件。')
        if not isinstance(dataset, dict):
            raise ValueError('来源文件不是 JSON 对象。')
        with db:
            staged = _stage(db, job_id, dataset)
            next_run = (datetime.now(timezone.utc) + timedelta(minutes=job['interval_minutes'])).isoformat(timespec='seconds') if job['interval_minutes'] else None
            db.execute('''UPDATE collection_jobs SET status='success',finished_at=?,candidate_count=?,
                next_run_at=? WHERE id=?''', (utc_now(), staged, next_run, job_id))
        return staged
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as error:
        with db:
            db.execute('''UPDATE collection_jobs SET status='failed',finished_at=?,error=?,
                next_run_at=NULL WHERE id=?''', (utc_now(), str(error)[:240], job_id))
        return None


def run_due_jobs(db):
    """只在进程运行时触发；重启后到期的任务执行一次，不逐次补跑。"""
    due = db.execute('''SELECT id FROM collection_jobs WHERE source_type='local_json'
        AND next_run_at IS NOT NULL AND next_run_at<=? AND status IN ('pending','success')
        ORDER BY id''', (utc_now(),)).fetchall()
    for job in due:
        run_job(db, job['id'])


def review_candidate(db, candidate_id, accept):
    candidate = db.execute('SELECT * FROM collection_candidates WHERE id=?', (candidate_id,)).fetchone()
    if candidate is None or candidate['status'] != 'pending':
        raise ValueError('候选不存在或已经审核。')
    dataset = json.loads(candidate['dataset_json'])
    if accept:
        metadata, rows = validate_dataset(dataset)
        # 来源许可需要审核者在页面确认；程序不能仅凭 URL 自动判定授权。
        import_dataset(db, metadata, rows)
    with db:
        db.execute('''UPDATE collection_candidates SET status=?,reviewed_at=?
            WHERE id=? AND status='pending' ''', ('accepted' if accept else 'rejected', utc_now(), candidate_id))
