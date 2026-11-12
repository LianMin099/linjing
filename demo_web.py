"""本机网页演示。所有地点、审核和数据库都只用于教学。"""
import argparse
from contextlib import closing
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import math
import secrets
from socketserver import TCPServer
import sqlite3
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

from map_config import load_config
from live_map import map_widget, proxy_response
from ui_assets import PILOT_CSS, CITY_ART, icon
from demo_workflow import seed_demo
from import_places import import_dataset, validate_dataset
from linjing_db import (connect, ensure_verification_table, ensure_query_interest_table,
                        latest_verifications, nearby_banks, nearby_communities, priority_queue,
                        record_query_interest, record_verification, review_correction,
                        submit_address_correction)


RADII = (100, 300, 1000, 3000)
STATUS = {'pending': '待审核', 'approved': '已通过', 'rejected': '已驳回'}
NOTICES = {'submitted': '建议已提交。审核通过前，查询仍显示原地址。',
           'approved': '审核通过。查询结果已更新，旧地址仍保留在审核记录中。',
           'rejected': '建议已驳回。查询结果继续显示原地址。',
           'signed-in': '管理员已登录，可以审核待处理的纠错。',
           'signed-out': '已退出管理员模式。',
           'open-home': '请使用本页的表单继续。',
           'pilot-only': '管理员登录在真实地点查询页，请运行「打开真实地点查询.cmd」。'}
ADMIN_COOKIE = 'linjing_admin'
PLACE_TYPES = {'all': '银行和 ATM', 'bank': '仅银行网点', 'atm': '仅 ATM'}
FORM_PATHS = ('/correction', '/review', '/login', '/logout', '/import', '/verify')
MAX_IMPORT_BYTES = 65536


def form_fields(token, radius, filters=None):
    values = dict(token=token, radius=radius, **(filters or {}))
    return ''.join(f'<input type="hidden" name="{name}" value="{escape(str(value), quote=True)}">'
                   for name, value in values.items())


def correction_history(db, hidden, can_review):
    records = []
    pending = 0
    for row in db.execute('''
        SELECT corrections.*, places.name FROM corrections
        JOIN places ON places.id = corrections.place_id ORDER BY corrections.id DESC
    '''):
        buttons = ''
        if row['status'] == 'pending':
            pending += 1
        if can_review and row['status'] == 'pending':
            buttons = (f'<form method="post" action="/review">{hidden}'
                       f'<input type="hidden" name="id" value="{row["id"]}">'
                       '<button name="decision" value="approve">审核通过</button> '
                       '<button class="secondary" name="decision" value="reject">驳回</button></form>')
        records.append(f'<li><strong>{STATUS[row["status"]]}</strong> · {escape(row["name"])}<br>'
                       f'<span>{escape(row["old_address"])} → {escape(row["proposed_address"])}</span><br>'
                       f'<small>依据：{escape(row["reason"])}</small>{buttons}</li>')
    history = '<ul>' + ''.join(records) + '</ul>' if records else '<p>还没有纠错记录。</p>'
    return f'<p>待审核：{pending} 条</p>' + history


def page(db, token, radius, searched, notice=''):
    hidden = form_fields(token, radius)
    options = ''.join(f'<option value="{r}"{" selected" if r == radius else ""}>{r} 米</option>' for r in RADII)
    results = '<p>选择距离后点击「查附近」，查看示例小区附近的银行和 ATM。</p>'
    if searched:
        rows = nearby_banks(db, 1, radius)
        results = ''.join(
            f'<li><strong>{escape(row["name"])}</strong><span>{escape(row["address"])}</span>'
            f'<small>直线距离 {row["distance_m"]} 米 · 版本 {row["version"]}</small></li>' for row in rows
        )
        results = f'<ul>{results}</ul>' if results else '<p>这个范围内没有示例银行或 ATM。</p>'

    history = correction_history(db, hidden, can_review=True)
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


def pilot_filters(fields):
    community = fields.get('community', [''])[0]
    kind = fields.get('kind', ['all'])[0]
    return {
        'community': community if community.isascii() and community.isdigit() and len(community) <= 18 else '',
        'kind': kind if kind in PLACE_TYPES else 'all',
    }


def location_diagram(community, rows, radius):
    """Draw a local, north-up sketch from the same records as the result list."""
    center = 150
    scale = 122 / radius
    meters_per_degree = 111195
    longitude_scale = math.cos(math.radians(community['latitude']))
    markers = []
    for number, row in enumerate(rows, 1):
        x = center + (row['longitude'] - community['longitude']) * meters_per_degree * longitude_scale * scale
        y = center - (row['latitude'] - community['latitude']) * meters_per_degree * scale
        color = '#8871cd' if row['kind'] == 'bank' else '#c99c5d'
        name = escape(row['name'], quote=True)
        markers.append(f'<a href="#place-{row["id"]}" aria-label="查看 {name} 的详情">'
                       f'<g data-kind="{row["kind"]}"><title>{name}</title>'
                       f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{color}"/>'
                       f'<text x="{x:.1f}" y="{y + 4:.1f}" fill="white">{number}</text></g></a>')
    return f'''
    <figure class="location-diagram">
      <svg viewBox="0 0 300 300" role="group" aria-labelledby="location-title location-description">
        <title id="location-title">相对位置示意图</title>
        <desc id="location-description">以所选小区为中心，上北下南，编号与查询列表对应。</desc>
        <circle cx="150" cy="150" r="122" fill="#eeebfa" stroke="#b7a4dc" stroke-dasharray="4 4"/><circle cx="150" cy="150" r="61" fill="none" stroke="#d6cbea" stroke-dasharray="3 4"/>
        <path d="M28 150h244 M150 28v244" stroke="#d6cbea"/>
        <text x="150" y="19">↑ 北</text>
        <circle cx="150" cy="150" r="7" fill="#7da58c"/>
        {''.join(markers)}
      </svg>
      <figcaption>中心绿点为小区，紫色为银行，金色为 ATM。虚线圆表示 {radius:,} 米查询范围。点编号可查看地点详情。位置来自样本参考坐标，图中不含道路。</figcaption>
    </figure>'''



def place_sources(reference):
    """Present the recorded source and distinguish a campus anchor from a facility entrance."""
    if reference is None:
        return '<p>坐标来源：暂无可核验记录。</p>'
    source = reference['source_id'].split(':', 1)[0]
    object_type, _, number = source.partition('/')
    if (reference['source_url'] == 'https://www.openstreetmap.org/'
            and object_type in ('node', 'way', 'relation') and number.isascii() and number.isdigit()):
        link = f'<a href="https://www.openstreetmap.org/{object_type}/{number}">OpenStreetMap 参考点</a>'
        evidence = {
            'way/533650675:citic-cuhksz-branch-area': (
                '中信银行开业公告',
                'https://www.citicbank.com/about/companynews/banknew/message/201911/t20191105_82445.html',
            ),
            'way/544063816:cuhksz-atm-area': (
                '校方入住手册',
                'https://harmonia.cuhk.edu.cn/sites/harmonia.prod.dpsite02.cuhk.edu.cn/files/2023-08/%EF%BC%88%E5%B7%B2%E5%8E%8B%E7%BC%A9%EF%BC%89%E7%A5%A5%E6%B3%A2%E4%B9%A6%E9%99%A2%E5%85%A5%E4%BD%8F%E6%89%8B%E5%86%8C-0815_0.pdf',
            ),
        }.get(reference['source_id'])
        verified = ''
        if evidence:
            label, url = evidence
            verified = f'<p>设施名称依据：<a href="{url}">{label}</a>。当前营业和通行情况待核实。</p>'
        return f'<p>坐标来源：{link}。直线距离按区域参考点估算，具体入口待核实。</p>{verified}'
    return f'<p>坐标来源：{escape(reference["source_url"])}</p>'


def verification_evidence(check):
    if not check:
        return ''
    url = escape(check['evidence_url'], quote=True)
    note = escape(check['note'])
    checked_at = escape(check['checked_at'])
    return f'<p class="verification-evidence">记录于 {checked_at} UTC · <a href="{url}" rel="noopener noreferrer">查看证据</a> · {note}</p>'


def verification_state(place, check):
    if check:
        if check['result'] == 'source_checked':
            return '资料来源已核对 · 现场情况仍待确认'
        return '待现场核验'
    if place['version'] > 1:
        return '未核验 · 请勿将本机修订当作真实结论'
    return '未核验'


def community_links(db, place):
    if place['kind'] != 'bank':
        return ''
    matches = nearby_communities(db, place['id'], 3000)
    if not matches:
        return '<details><summary>查看网点周边小区</summary><p>3 公里内暂无已入库小区。</p></details>'
    links = ''.join(
        f'<li><a href="/?community={item["id"]}&radius=3000&kind=all">{escape(item["name"])}</a>'
        f' · {item["distance_m"] / 1000:.2f} 公里（直线估算）</li>'
        for item in matches)
    return f'<details><summary>网点周边小区（{len(matches)}）</summary><ul>{links}</ul></details>'



def import_panel(hidden):
    return f"""
<section class="surface" id="import-panel"><h2>手动导入地点</h2>
<p>选择已核对来源和使用依据的 JSON 文件。已有来源编号会跳过，保留已审核的修改。</p>
<form method="post" action="/import">{hidden}
<label>选择 JSON 文件 <input type="file" id="import-file" accept=".json,application/json"></label>
<label for="import-data">文件内容（也可以直接粘贴）</label>
<textarea id="import-data" name="dataset" rows="4" required></textarea>
<p id="import-feedback" role="status"></p>
<button>校验并导入</button></form>
<script>
document.getElementById("import-file").addEventListener("change", async (event) => {{
  const file = event.target.files[0];
  const input = document.getElementById("import-data");
  const feedback = document.getElementById("import-feedback");
  input.value = "";
  feedback.textContent = "";
  if (!file) return;
  if (file.size > {MAX_IMPORT_BYTES}) {{
    feedback.textContent = "文件超过 64 KB，请分批导入。";
    return;
  }}
  try {{
    const text = await file.text();
    if (event.target.files[0] === file) input.value = text;
  }} catch {{
    feedback.textContent = "无法读取文件，请重选或粘贴内容。";
  }}
}});
</script></section>"""



def pilot_page(db, token, radius, notice, is_admin, filters, map_config=None):
    communities = db.execute("SELECT id, name, longitude, latitude FROM places WHERE kind = 'community' ORDER BY name, id").fetchall()
    if not communities:
        return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><p>数据库里还没有小区记录。</p></html>'
    inventory = {row['kind']: row['total'] for row in db.execute(
        'SELECT kind, COUNT(*) AS total FROM places GROUP BY kind')}
    community = next((row for row in communities if str(row['id']) == filters['community']), communities[0])
    kind = filters['kind']
    options = ''.join(f'<option value="{r}"{" selected" if r == radius else ""}>{r} 米</option>' for r in RADII)
    community_options = ''.join(
        f'<option value="{row["id"]}"{" selected" if row["id"] == community["id"] else ""}>{escape(row["name"])}</option>'
        for row in communities
    )
    kind_options = ''.join(f'<option value="{key}"{" selected" if key == kind else ""}>{label}</option>'
                           for key, label in PLACE_TYPES.items())
    hidden = form_fields(token, radius, {'community': community['id'], 'kind': kind})
    rows = [row for row in nearby_banks(db, community['id'], radius) if kind == 'all' or row['kind'] == kind]
    counts = {place_kind: sum(row['kind'] == place_kind for row in rows) for place_kind in ('bank', 'atm')}
    scale = max(1, *counts.values())
    chart = ''.join(
        f'<div class="stat-row"><span>{label}</span><div class="stat-track" role="img" '
        f'aria-label="{label} {counts[place_kind]} 条"><i class="stat-fill {place_kind}" '
        f'style="width:{counts[place_kind] / scale * 100:.0f}%"></i></div>'
        f'<strong>{counts[place_kind]}</strong></div>'
        for place_kind, label in (('bank', '银行网点'), ('atm', 'ATM'))
    )
    checks = latest_verifications(db)
    references = {row['place_id']: row for row in db.execute(
        'SELECT place_id, source_id, source_url FROM place_imports'
    )} if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='place_imports'").fetchone() else {}
    school_row = db.execute('SELECT school_longitude, school_latitude FROM place_imports LIMIT 1').fetchone() if references else None
    school = [school_row['school_longitude'], school_row['school_latitude']] if school_row else None
    results = ''.join(
        f'<li class="place-result" id="place-{row["id"]}" tabindex="-1">'
        f'<div class="place-head"><span class="place-symbol {row["kind"]}">{icon("bank")}</span>'
        f'<div class="place-title"><strong>{escape(row["name"])}</strong><div class="place-type">地点 {number:02d} · {"ATM 自助设备" if row["kind"] == "atm" else "银行服务网点"}</div></div>'
        f'<span class="place-distance">{row["distance_m"] / 1000:.2f}<small>公里 · 直线估算</small></span></div>'
        f'<p class="place-address">{escape(row["address"])}</p>'
        f'<div class="place-meta"><span class="badge {row["kind"]}-badge">{"ATM" if row["kind"] == "atm" else "银行网点"}</span>'
        f'<span class="badge">版本 {row["version"]}{" · 本机修订" if row["version"] > 1 else ""}</span></div>'
        f'<p class="verification-state">{verification_state(row, checks.get(row["id"]))}</p>'
        + verification_evidence(checks.get(row['id']))
        + f'<details><summary>查看来源与核验状态</summary>{place_sources(references.get(row["id"]))}</details>'
        + community_links(db, row)
        + f'<details><summary>提交地址纠错</summary><form method="post" action="/correction">{hidden}'
        f'<input type="hidden" name="place_id" value="{row["id"]}">'
        '<label>建议地址 <input name="address" maxlength="100" required></label> '
        '<label>依据 <input name="reason" maxlength="200" required></label> '
        '<button>提交纠错</button></form></details></li>'
        for number, row in enumerate(rows, 1)
    )
    message = f'<p class="notice" role="status">{escape(notice)}</p>' if notice else ''
    if is_admin:
        admin_panel = (f'<p>当前身份：管理员</p><form method="post" action="/logout">{hidden}'
                       '<button>退出管理员模式</button></form>')
    else:
        admin_panel = (f'<p>当前身份：访客。可以提交纠错，审核需要管理员登录。</p>'
                       f'<form method="post" action="/login">{hidden}'
                       '<label>本次管理员口令 <input name="code" type="password" maxlength="64" required></label> '
                       '<button>管理员登录</button></form><small>口令显示在本机启动窗口。</small>')
    verification_panel = ''
    priority_panel = ''
    if is_admin:
        queue = priority_queue(db)
        items = ''.join(f'<li><strong>{index}. {escape(item["name"])}</strong><span>查询请求 {item["searches"]} 次 · 周边待资料核对 {item["unverified"]} 处</span></li>'
                        for index, item in enumerate(queue, 1))
        priority_panel = '<section class="surface priority-panel"><h2>优先核验队列</h2><p>查询请求越多、周边待资料核对设施越多，越靠前；刷新也会计数。仅供人工安排，不会自动更改地点。</p><ol>' + items + '</ol></section>'
        place_options = ''.join(
            f'<option value="{p["id"]}">{escape(p["name"])} · 版本 {p["version"]}</option>'
            for p in db.execute('SELECT id, name, version FROM places ORDER BY id'))
        verification_panel = (f'<section class="surface" id="verify-panel"><h2>资料核验记录</h2>'
            '<p>只记录你亲自核对过的证据。资料核对不代表设备当前可用或访客可进入；地点版本变化后重新标为未核验。</p>'
            f'<form method="post" action="/verify">{hidden}'
            f'<label>地点<select name="place_id">{place_options}</select></label>'
            '<label>核对结果<select name="result"><option value="needs_field_check">仍需现场核实</option><option value="source_checked">公开资料已核对</option></select></label>'
            '<label>证据链接<input name="evidence_url" type="url" maxlength="500" placeholder="https://…" required></label>'
            '<label>核验说明<textarea name="note" maxlength="300" required placeholder="说明核对了什么，仍有哪些未知项"></textarea></label>'
            '<button>保存核验记录</button></form></section>')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>邻境 · 真实样本查询</title>
<style>{PILOT_CSS}</style>
<aside class="sidebar"><a class="brand" href="/" aria-label="邻境首页"><span class="brand-mark">{icon('pin')}</span><span class="brand-text"><strong>邻境</strong><small>LINJING</small></span></a>
<p class="nav-label">WORKSPACE</p><nav aria-label="页面导航"><a class="nav-link active" href="#query" aria-label="探索周边">{icon('compass')}<span class="nav-text">探索周边</span></a><a class="nav-link" href="#review" aria-label="纠错与反馈">{icon('edit')}<span class="nav-text">纠错与反馈</span></a><a class="nav-link" href="#admin" aria-label="管理工作台">{icon('shield')}<span class="nav-text">管理工作台</span></a></nav>
<div class="sidebar-note">{icon('pin')}<strong>从校园，走向周边</strong>深圳信息职业技术大学<br>周边 3 公里 · 试点探索</div></aside>
<div class="workspace"><header class="topbar"><div class="breadcrumb">邻境工作台 <b>／ &nbsp; 探索周边</b></div><div class="user-pill"><span class="avatar">{icon('shield') if is_admin else icon('grid')}</span>{'管理员模式' if is_admin else '访客模式'}</div></header>
<main><div class="page-heading"><div><h1>探索周边</h1><p>让身边的信息，更近一步。</p></div><span class="local-tag"><span class="status-dot"></span>本地试点 · 深圳龙岗</span></div>
<section class="hero"><div class="hero-copy"><div class="eyebrow">A LITTLE CLOSER TO YOUR NEIGHBORHOOD</div><h2>熟悉一座城，<br>从<em>身边的每一处</em>开始。</h2><p>发现小区附近的银行与 ATM，让每次出发都有据可依。</p><a class="hero-link" href="#query">探索我的周边 {icon('arrow')}</a></div>{CITY_ART}</section>
{message}
<section class="surface" id="query"><div class="query-header"><h2 class="section-label">{icon('search')} 发现附近</h2><span class="subtle-label">选择一个小区，开启周边探索</span></div>
<form class="filters" method="get" action="/"><label>所在小区<select name="community">{community_options}</select></label><label>探索范围<select name="radius">{options}</select></label><label>设施类型<select name="kind">{kind_options}</select></label><button>{icon('search')}查已入库地点</button></form>{'<p class="query-help">想看更多地点？请在下方地图点击「查银行」或「查小区」。高德实时结果可翻页，仅临时显示。</p>' if map_config else ''}</section>
<section class="query-stats" aria-label="当前查询统计"><div><strong>当前结果 · {len(rows)} 处</strong><p>试点库现有 {inventory.get('community', 0)} 个小区、{inventory.get('bank', 0)} 家银行、{inventory.get('atm', 0)} 台 ATM；尚未覆盖周边全部地点。当前结果随小区、范围和类型筛选变化。</p></div><div class="stat-bars">{chart}</div></section>
<div class="query-layout"><div class="map-panel"><div class="panel-heading"><h3 class="section-label">{icon('compass')} 周边分布</h3><small>{"高德地图 · 参考点" if map_config else "相对位置示意"}</small></div><div class="map-shell"><span class="map-label">{escape(community['name'])} · {radius:,} m</span>{map_widget(community, rows, radius, map_config, location_diagram(community, rows, radius), school)}</div><div class="map-legend"><span><i class="legend-dot" style="background:#7da58c"></i>所选小区</span><span><i class="legend-dot" style="background:#8871cd"></i>银行网点</span><span><i class="legend-dot" style="background:#c99c5d"></i>ATM</span></div></div>
<div><section id="amap-live-results" hidden><h3>高德实时结果 <span id="amap-live-count" class="count"></span></h3><p>学校周边 3 公里 · 仅本次搜索显示的候选</p><div id="amap-live-pager" hidden><button type="button" id="amap-prev-page">上一页</button><span id="amap-page-label"></span><button type="button" id="amap-next-page">下一页</button></div></section><div class="panel-heading"><h3>已入库样本 <span class="count">{len(rows):02d}</span></h3><small>按直线距离排序</small></div>
{('<ul class="results-list">' + results + '</ul>') if results else '<div class="empty">' + icon('search') + '<strong>附近还没有匹配的样本</strong><p>试试扩大探索范围，或选择其他设施类型。</p></div>'}
</div></div><div class="query-footnote"><p>中信银行网点和中国银行 ATM 分别使用港中大（深圳）下园、上园的区域代表点。距离为估算，具体入口和开放情况待核实；位置示意图不含道路。</p><p>坐标数据 © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors（ODbL）</a></p></div>
<section class="surface" id="review"><div class="review-heading"><div><h2 class="section-label">{icon('edit')} 一起，让信息更准确</h2><p>发现地址有误？在地点卡片中提交纠错，审核结果会显示在这里。</p></div>{'<a class="hero-link" href="#import-panel">导入地点 →</a>' if is_admin else ''}</div><div class="review-body"><div class="admin-box" id="admin"><h3>管理工作台</h3>{admin_panel}</div><div class="history-box"><h3>反馈动态</h3>{correction_history(db, hidden, can_review=is_admin)}</div></div></section>{import_panel(hidden) if is_admin else ''}
{verification_panel}
{priority_panel}
<footer class="footer"><span>邻境 LINJING · 发现身边，连接生活</span><span>本地试点版本 · 修改保存在本机数据库</span></footer></main></div></html>'''


class LocalDemoServer(HTTPServer):
    def server_bind(self):
        # A loopback-only demo does not need to resolve the Windows computer name.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Map SDK query strings can carry credentials; do not log request URLs.
        pass

    def serve_map_proxy(self):
        expected = urlsplit('http://' + self.headers.get('Host', ''))
        referer = urlsplit(self.headers.get('Referer', ''))
        if not self.server.map_config or referer.netloc != expected.netloc:
            print('Map proxy: request origin rejected', flush=True)
            self.send_error(403)
            return
        try:
            body, content_type = proxy_response(self.path, self.server.map_config)
        except Exception as error:
            print('Map proxy: ' + type(error).__name__, flush=True)
            # Never relay exception text: upstream URLs contain the security code.
            self.send_error(502, 'Map service unavailable')
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def is_admin(self):
        if not self.server.pilot or self.server.admin_session is None:
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except CookieError:
            return False
        session = cookies.get(ADMIN_COOKIE)
        return session is not None and secrets.compare_digest(
            session.value.encode('utf-8'), self.server.admin_session.encode('ascii'))

    def send_page(self, radius=1000, searched=False, notice='', status=200, filters=None):
        content = (pilot_page(self.server.db, self.server.token, radius, notice, self.is_admin(), filters or pilot_filters({}), self.server.map_config) if self.server.pilot
                   else page(self.server.db, self.server.token, radius, searched, notice))
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        port = self.server.server_port
        return self.headers.get('Host', '').lower() in ('127.0.0.1:{}'.format(port), 'localhost:{}'.format(port))

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.valid_host():
            self.send_error(404)
            return
        if path.startswith('/_AMapService/'):
            self.serve_map_proxy()
            return
        if path in FORM_PATHS:
            notice = 'pilot-only' if path in ('/login', '/logout', '/import', '/verify') and not self.server.pilot else 'open-home'
            self.send_response(303)
            self.send_header('Location', '/?notice=' + notice)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return
        if path != '/':
            self.send_error(404)
            return
        fields = parse_qs(urlsplit(self.path).query)
        radius = parse_radius(fields.get('radius', ['3000' if self.server.pilot else ''])[0])
        notice = NOTICES.get(fields.get('notice', [''])[0], '')
        if self.server.pilot and 'radius' in fields and 'community' in fields and 'notice' not in fields:
            selected = pilot_filters(fields)['community']
            if selected:
                record_query_interest(self.server.db, int(selected))
        self.send_page(radius, 'radius' in fields, notice, filters=pilot_filters(fields))

    def do_POST(self):
        paths = FORM_PATHS if self.server.pilot else ('/correction', '/review')
        if not self.valid_host() or self.path not in paths:
            self.send_error(404)
            return
        if self.path in ('/import', '/verify') and not self.is_admin():
            self.send_error(403)
            return
        cookie = None
        radius = 3000 if self.server.pilot else 1000
        filters = {}
        try:
            length = int(self.headers.get('Content-Length', '0'))
            max_length = MAX_IMPORT_BYTES * 3 + 4096 if self.path == '/import' else 4096
            if not 0 < length <= max_length:
                raise ValueError('表单内容超出限制。')
            fields = parse_qs(self.rfile.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=8)
            token = fields.get('token', [''])[0]
            if not secrets.compare_digest(token.encode('utf-8'), self.server.token.encode('ascii')):
                self.send_error(403)
                return
            radius = parse_radius(fields.get('radius', [''])[0])
            if self.server.pilot:
                filters = pilot_filters(fields)
            if self.path == '/verify':
                raw_id = fields.get('place_id', [''])[0]
                if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 18:
                    raise ValueError('请选择有效的地点。')
                record_verification(self.server.db, int(raw_id), fields.get('result', [''])[0],
                                    fields.get('evidence_url', [''])[0], fields.get('note', [''])[0])
                self.send_page(radius, notice='核验记录已保存；现场情况仍须按证据确认。', filters=filters)
                return
            if self.path == '/import':
                raw = fields.get('dataset', [''])[0]
                if len(raw.encode('utf-8')) > MAX_IMPORT_BYTES:
                    raise ValueError('文件超过 64 KB，请分批导入。')
                try:
                    dataset = json.loads(raw.lstrip('\ufeff'))
                except (ValueError, RecursionError) as error:
                    raise ValueError('文件不是有效的 JSON。') from error
                metadata, rows = validate_dataset(dataset)
                added = import_dataset(self.server.db, metadata, rows)
                self.send_page(radius, notice=f'导入完成：新增 {added} 条，跳过已有 {len(rows) - added} 条。',
                               filters=filters)
                return
            if self.path == '/login':
                code = fields.get('code', [''])[0].strip()
                if not secrets.compare_digest(code.encode('utf-8'), self.server.admin_code.encode('ascii')):
                    self.send_page(radius, notice='口令不正确，请查看启动窗口。', status=403, filters=filters)
                    return
                self.server.admin_session = secrets.token_urlsafe(32)
                cookie = f'{ADMIN_COOKIE}={self.server.admin_session}; Path=/; HttpOnly; SameSite=Strict'
                notice = 'signed-in'
            elif self.path == '/logout':
                if self.is_admin():
                    self.server.admin_session = None
                cookie = f'{ADMIN_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict'
                notice = 'signed-out'
            elif self.path == '/correction':
                address = fields.get('address', [''])[0]
                reason = fields.get('reason', [''])[0]
                if len(address) > 100 or len(reason) > 200:
                    raise ValueError('地址或纠错依据过长。')
                place_id = 2
                if self.server.pilot:
                    raw_id = fields.get('place_id', [''])[0]
                    if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 18:
                        raise ValueError('请选择有效的地点。')
                    place_id = int(raw_id)
                    place = self.server.db.execute(
                        "SELECT 1 FROM places WHERE id = ? AND kind IN ('bank', 'atm')", (place_id,)).fetchone()
                    if place is None:
                        raise ValueError('找不到对应银行或 ATM。')
                submit_address_correction(self.server.db, place_id, address, reason)
                notice = 'submitted'
            else:
                if self.server.pilot and not self.is_admin():
                    self.send_page(radius, notice='只有管理员可以审核纠错。', status=403, filters=filters)
                    return
                decision = fields.get('decision', [''])[0]
                feedback_id = fields.get('id', [''])[0]
                if decision not in ('approve', 'reject') or not feedback_id.isascii() or not feedback_id.isdigit() or len(feedback_id) > 18:
                    raise ValueError('请选择有效的审核操作。')
                review_correction(self.server.db, int(feedback_id), approve=decision == 'approve')
                notice = 'approved' if decision == 'approve' else 'rejected'
        except ValueError as error:
            self.send_page(radius, searched=True, notice=str(error), status=400, filters=filters)
            return
        except sqlite3.Error:
            self.send_page(radius, searched=True, notice='数据库写入失败，本次修改未保存。', status=500, filters=filters)
            return
        self.send_response(303)
        self.send_header('Location', '/?' + urlencode(dict(radius=radius, notice=notice, **filters)))
        if cookie is not None:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()


def start_server(pilot_db=None, open_browser=False, port=0):
    if pilot_db is None:
        db = connect(':memory:')
    else:
        db = sqlite3.connect(pilot_db.resolve().as_uri() + '?mode=rw', uri=True)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        ensure_verification_table(db)
        ensure_query_interest_table(db)
    with closing(db), LocalDemoServer(('127.0.0.1', port), DemoHandler) as server:
        server.pilot = pilot_db is not None
        server.map_config = None
        if server.pilot:
            try:
                server.map_config = load_config()
            except ValueError:
                print('地图配置不可用，将显示离线示意图。请重新配置地图。', flush=True)
        if not server.pilot:
            seed_demo(db)
        server.db = db
        server.token = secrets.token_urlsafe(24)
        server.admin_session = None
        url = 'http://127.0.0.1:{}'.format(server.server_port)
        print('邻境本机演示：' + url, flush=True)
        if server.pilot:
            server.admin_code = secrets.token_urlsafe(12)
            print('本次管理员口令：' + server.admin_code, flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description='邻境本机教学演示')
    parser.add_argument('--open-browser', action='store_true', help='启动后打开默认浏览器')
    parser.add_argument('--pilot-db', type=Path, help='打开真实样本数据库，持久保存本机纠错')
    args = parser.parse_args()
    start_server(args.pilot_db, args.open_browser)


if __name__ == '__main__':
    main()
