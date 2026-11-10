"""Generate the preliminary design PDF from the verified project milestones."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                               SimpleDocTemplate, Spacer, Table, TableStyle)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'docs' / '邻境_初赛设计说明.pdf'
pdfmetrics.registerFont(TTFont('SimHei', 'C:/Windows/Fonts/simhei.ttf'))
INK = colors.HexColor('#263047')
PURPLE = colors.HexColor('#6656a7')
PALE = colors.HexColor('#f2effb')
GREY = colors.HexColor('#657084')

styles = {
    'title': ParagraphStyle('title', fontName='SimHei', fontSize=25, leading=34, textColor=INK, spaceAfter=14),
    'subtitle': ParagraphStyle('subtitle', fontName='SimHei', fontSize=11, leading=18, textColor=GREY, spaceAfter=18),
    'h1': ParagraphStyle('h1', fontName='SimHei', fontSize=14, leading=22, textColor=PURPLE, spaceBefore=15, spaceAfter=9),
    'h2': ParagraphStyle('h2', fontName='SimHei', fontSize=10.5, leading=17, textColor=INK, spaceBefore=9, spaceAfter=5),
    'body': ParagraphStyle('body', fontName='SimHei', fontSize=9, leading=16, textColor=INK, spaceAfter=7),
    'small': ParagraphStyle('small', fontName='SimHei', fontSize=7.8, leading=12.5, textColor=INK),
    'cell': ParagraphStyle('cell', fontName='SimHei', fontSize=8, leading=13, textColor=INK),
    'head': ParagraphStyle('head', fontName='SimHei', fontSize=8, leading=13, textColor=colors.white),
    'center': ParagraphStyle('center', fontName='SimHei', fontSize=9, leading=15, textColor=INK, alignment=TA_CENTER),
}


def p(text, style='body'):
    return Paragraph(escape(text), styles[style])


def table(headings, rows, widths):
    data = [[p(value, 'head') for value in headings]]
    data.extend([[p(str(value), 'cell') for value in row] for row in rows])
    result = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PURPLE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f7fc')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, -1), (-1, -1), .4, colors.HexColor('#ddd9eb')),
    ]))
    return result


def chain(items):
    cells = []
    widths = []
    for index, item in enumerate(items):
        cells.append(p(item, 'center'))
        widths.append(45 * mm if len(items) == 3 else 31 * mm)
        if index < len(items) - 1:
            cells.append(p('→', 'center'))
            widths.append(10 * mm)
    result = Table([cells], colWidths=widths, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE),
        ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#d5cdef')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    return result


story = [
    p('邻境 · 初赛设计说明', 'title'),
    p('赛题四：银行与小区信息采集及查询系统  |  试点：深圳信息职业技术大学周边 3 公里', 'subtitle'),
    HRFlowable(width='100%', color=PURPLE, thickness=1),
    p('1. 需求与使用场景', 'h1'),
    p('用户选择小区和查询范围，在地图及列表中查找附近银行网点或 ATM，查看地址、直线距离和资料来源。银行卡片还可反向查看 3 公里内已入库小区。发现地址有误时可提交纠错；管理员审核后更新地点版本，查询结果同步变化。'),
    p('当前有两个小区、两家银行网点和一台 ATM。银行与 ATM 使用校区区域或楼宇代表点，不是设施入口；当前营业、设备可用性和访客通行仍待现场核实。'),
    p('2. 业务闭环', 'h1'),
    chain(['来源核对与导入', '小区周边查询', '地图与详情']),
    Spacer(1, 5 * mm),
    chain(['用户提交纠错', '管理员审核', '版本更新与再核验']),
    p('反馈提交后保持原地址；通过审核时，反馈状态和地点版本在同一事务中更新。基于旧版本的反馈不能覆盖较新的修订。新版本不沿用旧核验结论。', 'small'),
    p('3. 数据边界', 'h1'),
    p('输入样本带来源编号、许可说明及 WGS84 坐标。查询范围为学校参考点周边 3 公里。距离采用球面直线估算，页面明确标注，不等同于步行距离。缺失或未经证实的房价、营业状态不补造。'),
    PageBreak(),
    p('4. 系统架构', 'h1'),
    chain(['来源 JSON 与校验', 'SQLite 地点数据库', '本机 Python 服务']),
    Spacer(1, 5 * mm),
    chain(['浏览器查询与纠错', '在线地图与列表', '管理员审核、核验']),
    p('地图使用高德 JS API。WGS84 样本点仅在浏览器显示前转为 GCJ-02，转换结果不覆盖原数据；地图标记与筛选列表同步。安全密钥保存在本机 Git 忽略文件中，经固定路径代理使用。'),
    p('5. 核心接口', 'h1'),
    table(['接口', '输入', '作用'], [
        ('GET /', '小区、范围、设施类型', '查询地点列表和地图标记'),
        ('POST /correction', '地点、建议地址、依据', '生成待审核反馈'),
        ('POST /login', '本次启动口令', '进入本机管理员模式'),
        ('POST /review', '反馈编号、通过或驳回', '审核并按版本更新地点'),
        ('POST /import', '带来源的地点 JSON', '校验、去重并导入'),
        ('POST /verify', '地点、结果、HTTPS 证据、说明', '记录当前地点版本的核验依据'),
    ], [43 * mm, 48 * mm, 81 * mm]),
    p('表单写入均检查本次令牌；管理操作还检查管理员会话。服务只监听本机地址。', 'small'),
    PageBreak(),
    p('6. 关键数据表', 'h1'),
    table(['表', '关键内容'], [
        ('places', '地点类型、名称、地址、坐标、版本、更新时间'),
        ('place_imports', '来源编号、使用依据、坐标系、学校参考点、导入时间'),
        ('corrections', '原地址、建议地址、依据、提交时版本、审核状态及时间'),
        ('place_verifications', '地点版本、资料核验结果、证据链接、说明、记录时间'),
    ], [47 * mm, 125 * mm]),
    p('7. 已完成验证', 'h1'),
    table(['场景', '结果与边界'], [
        ('真实接口可得性', '学校定位后，银行与小区各查询第一页 10 条；名称、地址、有效坐标字段均 10/10。字段存在不等于地点真实。'),
        ('查询与地图', '独立临时数据库首导 5 条、重导 0 条；两小区各查到 3 项设施。新网点的网页输出已检查，浏览器地图显示仍待复核。'),
        ('查询统计', '当前筛选结果按银行与 ATM 计数；全部、单类及空结果与列表一致。仅代表已入库试点样本。'),
        ('反向关联', '银行网点可列出 3 公里内两处已入库小区，距离与小区查网点的计算结果一致。'),
        ('纠错闭环', '待审核不改址；管理员通过后版本更新；旧反馈冲突回滚。'),
        ('核验状态', '访客不能写入；管理员保存资料依据后可展示；地址版本更新后恢复未核验。'),
        ('数据恢复', '本机试玩的测试地址已从当前演示库恢复为原始样本；备份保留历史。'),
    ], [40 * mm, 132 * mm]),
    p('8. 可行性、风险与安排', 'h1'),
    p('技术：Python 标准库、SQLite 和本机网页已运行；独立服务器部署尚待验证。数据：目前仅 5 个公开来源样本，设施准确位置与现状需人工核对；批量采集须先确认来源允许的存储和使用范围。'),
    p('11 月 9—13 日：扩充可核验试点数据、整理证据；14—17 日：部署复现、回归和文档核对；18—19 日：冻结初赛版本、检查仓库评审访问及材料页数。'),
    p('9. 当前未完成范围', 'h1'),
    p('定时采集、热点驱动刷新、地图框选与图层切换、小区价格和年代筛选、区域总量统计及独立部署仍待实现。此原型不能代表完整区域覆盖或实时数据。'),
    p('资料：项目 README、samples/README.md、首次接口验证报告及地点核验清单。', 'small'),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('SimHei', 8)
    canvas.setFillColor(GREY)
    canvas.drawString(19 * mm, 13 * mm, '邻境 | 初赛设计说明 | 2026-11-10')
    canvas.drawRightString(191 * mm, 13 * mm, str(doc.page))
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=19 * mm,
                        leftMargin=19 * mm, topMargin=18 * mm, bottomMargin=21 * mm)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
