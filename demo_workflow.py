"""运行一次教学演示。全部地点为虚构测试数据，数据库随进程退出清除。"""
from contextlib import closing

from linjing_db import connect, nearby_banks, review_correction, submit_address_correction


def main():
    with closing(connect(':memory:')) as db:
        with db:
            db.executemany('''
                INSERT INTO places (id, kind, name, address, longitude, latitude, source)
                VALUES (?, ?, ?, ?, ?, ?, '虚构测试数据')
            ''', [
                (1, 'community', '示例小区', '示例路 1 号', 114.21, 22.68),
                (2, 'bank', '示例银行', '示例路 12 号', 114.213, 22.68),
                (3, 'atm', '示例 ATM', '示例路 8 号', 114.211, 22.68),
                (4, 'bank', '远处示例银行', '示例路 99 号', 114.24, 22.68),
            ])

        print('邻境业务演示 · 以下地点均为虚构测试数据')
        print('1. 查询示例小区 1000 米范围内的银行和 ATM')
        for place in nearby_banks(db, 1, 1000):
            print('   {name}：{address}，直线距离 {distance_m} 米'.format(**place))

        correction_id = submit_address_correction(db, 2, '示例路 16 号', '演示中模拟核验门牌号')
        pending = db.execute('SELECT status FROM corrections WHERE id = ?', (correction_id,)).fetchone()
        print('2. 提交地址纠错，状态为 {}（待审核），查询仍显示原地址'.format(pending['status']))
        before = next(place for place in nearby_banks(db, 1, 1000) if place['id'] == 2)
        print('   ' + before['address'])

        review_correction(db, correction_id, approve=True)
        after = next(place for place in nearby_banks(db, 1, 1000) if place['id'] == 2)
        print('3. 模拟审核通过，再次查询：{address}（版本 {version}）'.format(**after))
        audit = db.execute('SELECT * FROM corrections WHERE id = ?', (correction_id,)).fetchone()
        print('4. 审核记录：{} → {}'.format(audit['old_address'], audit['proposed_address']))


if __name__ == '__main__':
    main()
