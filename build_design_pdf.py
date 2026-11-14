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
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
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
    p('当前有六个小区、两家银行网点和一台 ATM，共九条 OSM 代表点试点样本。黄阁翠苑使用同名公交站参考点；准确入口、当前营业、设备可用性和访客通行仍待核实。'),
    p('2. 业务闭环', 'h1'),
    chain(['手动或运行期定时读取', '候选暂存与去重', '管理员确认入库']),
    Spacer(1, 5 * mm),
    chain(['用户提交纠错', '管理员审核', '版本更新与再核验']),
    p('候选必须先核对来源许可、位置和类别。查询热度只影响人工复核排序。字段变化才升版本；来源更新不覆盖已审核通过的地址。反馈提交后保持原地址，审核通过时版本增加。', 'small'),
    p('3. 数据边界', 'h1'),
    p('现有试点以 WGS84 114.210700, 22.687940 为 3 公里圆心，来源是 OSM 学校面历史代表点，不是校门。球面直线距离不等于步行距离。OSM 数据须保留 ODbL 署名与使用条件；高德实时候选只临时展示，不入库。原始采集时间未知，不补造日期。'),
    PageBreak(),
    p('4. 系统架构', 'h1'),
    chain(['本机 JSON 与校验', '任务与待审核候选', 'SQLite 版本数据库']),
    Spacer(1, 5 * mm),
    chain(['浏览器查询与纠错', '在线地图与列表', '管理员审核、核验']),
    p('本机服务运行时按设置的间隔重读来源文件；失败留错误和重试入口，不是独立服务器调度。候选经管理员确认后按来源编号增量合并，记录变化字段和时间。地图使用高德 JS API；WGS84 只在显示前转换，临时搜索结果不入库。'),
    p('5. 核心接口', 'h1'),
    table(['接口', '输入', '作用'], [
        ('GET /', '小区、范围、设施类型', '查询地点列表和地图标记'),
        ('POST /correction', '地点、建议地址、依据', '生成待审核反馈'),
        ('POST /login', '本次启动口令', '进入本机管理员模式'),
        ('POST /review', '反馈编号、通过或驳回', '审核并按版本更新地点'),
        ('POST /import', '带来源的地点 JSON', '校验并生成待审核候选'),
        ('POST /candidate', '候选编号、确认或驳回', '确认后增量入库，保留审核地址'),
        ('POST /retry', '失败任务编号', '重试本机文件采集'),
        ('POST /verify', '地点、结果、HTTPS 证据、说明', '记录当前地点版本的核验依据'),
    ], [43 * mm, 48 * mm, 81 * mm]),
    p('表单写入均检查本次令牌；管理操作还检查管理员会话。服务只监听本机地址。', 'small'),
    p('6. 关键数据表', 'h1'),
    table(['表', '关键内容'], [
        ('places', '地点类型、名称、地址、坐标、版本、更新时间'),
        ('place_imports', '来源编号、使用依据、坐标系、学校参考点、导入时间'),
        ('corrections', '原地址、建议地址、依据、提交时版本、审核状态及时间'),
        ('place_verifications', '地点版本、资料核验结果、证据链接、说明、记录时间'),
        ('query_interests', '小区编号、查询次数、最近查询时间；不保存访客身份'),
        ('collection_jobs / candidates', '来源文件、任务状态、结果、错误；候选及审核状态'),
        ('place_changes', '来源编号、前后版本、变化字段、采集时间'),
    ], [47 * mm, 125 * mm]),
    PageBreak(),
    p('7. 已完成验证', 'h1'),
    table(['场景', '结果与边界'], [
        ('真实接口可得性', '学校定位后，银行与小区各查询第一页 10 条；名称、地址、有效坐标字段均 10/10。字段存在不等于地点真实。'),
        ('查询与地图', '独立临时数据库首导 9 条、重导 0 条；选定小区可查附近设施。新版地图与筛选同步尚无新增截图证据。'),
        ('采集与增量', '临时来源文件验证定时触发、候选暂存、审核入库、字段变化升版、人工地址保护、失败重试；未验证外部接口持久化许可。'),
        ('查询统计', '当前筛选结果按银行与 ATM 计数；全部、单类及空结果与列表一致。仅代表已入库试点样本。'),
        ('更新优先级', '按小区查询次数与周边待资料核对设施数排人工队列；刷新也计数，不代表独立人数。'),
        ('反向关联', '两家银行网点可列出 3 公里内符合范围的已入库小区，距离与小区查网点的计算结果一致。'),
        ('纠错闭环', '待审核不改址；管理员通过后版本更新；旧反馈冲突回滚。'),
        ('核验状态', '访客不能写入；管理员保存资料依据后可展示；地址版本更新后恢复未核验。'),
        ('数据恢复', '本机试玩的测试地址已从当前演示库恢复为原始样本；备份保留历史。'),
    ], [40 * mm, 132 * mm]),
    p('8. 可行性、风险与安排', 'h1'),
    table(['维度', '可行依据、难点与应对'], [
        ('技术', 'Python 标准库、SQLite 与本机网页已跑通关键流程；独立服务器尚未验证。先用干净目录复现，决赛前再准备部署脚本并在指定纯净服务器实测；地图不可用时保留列表和离线示意。'),
        ('数据', '已有 9 条 OSM 代表点样本，覆盖不完整且原始采集时间未知。继续核对 ODbL 及跨地图展示条件；高德候选只临时展示，不批量入库。'),
        ('时间', '11 月 13 日前完成原型与证据；14—17 日回归、核对资料和完善文档；18—19 日冻结初赛版本并检查评审访问。若扩充数据来不及，保留可复现的 9 条试点样本和清楚的覆盖边界，不以假数据填数。'),
    ], [25 * mm, 147 * mm]),
    p('9. 当前未完成范围', 'h1'),
    p('外部接口的持久化采集、独立服务器调度、地图框选与图层切换、小区价格和年代筛选、区域总量统计及独立部署仍待实现。本机文件定时任务只在程序运行期间工作；当前数据不代表完整区域覆盖或实时状态。'),
    p('10. AI 服务使用说明', 'h1'),
    p('开发中使用 OpenAI Codex / ChatGPT 对话服务辅助起草代码、整理文档与排查问题，参赛者负责最终核对。调用方式为在客户端对话；邻境程序运行时未集成 AI 服务、未调用模型 API，因而没有产品内集成位置。AI 生成内容不作为地点真实性或核验结论。'),
    p('资料：项目 README、samples/README.md、首次接口验证报告及地点核验清单。', 'small'),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('SimHei', 8)
    canvas.setFillColor(GREY)
    canvas.drawString(19 * mm, 13 * mm, '邻境 | 初赛设计说明 | 2026-11-14')
    canvas.drawRightString(191 * mm, 13 * mm, str(doc.page))
    canvas.restoreState()


doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=19 * mm,
                        leftMargin=19 * mm, topMargin=18 * mm, bottomMargin=21 * mm,
                        title='邻境·初赛设计说明', author='邻境项目组', subject='赛题四初步设计与验证')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
