from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BRAND = colors.HexColor("#0F766E")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#F1F5F9")
LINE = colors.HexColor("#DCE3EA")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#B54708")
GREEN = colors.HexColor("#067647")


def _register_font() -> str:
    font_path = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    if font_path.exists():
        if "RiskLeadCN" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("RiskLeadCN", str(font_path)))
        return "RiskLeadCN"

    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def _safe(value: Any) -> str:
    if value in (None, "", [], {}):
        return "暂无数据"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _detail_lines(payload: Any, limit: int = 12) -> list[str]:
    lines: list[str] = []

    def visit(label: str, value: Any) -> None:
        if len(lines) >= limit:
            return
        if isinstance(value, dict):
            scalar_parts = [
                f"{key}: {_safe(item)}"
                for key, item in value.items()
                if not isinstance(item, (dict, list))
            ]
            if scalar_parts:
                prefix = f"{label} - " if label else ""
                lines.append(prefix + "；".join(scalar_parts))
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    visit(str(key), item)
        elif isinstance(value, list):
            for index, item in enumerate(value, 1):
                visit(f"{label} {index}", item)
                if len(lines) >= limit:
                    break
        else:
            lines.append(f"{label}: {_safe(value)}")

    visit("", payload)
    return lines[:limit]


def generate_pdf_report(report: dict[str, Any]) -> bytes:
    font = _register_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{report['company']['name']}企业风险报告",
        author="企信雷达",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CNTitle",
        parent=styles["Title"],
        fontName=font,
        fontSize=22,
        leading=29,
        textColor=INK,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "CNSubtitle",
        parent=styles["Normal"],
        fontName=font,
        fontSize=9,
        leading=14,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=14,
    )
    heading_style = ParagraphStyle(
        "CNHeading",
        parent=styles["Heading2"],
        fontName=font,
        fontSize=14,
        leading=20,
        textColor=BRAND,
        spaceBefore=10,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "CNBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9,
        leading=15,
        textColor=INK,
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "CNSmall",
        parent=body_style,
        fontSize=7.5,
        leading=12,
        textColor=MUTED,
    )
    bullet_style = ParagraphStyle(
        "CNBullet",
        parent=body_style,
        leftIndent=10,
        firstLineIndent=-6,
        bulletIndent=0,
        spaceAfter=3,
    )

    def paragraph(value: Any, style=body_style) -> Paragraph:
        return Paragraph(escape(_safe(value)), style)

    def section(title: str) -> Paragraph:
        return Paragraph(escape(title), heading_style)

    def table(data, widths, header=True) -> Table:
        result = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 12),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.45, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        if header:
            commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ]
            )
        result.setStyle(TableStyle(commands))
        return result

    company = report["company"]
    assessment = report["risk_assessment"]
    scan = report["risk_scan"]
    level_color = {
        "低风险": GREEN,
        "中风险": AMBER,
        "高风险": RED,
        "严重风险": RED,
    }[assessment["level"]]

    story = [
        Paragraph("企信雷达", subtitle_style),
        Paragraph(escape(company["name"]), title_style),
        Paragraph(
            f"企业风险报告　|　生成时间：{escape(report['generated_at'])}",
            subtitle_style,
        ),
    ]

    summary_table = Table(
        [
            [paragraph("风险分", small_style), paragraph("风险等级", small_style), paragraph("待核查维度", small_style)],
            [paragraph(f"{assessment['score']} / 100"), paragraph(assessment["level"]), paragraph(assessment["attention_factor_count"])],
        ],
        colWidths=[55 * mm, 55 * mm, 55 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TEXTCOLOR", (1, 1), (1, 1), level_color),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([summary_table, Spacer(1, 7 * mm)])

    recommendation = {
        "低风险": "当前明确负面风险因子较少；仍需核查诉讼角色及具体交易背景。",
        "中风险": "存在需要关注的明确风险，建议补充材料并进行人工复核。",
        "高风险": "风险较高，建议谨慎合作并开展专项尽调。",
        "严重风险": "命中严重风险规则，建议暂停合作并立即开展人工核查。",
    }[assessment["level"]]
    story.extend([section("一、综合结论"), paragraph(recommendation), Spacer(1, 3 * mm)])

    ai_result = report.get("ai_analysis", {})
    story.append(section("二、风控负责人综合意见"))
    if ai_result.get("ok"):
        analysis = ai_result["data"]
        ai_summary_rows = [
            [paragraph("综合建议"), paragraph("固定评分"), paragraph("固定等级")],
            [
                paragraph(analysis["decision"]),
                paragraph(f"{analysis['fixed_score']} / 100"),
                paragraph(analysis["fixed_level"]),
            ],
        ]
        story.extend(
            [
                table(ai_summary_rows, [55 * mm, 55 * mm, 55 * mm]),
                Spacer(1, 3 * mm),
                paragraph(analysis["executive_summary"]),
            ]
        )
        if analysis["key_risks"]:
            story.append(Paragraph("重点风险", heading_style))
            for item in analysis["key_risks"]:
                story.append(
                    Paragraph(
                        "• " + escape(
                            f"[{item.get('severity', '待定')}] "
                            f"{item.get('title', '')}：{item.get('evidence', '')}"
                        ),
                        bullet_style,
                    )
                )
        if analysis["due_diligence_actions"]:
            story.append(Paragraph("建议补充核查", heading_style))
            for item in analysis["due_diligence_actions"]:
                story.append(Paragraph("• " + escape(str(item)), bullet_style))
        if analysis["risk_controls"]:
            story.append(Paragraph("建议风控措施", heading_style))
            for item in analysis["risk_controls"]:
                story.append(Paragraph("• " + escape(str(item)), bullet_style))
        story.append(
            Paragraph(
                escape(f"评分标准：{analysis['scoring_standard']}。大模型无权修改规则评分。"),
                small_style,
            )
        )
    else:
        story.append(paragraph(f"大模型综合分析暂不可用：{ai_result.get('error', '未知错误')}"))

    story.append(section("三、企业基本信息"))
    registration_rows = [
        [paragraph("字段"), paragraph("内容"), paragraph("字段"), paragraph("内容")],
        [paragraph("统一社会信用代码"), paragraph(company["credit_code"]), paragraph("登记状态"), paragraph(company["registration_status"])],
        [paragraph("法定代表人"), paragraph(company["legal_representative"]), paragraph("成立日期"), paragraph(company["established_date"])],
        [paragraph("注册资本"), paragraph(company["registered_capital"]), paragraph("实缴资本"), paragraph(company["paid_in_capital"])],
        [paragraph("企业类型"), paragraph(company["company_type"]), paragraph("所属行业"), paragraph(company["industry"])],
        [paragraph("所属地区"), paragraph(company["region"]), paragraph("人员规模"), paragraph(company["staff_size"])],
        [paragraph("注册地址"), paragraph(company["registered_address"]), paragraph("登记机关"), paragraph(company["registration_authority"])],
    ]
    story.append(table(registration_rows, [28 * mm, 55 * mm, 28 * mm, 55 * mm]))

    story.append(section("四、风险扣分原因"))
    if assessment["reasons"]:
        rows = [[paragraph("风险因子"), paragraph("记录数"), paragraph("分值"), paragraph("说明")]]
        rows.extend(
            [
                paragraph(item["factor"]),
                paragraph(item["count"]),
                paragraph(item["points"]),
                paragraph(item["description"]),
            ]
            for item in assessment["reasons"]
        )
        story.append(table(rows, [34 * mm, 22 * mm, 20 * mm, 90 * mm]))
    else:
        story.append(paragraph("当前未命中自动扣分规则。"))

    story.append(section("五、待核查事项"))
    if assessment["attention_items"]:
        rows = [[paragraph("维度"), paragraph("记录数"), paragraph("核查说明")]]
        rows.extend(
            [paragraph(item["factor"]), paragraph(item["count"]), paragraph(item["description"])]
            for item in assessment["attention_items"]
        )
        story.append(table(rows, [35 * mm, 24 * mm, 107 * mm]))
    else:
        story.append(paragraph("当前没有额外待核查维度。"))

    story.append(section("六、35项风险扫描摘要"))
    hit_factors = [factor for factor in scan["factors"] if factor["has_records"]]
    if hit_factors:
        rows = [[paragraph("风险因子"), paragraph("条目数"), paragraph("明细工具")]]
        rows.extend(
            [paragraph(item["name"]), paragraph(item["count"]), paragraph(item["detail_tool"])]
            for item in hit_factors
        )
        story.append(table(rows, [50 * mm, 28 * mm, 88 * mm]))
    else:
        story.append(paragraph("35项当前风险因子均未发现记录。"))

    story.append(section("七、企业画像与治理摘要"))
    for key in ("profile", "shareholders", "controller", "personnel"):
        detail = report["company_details"][key]
        content = [Paragraph(escape(detail["title"]), heading_style)]
        if detail["ok"]:
            lines = _detail_lines(detail["data"])
            content.extend(
                Paragraph("• " + escape(line), bullet_style)
                for line in lines
            )
            if not lines:
                content.append(paragraph("暂无数据"))
        else:
            content.append(paragraph(f"查询失败：{detail['error']}"))
        story.extend(content)

    story.extend(
        [
            section("八、使用说明"),
            Paragraph(
                "本报告的数据来自企查查智能体数据平台。风险分由企信雷达规则生成，"
                "不是企查查官方评分。风险扫描中的计数用于分诊，不代表案件责任或最终结论；"
                "未查询到记录也不等于绝对不存在风险。本报告不能替代法律、审计、征信或人工尽职调查。",
                small_style,
            ),
        ]
    )

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 10 * mm, "企信雷达 · 企业风险报告")
        canvas.drawRightString(A4[0] - 17 * mm, 10 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
