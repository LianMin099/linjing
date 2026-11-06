"""本机网页演示。所有地点、审核和数据库都只用于教学。"""
import argparse
from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
from socketserver import TCPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser

from demo_workflow import seed_demo
from linjing_db import connect, nearby_banks, review_correction, submit_address_correction


RADII = (100, 300, 1000, 3000)
STATUS = {'pending': '待审核', 'approved': '已通过', 'rejected': '已驳回'}
NOTICES = {'submitted': '建议已提交。审核通过前，查询仍显示原地址。',
           'approved': '审核通过。查询结果已更新，旧地址仍保留在审核记录中。',
           'rejected': '建议已驳回。查询结果继续显示原地址。'}


def page(db, token, radius, searched, notice=''):
    hidden = f'<input type="hidden" name="token" value="{token}">' + (
        f'<input type="hidden" name="radius" value="{radius}">')
    options = ''.join(f'<option value="{r}"{" selected" if r == radius else ""}>{r} 米</option>' for r in RADII)
    results = '<p>选择距离后点击「查附近」，查看示例小区附近的银行和 ATM。</p>'
    if searched:
        rows = nearby_banks(db, 1, radius)
        results = ''.join(
            f'<li><strong>{escape(row["name"])}</strong><span>{escape(row["address"])}</span>'
            f'<small>直线距离 {row["distance_m"]} 米 · 版本 {row["version"]}</small></li>' for row in rows
        )
        results = f'<ul>{results}</ul>' if results else '<p>这个范围内没有示例银行或 ATM。</p>'

    records = []
    for row in db.execute('SELECT * FROM corrections ORDER BY id DESC'):
        buttons = ''
        if row['status'] == 'pending':
            buttons = (f'<form method="post" action="/review">{hidden}'
                       f'<input type="hidden" name="id" value="{row["id"]}">'
                       '<button name="decision" value="approve">审核通过</button> '
                       '<button class="secondary" name="decision" value="reject">驳回</button></form>')
        records.append(f'<li><strong>{STATUS[row["status"]]}</strong>'
                       f'<span>{escape(row["old_address"])} → {escape(row["proposed_address"])}</span>'
                       f'<small>依据：{escape(row["reason"])}</small>{buttons}</li>')
    history = '<ul>' + ''.join(records) + '</ul>' if records else '<p>还没有纠错记录。</p>'
    message = f'<p class="notice" role="status">{escape(notice)}</p>' if notice else ''

    return f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>邻境 · 纠错流程演示</title>
<style>
* {{box-sizing:border-box}} body {{margin:0;background:#eef4f2;color:#19332d;font:16px/1.6 system-ui,sans-serif}}
main {{max-width:960px;margin:auto;padding:32px 18px 48px}} header {{margin-bottom:24px}}
h1 {{font-size:2.2rem;margin:4px 0}} h2 {{font-size:1.15rem;margin:0 0 12px}}
p {{margin:8px 0}} small {{color:#45645a}} .badge {{background:#d6e9e2;padding:4px 10px;border-radius:8px}}
.grid {{display:grid;grid-template-columns:1fr 1fr;gap:16px}} section {{background:white;border:1px solid #d4e2dc;border-radius:14px;padding:20px}}
section:last-child {{grid-column:1/-1}} form {{margin:10px 0}} label {{display:block;margin-bottom:8px}}
input,select,button {{font:inherit;border:1px solid #749388;border-radius:7px;padding:7px 10px}}
input:not([type=hidden]) {{display:block;width:100%;margin-top:4px}}
button {{background:#135d4c;color:white;cursor:pointer}} button.secondary {{background:white;color:#19332d}}
ul {{list-style:none;padding:0;margin:8px 0}} li {{padding:10px 0;border-top:1px solid #d4e2dc}} li span,li small {{display:block}}
.notice {{background:#d6e9e2;padding:10px 14px;border-radius:8px;margin-bottom:16px}}
@media(max-width:620px) {{.grid {{grid-template-columns:1fr}}}}
</style>
<main><header><span class="badge">本机教学演示 · 虚构地点</span><h1>邻境</h1>
<p>在一页里体验周边查询、地址纠错和审核更新。关闭启动窗口后，演示会重置。</p></header>
{message}
<div class="grid"><section><h2>1. 查附近银行</h2><form method="get" action="/">
<label for="radius">示例小区周边范围</label><select id="radius" name="radius">{options}</select>
<button>查附近</button></form>{results}</section>
<section><h2>2. 给示例银行提交纠错</h2><form method="post" action="/correction">{hidden}
<label>建议地址<input name="address" value="示例路 16 号" maxlength="100" required></label>
<label>纠错依据<input name="reason" value="演示中模拟核验门牌号" maxlength="200" required></label>
<button>提交纠错</button></form></section>
<section><h2>3. 模拟审核与修改记录</h2>{history}</section></div></main></html>'''


def parse_radius(value):
    return int(value) if value in tuple(map(str, RADII)) else 1000


class LocalDemoServer(HTTPServer):
    def server_bind(self):
        # A loopback-only demo does not need to resolve the Windows computer name.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class DemoHandler(BaseHTTPRequestHandler):
    def send_page(self, radius=1000, searched=False, notice='', status=200):
        body = page(self.server.db, self.server.token, radius, searched, notice).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get('Host') == '127.0.0.1:{}'.format(self.server.server_port)

    def do_GET(self):
        if not self.valid_host() or urlsplit(self.path).path != '/':
            self.send_error(404)
            return
        fields = parse_qs(urlsplit(self.path).query)
        radius = parse_radius(fields.get('radius', [''])[0])
        notice = NOTICES.get(fields.get('notice', [''])[0], '')
        self.send_page(radius, 'radius' in fields, notice)

    def do_POST(self):
        if not self.valid_host() or self.path not in ('/correction', '/review'):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('表单内容超出限制。')
            fields = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=8)
            token = fields.get('token', [''])[0]
            if not secrets.compare_digest(token.encode('utf-8'), self.server.token.encode('ascii')):
                self.send_error(403)
                return
            radius = parse_radius(fields.get('radius', [''])[0])
            if self.path == '/correction':
                address = fields.get('address', [''])[0]
                reason = fields.get('reason', [''])[0]
                if len(address) > 100 or len(reason) > 200:
                    raise ValueError('地址或纠错依据过长。')
                submit_address_correction(self.server.db, 2, address, reason)
                notice = 'submitted'
            else:
                decision = fields.get('decision', [''])[0]
                feedback_id = fields.get('id', [''])[0]
                if decision not in ('approve', 'reject') or not feedback_id.isascii() or not feedback_id.isdigit() or len(feedback_id) > 18:
                    raise ValueError('请选择有效的审核操作。')
                review_correction(self.server.db, int(feedback_id), approve=decision == 'approve')
                notice = 'approved' if decision == 'approve' else 'rejected'
        except ValueError as error:
            self.send_page(notice=str(error), status=400)
            return
        self.send_response(303)
        self.send_header('Location', '/?radius={}&notice={}'.format(radius, notice))
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description='邻境本机教学演示')
    parser.add_argument('--open-browser', action='store_true', help='启动后打开默认浏览器')
    args = parser.parse_args()
    with closing(connect(':memory:')) as db, LocalDemoServer(('127.0.0.1', 0), DemoHandler) as server:
        seed_demo(db)
        server.db = db
        server.token = secrets.token_urlsafe(24)
        url = 'http://127.0.0.1:{}'.format(server.server_port)
        print('邻境本机演示：' + url, flush=True)
        if args.open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
