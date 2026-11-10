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
        CREATE TABLE IF NOT EXISTS place_verifications (
            id INTEGER PRIMARY KEY,
            place_id INTEGER NOT NULL REFERENCES places(id),
            place_version INTEGER NOT NULL,
            result TEXT NOT NULL CHECK (result IN ('source_checked', 'needs_field_check')),
            evidence_url TEXT NOT NULL,
            note TEXT NOT NULL,
            checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS query_interests (
            community_id INTEGER PRIMARY KEY REFERENCES places(id),
            search_count INTEGER NOT NULL DEFAULT 0,
            last_searched_at TEXT
        );
    ''')
    return db


def latest_verifications(db):
    return {row['place_id']: row for row in db.execute('''
        SELECT v.* FROM place_verifications v
        JOIN (SELECT place_id, MAX(id) id FROM place_verifications GROUP BY place_id) last
        ON last.id = v.id
        JOIN places p ON p.id = v.place_id AND p.version = v.place_version
    ''')}


def ensure_verification_table(db):
    db.execute('''CREATE TABLE IF NOT EXISTS place_verifications (
        id INTEGER PRIMARY KEY,
        place_id INTEGER NOT NULL REFERENCES places(id),
        place_version INTEGER NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('source_checked', 'needs_field_check')),
        evidence_url TEXT NOT NULL,
        note TEXT NOT NULL,
        checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    db.commit()


def ensure_query_interest_table(db):
    db.execute('''CREATE TABLE IF NOT EXISTS query_interests (
        community_id INTEGER PRIMARY KEY REFERENCES places(id),
        search_count INTEGER NOT NULL DEFAULT 0,
        last_searched_at TEXT
    )''')
    db.commit()


def record_query_interest(db, community_id):
    """只累计主动查询的地点编号，不保存访问者身份。"""
    if db.execute("SELECT 1 FROM places WHERE id = ? AND kind = 'community'", (community_id,)).fetchone() is None:
        return False
    with db:
        db.execute('''INSERT INTO query_interests (community_id, search_count, last_searched_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(community_id) DO UPDATE SET
            search_count = search_count + 1, last_searched_at = CURRENT_TIMESTAMP''', (community_id,))
    return True


def priority_queue(db):
    """按搜索需求和仍未核验的周边设施，列出人工更新顺序。"""
    checks = latest_verifications(db)
    rows = []
    for community in db.execute("SELECT id, name FROM places WHERE kind = 'community'"):
        interest = db.execute('SELECT search_count FROM query_interests WHERE community_id = ?',
                              (community['id'],)).fetchone()
        searches = interest['search_count'] if interest else 0
        nearby = nearby_banks(db, community['id'], 3000)
        unverified = sum(place['id'] not in checks or checks[place['id']]['result'] != 'source_checked'
                         for place in nearby)
        rows.append({'name': community['name'], 'searches': searches,
                     'unverified': unverified, 'score': searches * 2 + unverified})
    return sorted(rows, key=lambda row: (-row['score'], row['name']))


def record_verification(db, place_id, result, evidence_url, note):
    from urllib.parse import urlsplit
    result = result.strip()
    evidence_url = evidence_url.strip()
    note = note.strip()
    parts = urlsplit(evidence_url)
    if result not in ('source_checked', 'needs_field_check'):
        raise ValueError('请选择有效的核验结果。')
    if (len(evidence_url) > 500 or parts.scheme != 'https' or not parts.hostname
            or parts.username or parts.password):
        raise ValueError('请填写不含账号信息的 HTTPS 证据链接。')
    if not note or len(note) > 300:
        raise ValueError('请填写 300 字以内的核验说明。')
    with db:
        place = db.execute('SELECT id, version FROM places WHERE id = ?', (place_id,)).fetchone()
        if place is None:
            raise ValueError('地点不存在。')
        db.execute('''INSERT INTO place_verifications
            (place_id, place_version, result, evidence_url, note)
            VALUES (?, ?, ?, ?, ?)''', (place_id, place['version'], result, evidence_url, note))


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


def nearby_communities(db, bank_id, radius_m):
    """按同一 WGS84 坐标系求银行或 ATM 周边的小区。"""
    if not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError('查询半径必须是正数')
    center = db.execute(
        "SELECT longitude, latitude FROM places WHERE id = ? AND kind IN ('bank', 'atm')",
        (bank_id,),
    ).fetchone()
    if center is None:
        raise ValueError('找不到对应银行或 ATM')
    matches = []
    for place in db.execute("SELECT * FROM places WHERE kind = 'community'"):
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
            if db.execute('SELECT 1 FROM places WHERE id = ?', (place_id,)).fetchone() is None:
                raise ValueError('地点不存在，未提交纠错。')
            raise ValueError('建议地址和当前地址相同，未生成待审核记录。请填写有改动的地址。')
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
