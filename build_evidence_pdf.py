"""Build the preliminary validation evidence from recorded results and screenshots."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "docs" / "验证证据"
OUTPUT = ROOT / "docs" / "邻境_初步验证证据.pdf"
pdfmetrics.registerFont(TTFont("SimHei", "C:/Windows/Fonts/simhei.ttf"))
INK = colors.HexColor("#263047")
PURPLE = colors.HexColor("#6656a7")
GREY = colors.HexColor("#657084")
PALE = colors.HexColor("#f2effb")

TITLE = ParagraphStyle("title", fontName="SimHei", fontSize=23, leading=31, textColor=INK, spaceAfter=11)
SECTION = ParagraphStyle("section", fontName="SimHei", fontSize=13, leading=20, textColor=PURPLE, spaceBefore=11, spaceAfter=7)
BODY = ParagraphStyle("body", fontName="SimHei", fontSize=9, leading=16, textColor=INK, spaceAfter=6)
SMALL = ParagraphStyle("small", fontName="SimHei", fontSize=8, leading=13, textColor=GREY, spaceAfter=5)
CELL = ParagraphStyle("cell", fontName="SimHei", fontSize=8.3, leading=14, textColor=INK)


def para(value, style=BODY):
    return Paragraph(escape(value), style)


def screenshot(name, caption):
    path = EVIDENCE / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return [para(caption, SECTION), Image(str(path), width=250 * mm, height=141 * mm), Spacer(1, 6 * mm)]


class ScreenshotHalf(Flowable):
    """Show one half of the same tall browser capture without shrinking its text."""

    def __init__(self, name, upper):
        super().__init__()
        self.path = EVIDENCE / name
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.width = 220 * mm
        self.height = 137 * mm
        self.upper = upper
        self.hAlign = "CENTER"

    def draw(self):
        source_width, source_height = ImageReader(str(self.path)).getSize()
        full_height = self.width * source_height / source_width
        self.canv.saveState()
        clip = self.canv.beginPath()
        clip.rect(0, 0, self.width, self.height)
        self.canv.clipPath(clip, stroke=0)
        y = self.height - full_height if self.upper else 0
        self.canv.drawImage(str(self.path), 0, y, width=self.width, height=full_height)
        self.canv.restoreState()


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("SimHei", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 13 * mm, "邻境 · 赛题四 · 初步验证证据 · 2026-11-14")
    canvas.drawRightString(279 * mm, 13 * mm, str(doc.page))
    canvas.restoreState()


story = [
    para("邻境 · 初步验证证据", TITLE),
    para("试点：以 OSM 学校面历史代表点 WGS84 114.210700, 22.687940 为圆心约 3 公里；此点不是校门。此文件与设计说明及源码仓库配套阅读。", BODY),
    para("1. 真实接口的初步验证", SECTION),
    para("2026-11-06 使用参赛者自己的高德 Web 服务 Key，先确认学校主体，再查询学校周边银行与小区。两类各取得第一页 10 条候选；名称、地址和有效坐标在各自样本中均为 10/10。银行电话为 6/10，小区电话为 1/10。工具不保存 Key 和原始候选列表。", BODY),
    para("这只证明接口连通和字段可得，不证明地点真实、类别准确、当前营业或全部覆盖；原始候选也未直接写入试点数据库。", SMALL),
    para("2. 从空库复现业务闭环", SECTION),
    para("2026-11-13 在独立临时数据库运行验证：首次导入 9 条附来源说明的样本（6 个小区、2 家银行、1 台 ATM）；查询返回已入库设施；纠错提交后仍显示原地址；管理员审核通过后更新地址与版本；服务重启后修订仍保留。命令为 python -B verify_clean_launch.py。", BODY),
    para("截图来自另一份独立演示库的实际浏览器操作。演示地址明确标为临时验证；它不是真实地点资料。本机试玩数据库未参与。", SMALL),
    para("2026-11-14 另在临时库验证本机 JSON 定时读取、候选暂存、管理员确认后入库、增量版本、人工地址保护和失败重试；来源内容的变化仅为模拟，未取得外部接口持久化采集的许可证明。", BODY),
    para("3. 可核对的原始记录", SECTION),
]

rows = [
    ["材料", "对应结论"],
    ["首次接口验证_20261106.md", "两类候选各 10 条的字段统计与限制"],
    ["本机业务闭环复现_20261113.md", "干净目录自动检查、浏览器彩排和重启记录"],
    ["01 至 05 浏览器截图", "查询、纠错审核、版本更新及在线地图与筛选的页面状态"],
    ["samples/README.md", "9 条试点样本的来源、坐标性质和限制"],
    ["本机采集任务复现_20261114.md", "本机文件任务与模拟增量变更；不代表外部接口许可"],
]
table = Table([[para(cell, CELL) for cell in row] for row in rows], colWidths=[66 * mm, 108 * mm])
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), PALE),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#ddd9eb")),
    ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
story.append(table)
story.append(PageBreak())
story.extend(screenshot("01-查询结果.jpg", "4. 查询结果：原地址、版本 1、未核验"))
story.append(PageBreak())
story.extend(screenshot("02-待审核.jpg", "5. 提交纠错：待审核 1 条，原地址未改变"))
story.append(PageBreak())
story.extend(screenshot("03-审核通过.jpg", "6. 审核通过：待审核归零，反馈显示已通过"))
story.append(PageBreak())
story.extend(screenshot("04-版本更新.jpg", "7. 新版本：演示地址、版本 2，仍标记未核验"))
story.extend([
    para("验证边界：现有样本不足以代表学校周边全部银行和小区；部分坐标为区域或楼宇参考点。独立服务器部署、真实入口及当前营业状态仍待另行核对。", SMALL),
])
story.append(PageBreak())
story.extend([
    para("8. 在线地图：筛选、统计与编号标记", SECTION),
    para("2026-11-14 本机独立验证库的同一次实际浏览器截图。京基·御景中央花园（一期）、3000 米、银行和 ATM：当前结果 3 处，其中银行 2、ATM 1；地图显示所选小区与 1 至 3 号地点。截图在两页分段展示，未拼接不同查询。", SMALL),
    ScreenshotHalf("05-在线地图与筛选.png", upper=True),
    PageBreak(),
    para("9. 同次查询：地图图例与三张地点卡片", SECTION),
    para("下半部分与上一页来自同一张浏览器截图。卡片共 3 张，顺序与地图编号一致。地图加载和界面同步已验证；地点入口、营业状态及许可边界仍须另行核对。", SMALL),
    ScreenshotHalf("05-在线地图与筛选.png", upper=False),
])

doc = SimpleDocTemplate(str(OUTPUT), pagesize=landscape(A4), leftMargin=18 * mm, rightMargin=18 * mm,
                        topMargin=20 * mm, bottomMargin=20 * mm,
                        title='邻境·初步验证证据', author='邻境项目组', subject='赛题四本机初步验证')
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
