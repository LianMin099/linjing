"""邻境的数据存储与纠错逻辑，使用 Python 自带的 SQLite。"""
import math
import sqlite3


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('community', 'bank', 'atm')),
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
            latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
            source TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY,
            place_id INTEGER NOT NULL REFERENCES places(id),
            base_version INTEGER NOT NULL,
            old_address TEXT NOT NULL,
            proposed_address TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected')),
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );
    ''')
    return db


def distance_m(first, second):
    """输入使用同一坐标系，计算球面直线距离，单位为米。"""
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(min(1, a)))


def nearby_banks(db, community_id, radius_m):
    if not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError('查询半径必须是正数')
    center = db.execute(
        "SELECT longitude, latitude FROM places WHERE id = ? AND kind = 'community'",
        (community_id,),
    ).fetchone()
    if center is None:
        raise ValueError('找不到对应小区')
    matches = []
    for place in db.execute("SELECT * FROM places WHERE kind IN ('bank', 'atm')"):
        distance = distance_m(center, (place['longitude'], place['latitude']))
        if distance <= radius_m:
            matches.append(dict(place, distance_m=round(distance, 1)))
    return sorted(matches, key=lambda place: (place['distance_m'], place['id']))


def submit_address_correction(db, place_id, new_address, reason):
    address, reason = new_address.strip(), reason.strip()
    if not address or not reason:
        raise ValueError('请填写新地址和纠错依据')
    with db:
        result = db.execute('''
            INSERT INTO corrections (place_id, base_version, old_address, proposed_address, reason)
            SELECT id, version, address, ?, ? FROM places WHERE id = ? AND address <> ?
        ''', (address, reason, place_id, address))
        if result.rowcount != 1:
            raise ValueError('地点不存在或地址没有变化')
        return result.lastrowid


def review_correction(db, correction_id, approve):
    """审核与地点更新在同一事务内完成。旧版本反馈不能覆盖较新的修改。"""
    with db:
        status = 'approved' if approve else 'rejected'
        reviewed = db.execute('''
            UPDATE corrections SET status = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
        ''', (status, correction_id))
        if reviewed.rowcount != 1:
            raise ValueError('反馈不存在或已审核')
        if approve:
            correction = db.execute('SELECT * FROM corrections WHERE id = ?', (correction_id,)).fetchone()
            updated = db.execute('''
                UPDATE places SET address = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?
            ''', (correction['proposed_address'], correction['place_id'], correction['base_version']))
            if updated.rowcount != 1:
                raise ValueError('地点已更新，请核对最新信息后重新提交')
