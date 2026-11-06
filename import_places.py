"""校验有明确使用依据的地点数据，按需导入 SQLite。"""
import argparse
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from linjing_db import connect, distance_m


def required_text(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('缺少有效字段 {}'.format(field))
    return value.strip()


def source_link(record, field):
    url = required_text(record, field)
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username is not None:
        raise ValueError('{} 需要不含账号凭证的 HTTPS 链接'.format(field))
    return url


def coordinates(record):
    result = []
    for field, limit in (('longitude', 180), ('latitude', 90)):
        value = record.get(field)
        if type(value) not in (int, float) or not -limit <= value <= limit or not math.isfinite(value):
            raise ValueError('{} 坐标无效'.format(field))
        result.append(value)
    return tuple(result)


def validate_dataset(dataset):
    if not isinstance(dataset, dict) or dataset.get('coordinate_system') != 'WGS84':
        raise ValueError('请提供标为 WGS84 的地点数据，学校和各地点必须使用同一坐标系')
    source = source_link(dataset, 'source_url')
    permission = source_link(dataset, 'permission_url')
    school = dataset.get('school')
    if not isinstance(school, dict):
        raise ValueError('缺少学校坐标及其来源')
    school_source = source_link(school, 'source_url')
    school_permission = source_link(school, 'permission_url')
    center = coordinates(school)
    places = dataset.get('places')
    if not isinstance(places, list) or not places:
        raise ValueError('places 必须是非空地点列表')
    rows = []
    seen = set()
    for index, place in enumerate(places, 1):
        try:
            if not isinstance(place, dict):
                raise ValueError('需要地点对象')
            external_id = required_text(place, 'source_id')
            kind = required_text(place, 'kind')
            if kind not in ('bank', 'atm', 'community'):
                raise ValueError('kind 必须是 bank、atm 或 community')
            name = required_text(place, 'name')
            address = required_text(place, 'address')
            point = coordinates(place)
            if distance_m(center, point) > 3000:
                raise ValueError('超过学校周边 3 公里')
            if external_id in seen:
                raise ValueError('来源编号重复')
            seen.add(external_id)
            rows.append((external_id, kind, name, address, *point))
        except ValueError as error:
            raise ValueError('第 {} 条：{}'.format(index, error)) from error
    return (source, permission, school_source, school_permission, *center), rows


def import_dataset(db, metadata, rows):
    """同一来源编号只导入一次，已有地点交由纠错流程修改。"""
    source, permission, school_source, school_permission, school_lon, school_lat = metadata
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''
            CREATE TABLE IF NOT EXISTS place_imports (
                source_url TEXT NOT NULL,
                source_id TEXT NOT NULL,
                place_id INTEGER NOT NULL UNIQUE REFERENCES places(id),
                permission_url TEXT NOT NULL,
                coordinate_system TEXT NOT NULL,
                school_source_url TEXT NOT NULL,
                school_permission_url TEXT NOT NULL,
                school_longitude REAL NOT NULL,
                school_latitude REAL NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_url, source_id)
            )
        ''')
        added = 0
        for external_id, kind, name, address, longitude, latitude in rows:
            if db.execute('SELECT 1 FROM place_imports WHERE source_url = ? AND source_id = ?',
                          (source, external_id)).fetchone():
                continue
            record = db.execute('''
                INSERT INTO places (kind, name, address, longitude, latitude, source)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (kind, name, address, longitude, latitude, source))
            db.execute('''
                INSERT INTO place_imports (source_url, source_id, place_id, permission_url, coordinate_system,
                    school_source_url, school_permission_url, school_longitude, school_latitude)
                VALUES (?, ?, ?, ?, 'WGS84', ?, ?, ?, ?)
            ''', (source, external_id, record.lastrowid, permission, school_source, school_permission, school_lon, school_lat))
            added += 1
    return added


def main():
    parser = argparse.ArgumentParser(description='校验地点 JSON。只有指定 --db 才会写入 SQLite。')
    parser.add_argument('input', type=Path)
    parser.add_argument('--db', type=Path)
    args = parser.parse_args()
    try:
        metadata, rows = validate_dataset(json.loads(args.input.read_text(encoding='utf-8-sig')))
        print('通过字段、坐标及试点范围检查：{} 条。'.format(len(rows)))
        if args.db is not None:
            with closing(connect(str(args.db))) as db:
                added = import_dataset(db, metadata, rows)
            print('新增 {} 条，跳过已有 {} 条。'.format(added, len(rows) - added))
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, '处理失败：{}\n'.format(error))


if __name__ == '__main__':
    main()
