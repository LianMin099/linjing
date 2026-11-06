"""第一课：用少量实际请求检查候选数据源；不保存 Key 或原始地点数据。

仅使用 Python 标准库。离线检查：python probe_amap.py --self-test
"""
import argparse
import getpass
import json
import math
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = 'https://restapi.amap.com/v5/place/'
CHINA_TIME = timezone(timedelta(hours=8))


class ProbeError(Exception):
    pass


def request_api(endpoint, params, key):
    """Key 仅用于 HTTPS 请求；不打印 URL 或底层异常，避免泄露凭证。"""
    query = dict(params)
    query['key'] = key
    url = BASE + endpoint + '?' + urlencode(query)
    try:
        with urlopen(url, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise ProbeError('HTTP 错误：{}'.format(exc.code)) from None
    except (URLError, socket.timeout, TimeoutError, OSError):
        raise ProbeError('网络连接失败或超时，请检查网络后重新运行。') from None
    except (ValueError, UnicodeError):
        raise ProbeError('服务返回的内容不是有效 JSON。') from None
    if not isinstance(data, dict):
        raise ProbeError('服务返回结构异常。')
    if str(data.get('status')) != '1':
        # 只展示有限长度错误码，不保存可能包含请求信息的原始错误响应。
        code = str(data.get('infocode', 'UNKNOWN'))[:20]
        code = ''.join(c for c in code if c.isalnum() or c == '_')
        raise ProbeError('服务未成功，错误码：{}。请核对 Key 类型和账号权限。'.format(code))
    pois = data.get('pois')
    if not isinstance(pois, list) or any(not isinstance(p, dict) for p in pois):
        raise ProbeError('服务缺少有效地点列表。')
    return pois


def valid_location(value):
    try:
        lng, lat = [float(part) for part in value.split(',')]
        return math.isfinite(lng) and math.isfinite(lat) and -180 <= lng <= 180 and -90 <= lat <= 90
    except (AttributeError, TypeError, ValueError):
        return False


def present(value):
    return value is not None and value != '' and value != [] and value != {}


def summarize(pois):
    """统计字段可得性，不能将字段存在误称为内容准确。"""
    counts = {name: 0 for name in ('名称', '地址', '有效坐标', '电话', '今日营业时间')}
    for poi in pois:
        business = poi.get('business')
        if not isinstance(business, dict):
            business = {}
        counts['名称'] += int(present(poi.get('name')))
        counts['地址'] += int(present(poi.get('address')))
        counts['有效坐标'] += int(valid_location(poi.get('location')))
        counts['电话'] += int(present(business.get('tel')))
        counts['今日营业时间'] += int(present(business.get('opentime_today')))
    return {'sample_size': len(pois), 'fields': counts}


def choose_school(pois):
    if not pois:
        raise ProbeError('没有学校候选结果，需检查学校关键词或服务权限。')
    print('\n请核对学校主体：深圳市龙岗区龙翔大道 2188 号。')
    for index, poi in enumerate(pois, 1):
        print('{}：{} | {} | {}'.format(index, poi.get('name', ''), poi.get('address', ''), poi.get('location', '')))
    print('仅有校门、商铺或地址不符时，请输入 0 退出。')
    while True:
        answer = input('学校主体对应序号（0 退出）：').strip()
        if answer == '0':
            raise ProbeError('用户未确认学校主体，未继续查询。')
        if answer.isdigit() and 1 <= int(answer) <= len(pois):
            school = pois[int(answer) - 1]
            if not valid_location(school.get('location')):
                print('该候选没有有效坐标，请重新选择。')
                continue
            return school['location']
        print('请输入列表中的序号。')


def save_report(results):
    now = datetime.now(CHINA_TIME)
    lines = ['# 候选数据源验证报告', '', '执行时间：' + now.isoformat(timespec='seconds'),
             '', '计划范围：学校主体点周边 3000 米；定位成功并经用户确认后才进行周边查询，每类第一页最多 10 条。',
             '这是接口与字段验证，不是全部地点覆盖证明，也不是数据存储授权证明。',
             '未保存 Key、原始地点列表、请求 URL。', '']
    for name, result in results:
        lines.extend(['## ' + name, ''])
        if isinstance(result, str):
            lines.extend(['状态：未通过。' + result, ''])
            continue
        size = result['sample_size']
        lines.extend(['状态：请求成功；返回样本 {} 条。'.format(size), '', '| 字段 | 有效数量 | 样本覆盖率 |', '| --- | --- | --- |'])
        for field, count in result['fields'].items():
            rate = '{:.0%}'.format(count / size) if size else '不适用'
            lines.append('| {} | {} | {} |'.format(field, count, rate))
        lines.append('')
    lines.extend(['## 未完成的验证', '', '- 尚未人工核对地点真实性、类别准确性或位置偏差。',
                  '- 小区建成年代、住宅均价、物业费来源尚未落实。',
                  '- 自动采集、持久化和再次展示的使用权限仍需确认。',
                  '- 还未完成自动更新、数据库、网站和业务闭环。', ''])
    folder = Path(__file__).resolve().parent / 'reports'
    folder.mkdir(exist_ok=True)
    target = folder / ('验证报告_' + now.strftime('%Y%m%d_%H%M%S_%f') + '.md')
    target.write_text('\n'.join(lines), encoding='utf-8')
    print('\n报告已保存：' + str(target))


def self_test():
    # 以下仅为内存中的测试夹具，不写入真实验证报告。
    assert valid_location('114.0,22.0')
    assert not valid_location('nan,22')
    assert not valid_location('114,91')
    assert not valid_location(None)
    assert summarize([])['sample_size'] == 0
    result = summarize([{'name': 'TEST_ONLY', 'address': [], 'location': '114,22', 'business': {'tel': 'TEST_ONLY'}}, {'business': []}])
    assert result['fields'] == {'名称': 1, '地址': 0, '有效坐标': 1, '电话': 1, '今日营业时间': 0}
    print('离线检查通过：缺失值、坐标有效性、字段统计。未调用真实 API。')


def main():
    parser = argparse.ArgumentParser(description='邻境：候选数据源验证')
    parser.add_argument('--self-test', action='store_true', help='离线自检，不访问网络')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    print('邻境 · 第一课：真实接口验证')
    print('需使用你自己的高德 Web 服务 Key；最多 3 次请求，不自动重试。')
    print('请先阅读 README.md，并确认账号服务权限和调用费用。')
    if not sys.stdin.isatty():
        print('请通过“开始验证.cmd”在本地交互窗口中输入 Key。')
        return 1
    key = getpass.getpass('粘贴 Key 后按回车（输入不显示、不保存）：').strip()
    if not key:
        print('未输入 Key，已退出。')
        return 1
    results = []
    try:
        print('正在搜索学校……')
        schools = request_api('text', {'keywords': '深圳信息职业技术', 'region': '440307', 'city_limit': 'true', 'page_size': 10}, key)
        location = choose_school(schools)
    except ProbeError as exc:
        results.append(('学校定位', str(exc)))
        print(str(exc))
        save_report(results)
        return 1
    all_ok = True
    for name, keyword in [('银行', '银行'), ('小区', '住宅小区')]:
        print('正在查询周边{}……'.format(name))
        try:
            pois = request_api('around', {'location': location, 'radius': 3000, 'keywords': keyword,
                                         'page_size': 10, 'page_num': 1, 'show_fields': 'business', 'sortrule': 'distance'}, key)
            summary = summarize(pois)
            results.append((name, summary))
            print('请求成功，样本 {} 条；类别和真实性仍待人工核验。'.format(len(pois)))
        except ProbeError as exc:
            all_ok = False
            results.append((name, str(exc)))
            print(str(exc))
    save_report(results)
    return 0 if all_ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\n已取消。Key 未写入文件。')
        sys.exit(1)
