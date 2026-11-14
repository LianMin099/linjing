"""在临时数据库验证本机来源任务、候选审核及增量更新。"""
from contextlib import closing
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import time
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
import re

from collection_jobs import create_file_job, ensure_tables, review_candidate, run_due_jobs, run_job
from import_places import import_dataset, validate_dataset
from linjing_db import connect, review_correction, submit_address_correction


def main():
    sample = json.loads((Path(__file__).parent / 'samples/pilot_osm.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='linjing-collection-') as directory:
        folder = Path(directory)
        source = folder / 'source.json'
        source.write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')
        with closing(connect(str(folder / 'check.sqlite'))) as db:
            ensure_tables(db)
            job_id = create_file_job(db, source, 1)
            run_due_jobs(db)
            job = db.execute('SELECT * FROM collection_jobs WHERE id=?', (job_id,)).fetchone()
            assert job['status'] == 'success' and job['candidate_count'] == 9
            assert db.execute('SELECT COUNT(*) FROM places').fetchone()[0] == 0
            candidate = db.execute('''SELECT * FROM collection_candidates
                WHERE source_id='way/1170469872:srcb-longcheng-building-area' ''').fetchone()
            review_candidate(db, candidate['id'], True)
            bank = db.execute("SELECT * FROM places WHERE kind='bank'").fetchone()
            assert bank['version'] == 1
            sample['places'][4]['name'] += '（临时验证）'
            sample['places'][4]['address'] += '（来源更新）'
            source.write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')
            assert run_job(db, job_id) == 1
            candidate = db.execute('''SELECT id FROM collection_candidates WHERE source_id=?
                AND status='pending' ORDER BY id DESC LIMIT 1''', (sample['places'][4]['source_id'],)).fetchone()
            review_candidate(db, candidate['id'], True)
            bank = db.execute('SELECT * FROM places WHERE id=?', (bank['id'],)).fetchone()
            assert bank['version'] == 2 and bank['name'].endswith('（临时验证）')
            assert db.execute('SELECT changed_fields FROM place_changes WHERE place_id=?',
                              (bank['id'],)).fetchone()[0] == 'name, address'
            correction_id = submit_address_correction(db, bank['id'], '人工审核地址（临时验证）', '测试人工修订优先')
            review_correction(db, correction_id, True)
            sample['places'][4]['name'] += '2'
            sample['places'][4]['address'] += '再次变化'
            source.write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')
            assert run_job(db, job_id) == 1
            candidate = db.execute('''SELECT id FROM collection_candidates WHERE source_id=?
                AND status='pending' ORDER BY id DESC LIMIT 1''', (sample['places'][4]['source_id'],)).fetchone()
            review_candidate(db, candidate['id'], True)
            bank = db.execute('SELECT * FROM places WHERE id=?', (bank['id'],)).fetchone()
            assert bank['version'] == 4 and bank['address'] == '人工审核地址（临时验证）'
            source.unlink()
            assert run_job(db, job_id) is None
            failed = db.execute('SELECT status,error FROM collection_jobs WHERE id=?', (job_id,)).fetchone()
            assert failed['status'] == 'failed' and failed['error']
            source.write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')
            assert run_job(db, job_id) == 0
            assert db.execute('SELECT status FROM collection_jobs WHERE id=?', (job_id,)).fetchone()[0] == 'success'
        environment = os.environ.copy()
        environment['PYTHONIOENCODING'] = 'utf-8'
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).parent / 'run_pilot.py'),
                                    '--db', str(folder / 'server.sqlite'), '--collection-file', str(source),
                                    '--collection-interval-minutes', '1'], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=environment)
        try:
            lines = [process.stdout.readline().strip() for _ in range(3)]
            if not all(lines):
                raise AssertionError('本机服务未能启动')
            url = next(line.split('：', 1)[1] for line in lines if line.startswith('邻境本机演示：'))
            code = next(line.split('：', 1)[1] for line in lines if line.startswith('本次管理员口令：'))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with closing(connect(str(folder / 'server.sqlite'))) as check:
                    result = check.execute('''SELECT status,candidate_count FROM collection_jobs
                        ORDER BY id DESC LIMIT 1''').fetchone()
                    if result and result['status'] == 'success':
                        assert result['candidate_count'] == 9
                        break
                time.sleep(.1)
            else:
                raise AssertionError('服务运行时未触发到期任务')
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            with opener.open(url + '/', timeout=5) as response:
                html = response.read().decode('utf-8')
            token = re.search(r'name="token" value="([^"]+)"', html).group(1)
            body = urlencode({'token': token, 'radius': 3000, 'community': '', 'kind': 'all',
                              'code': code}).encode('utf-8')
            opener.open(Request(url + '/login', data=body), timeout=5).close()
            with opener.open(url + '/', timeout=5) as response:
                admin_html = response.read().decode('utf-8')
            assert '采集任务与候选审核' in admin_html and '待审核候选' in admin_html
            body = urlencode({'token': token, 'radius': 3000, 'community': '', 'kind': 'all',
                              'dataset': json.dumps(sample, ensure_ascii=False)}).encode('utf-8')
            with opener.open(Request(url + '/import', data=body), timeout=5) as response:
                assert '待审核候选' in response.read().decode('utf-8')
            with closing(connect(str(folder / 'server.sqlite'))) as check:
                candidate_id = check.execute('''SELECT id FROM collection_candidates
                    WHERE status='pending' ORDER BY id LIMIT 1''').fetchone()[0]
            body = urlencode({'token': token, 'radius': 3000, 'community': '', 'kind': 'all',
                              'candidate_id': candidate_id, 'permission_confirmed': 'yes',
                              'decision': 'accept'}).encode('utf-8')
            opener.open(Request(url + '/candidate', data=body), timeout=5).close()
            with closing(connect(str(folder / 'server.sqlite'))) as check:
                assert check.execute('SELECT status FROM collection_candidates WHERE id=?',
                                     (candidate_id,)).fetchone()[0] == 'accepted'
        finally:
            process.terminate()
            process.wait(timeout=5)
    print('通过：定时触发、候选暂存、审核入库、增量版本、人工地址保护、失败原因与重试。')
    print('验证使用临时文件中的模拟变更，不代表真实数据源许可或地点真实性。')


if __name__ == '__main__':
    main()
