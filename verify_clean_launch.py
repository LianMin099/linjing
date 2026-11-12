"""在临时目录验证源码启动、查询、纠错审核与重启保存。"""
from http.cookiejar import CookieJar
from pathlib import Path
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


FILES = ('run_pilot.py', 'demo_web.py', 'demo_workflow.py', 'import_places.py',
         'linjing_db.py', 'live_map.py', 'map_config.py', 'ui_assets.py',
         'samples/pilot_osm.json')


def start(folder):
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'utf-8'
    process = subprocess.Popen(
        [sys.executable, '-B', 'run_pilot.py', '--db', 'data/check.sqlite'],
        cwd=str(folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, encoding='utf-8', bufsize=1, env=environment)
    try:
        lines = [process.stdout.readline().strip() for _ in range(3)]
        url = next((line.rsplit('：', 1)[-1] for line in lines if line.startswith('邻境本机演示：')), '')
        code = next((line.rsplit('：', 1)[-1] for line in lines if line.startswith('本次管理员口令：')), '')
        if not url or not code:
            raise RuntimeError('启动失败；输出：' + repr(lines))
        return process, url, code, lines[0]
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        raise


def post(opener, url, path, fields):
    body = urlencode(fields).encode('utf-8')
    with opener.open(Request(url + path, data=body), timeout=5) as response:
        return response.read().decode('utf-8')


def main():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='linjing-clean-') as temporary:
        folder = Path(temporary)
        for name in FILES:
            destination = folder / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(root / name), str(destination))
        process = None
        try:
            process, url, code, first_line = start(folder)
            assert first_line == 'Samples: 9 added, 0 already present.', first_line
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            with opener.open(url + '/', timeout=5) as response:
                html = response.read().decode('utf-8')
            assert '当前结果 · 3 处' in html and '深圳农村商业银行龙城支行' in html
            assert '查已入库地点' in html
            assert '试点库现有 6 个小区、2 家银行、1 台 ATM；尚未覆盖周边全部地点' in html
            token = re.search(r'name="token" value="([^"]+)"', html).group(1)
            db = sqlite3.connect(str(folder / 'data/check.sqlite'))
            assert db.execute("SELECT kind, COUNT(*) FROM places GROUP BY kind ORDER BY kind").fetchall() == [
                ('atm', 1), ('bank', 2), ('community', 6)]
            bank_id = db.execute("SELECT id FROM places WHERE name = '深圳农村商业银行龙城支行'").fetchone()[0]
            community_id = db.execute("SELECT id FROM places WHERE kind = 'community' ORDER BY id LIMIT 1").fetchone()[0]
            huangge_id = db.execute("SELECT id FROM places WHERE name = '黄阁翠苑'").fetchone()[0]
            original = db.execute('SELECT address FROM places WHERE id = ?', (bank_id,)).fetchone()[0]
            proposed = original + '（临时验证，不作为真实地址）'
            db.close()
            with opener.open(url + '/?community={}&radius=3000&kind=all'.format(community_id), timeout=5) as response:
                assert '当前结果 · 3 处' in response.read().decode('utf-8')
            with opener.open(url + '/?community={}&radius=3000&kind=all'.format(huangge_id), timeout=5) as response:
                assert '当前结果 · 3 处' in response.read().decode('utf-8')
            with opener.open(url + '/?community={}&radius=1000&kind=all'.format(huangge_id), timeout=5) as response:
                assert '当前结果 · 0 处' in response.read().decode('utf-8')
            db = sqlite3.connect(str(folder / 'data/check.sqlite'))
            assert db.execute('SELECT search_count FROM query_interests WHERE community_id = ?',
                              (community_id,)).fetchone()[0] == 1
            db.close()
            post(opener, url, '/correction', {'token': token, 'radius': 3000,
                 'community': '', 'kind': 'all', 'place_id': bank_id,
                 'address': proposed, 'reason': '独立目录流程验证'})
            db = sqlite3.connect(str(folder / 'data/check.sqlite'))
            assert db.execute('SELECT address FROM places WHERE id = ?', (bank_id,)).fetchone()[0] == original
            correction_id = db.execute('SELECT id FROM corrections ORDER BY id DESC LIMIT 1').fetchone()[0]
            db.close()
            post(opener, url, '/login', {'token': token, 'radius': 3000,
                 'community': '', 'kind': 'all', 'code': code})
            with opener.open(url + '/', timeout=5) as response:
                assert '优先核验队列' in response.read().decode('utf-8')
            reviewed = post(opener, url, '/review', {'token': token, 'radius': 3000,
                 'community': '', 'kind': 'all', 'id': correction_id, 'decision': 'approve'})
            assert proposed in reviewed and '已通过' in reviewed
            process.terminate()
            process.wait(timeout=5)
            process = None
            process, url, code, first_line = start(folder)
            assert first_line == 'Samples: 0 added, 9 already present.', first_line
            db = sqlite3.connect(str(folder / 'data/check.sqlite'))
            assert db.execute('SELECT address, version FROM places WHERE id = ?', (bank_id,)).fetchone() == (proposed, 2)
            db.close()
            print('通过：独立目录启动、9 条导入、查询、待审核不改址、管理员审核、重启保留修订。')
            print('所有测试数据位于自动清理的临时目录；未使用本机试玩数据库或地图密钥。')
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
