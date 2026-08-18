from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT = Path(__file__).resolve().parents[1] / "samples/enterprise_corpus"
FONT = "ArialUnicode"
pdfmetrics.registerFont(TTFont(FONT, "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"))


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "EnterpriseTitle", parent=base["Title"], fontName=FONT,
            fontSize=22, leading=30, alignment=TA_CENTER, spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "EnterpriseSubtitle", parent=base["Normal"], fontName=FONT,
            fontSize=10, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"),
        ),
        "h1": ParagraphStyle(
            "EnterpriseH1", parent=base["Heading1"], fontName=FONT,
            fontSize=16, leading=24, textColor=colors.HexColor("#163d35"),
            spaceBefore=12, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "EnterpriseH2", parent=base["Heading2"], fontName=FONT,
            fontSize=12, leading=19, textColor=colors.HexColor("#295c50"),
            spaceBefore=9, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "EnterpriseBody", parent=base["BodyText"], fontName=FONT,
            fontSize=9.5, leading=17, alignment=TA_LEFT, spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "EnterpriseSmall", parent=base["BodyText"], fontName=FONT,
            fontSize=8, leading=13, textColor=colors.HexColor("#64748b"),
        ),
        "table": ParagraphStyle(
            "EnterpriseTable", parent=base["BodyText"], fontName=FONT,
            fontSize=8.2, leading=13,
        ),
        "table_head": ParagraphStyle(
            "EnterpriseTableHead", parent=base["BodyText"], fontName=FONT,
            fontSize=8.2, leading=13, textColor=colors.white,
        ),
    }


def footer(canvas, document):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.drawString(20 * mm, 12 * mm, "星河智联科技有限公司 · 企业知识库样本文档")
    canvas.drawRightString(190 * mm, 12 * mm, f"第 {document.page} 页")
    canvas.restoreState()


def build_pdf(path: Path, title: str, subtitle: str, sections: list[tuple[str, str]], tables: list[tuple[str, list[list[str]]]]) -> None:
    frame = Frame(20 * mm, 20 * mm, 170 * mm, 247 * mm, id="normal")
    doc = BaseDocTemplate(
        str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=title, author="星河智联科技有限公司",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=footer)])
    s = styles()
    story = [Paragraph(title, s["title"]), Paragraph(subtitle, s["subtitle"]), Spacer(1, 8), HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#dca85f")), Spacer(1, 14)]

    for heading, content in sections:
        story.append(Paragraph(heading, s["h1"]))
        for paragraph in content.split("\n\n"):
            story.append(Paragraph(paragraph, s["body"]))

    for heading, rows in tables:
        story.append(PageBreak())
        story.append(Paragraph(heading, s["h1"]))
        table_data = []
        for row_index, row in enumerate(rows):
            style = s["table_head"] if row_index == 0 else s["table"]
            table_data.append([Paragraph(cell, style) for cell in row])
        table = Table(table_data, repeatRows=1, colWidths=[38 * mm, 42 * mm, 45 * mm, 45 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173f35")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(Paragraph("表格说明：表内数据为企业知识库测试数据，用于验证表头保留、跨页表格、行级切片和来源页码。", s["small"]))

    doc.build(story)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    customer_sections = [
        ("一、服务范围", "客户服务中心负责受理客户关于产品使用、账号权限、账单咨询、故障报告和功能建议的请求。服务团队应先确认客户身份、合同范围和服务等级，再提供与授权范围一致的支持。未经客户授权，客服人员不得导出全部客户数据、修改结算账户或代替客户完成高风险操作。\n\n服务请求应统一进入客户服务平台。电话、即时通讯和现场反馈也应在一个工作日内补录为工单，以便后续统计、质量复盘和责任追踪。每一张工单都应包含问题描述、影响范围、发现时间、已采取措施、客户期望和下一步计划。"),
        ("二、客户问题分级", "紧急故障是指核心业务完全不可用、关键数据无法访问、出现疑似安全事件或大面积客户受到影响。高优先级问题是指主要功能明显受影响但存在临时替代方案。普通问题包括单个用户配置错误、使用咨询和一般功能建议。客服人员不能仅依据客户情绪判断等级，应结合业务影响、受影响人数、合同服务等级和是否存在安全风险综合判断。\n\n当问题需要研发、运维或安全团队介入时，客服人员应提供经过整理的最小必要信息，避免在公共群组中粘贴完整客户数据。升级后仍由客服负责人维护客户沟通节奏，技术团队负责诊断和修复。"),
        ("三、沟通与承诺", "客服回复应准确、清晰并避免未经确认的时间承诺。可以承诺下一次更新时间，但不能在根因尚未确认时承诺最终修复时间。涉及服务中断时，应说明已知影响、临时措施、正在进行的工作和下一次更新节点。\n\n客户要求修改权限、导出数据、关闭安全控制或变更收款信息时，应通过第二渠道核实并按照审批流程执行。客户服务人员不得将个人邮箱、私人网盘或个人即时通讯账号作为长期资料交换渠道。"),
        ("四、质量与复盘", "每月抽取已关闭工单进行质量检查，检查内容包括分类是否准确、首次响应是否及时、引用的知识是否正确、客户是否得到明确下一步以及是否存在重复沟通。重大故障和重复发生的问题必须形成复盘记录，包含时间线、影响、根因、短期修复、长期改进和责任人。\n\n知识库管理员应将高频问题转化为经过审核的知识文章。文章应包含适用版本、前置条件、操作步骤、常见错误、回滚方法和最后更新时间，避免客服只复制一段脱离上下文的答案。"),
    ]
    customer_tables = [("客户服务等级与响应目标", [
        ["等级", "典型场景", "首次响应", "更新与关闭"],
        ["S1 紧急", "核心业务中断或疑似数据泄露", "15 分钟", "每 30 分钟更新，恢复后 5 日内复盘"],
        ["S2 高", "主要功能受影响且影响多个用户", "1 小时", "每日更新，目标 2 个工作日内给方案"],
        ["S3 普通", "单用户故障、配置或一般使用问题", "4 小时", "3 个工作日内解决或给出计划"],
        ["S4 咨询", "产品咨询、建议和低影响请求", "1 工作日", "进入知识库或产品计划"],
        ["安全事件", "账号接管、异常导出或敏感信息外泄", "立即升级", "由安全负责人决定通知和恢复策略"],
    ])]

    finance_sections = [
        ("一、财务共享服务中心", "财务共享服务中心负责应付、应收、费用、发票、资金和月结支持。业务部门应通过财务服务门户提交申请，不得通过口头承诺或私人聊天记录替代正式凭证。财务人员应遵循职责分离原则，申请、审批、付款和对账不能由同一人独立完成。\n\n所有金额、税率、币种、合同主体和付款账户都必须与合同及发票一致。发现供应商账户变更、重复发票、异常折扣或付款信息不一致时，应暂停付款并通过供应商主数据流程核实。"),
        ("二、收入确认与开票", "销售团队提交开票申请时，应提供合同、订单、交付或验收证明以及客户开票信息。财务人员应确认合同主体、服务周期、税率和开票金额。跨期服务必须按照会计政策和合同履约情况确认收入，不得为了完成当月指标提前开票或虚构交付。\n\n红字发票、作废发票和客户抬头变更需要说明原因并关联原始单据。客户要求将发票发送至个人邮箱时，员工应确认该邮箱属于客户授权联系人，避免将商业信息发送到未经验证的地址。"),
        ("三、月结管理", "月结包括银行对账、应收应付余额核对、预提费用、合同负债、固定资产、员工费用和项目成本检查。各业务负责人应在月结截止日前完成未入账事项确认。对无法及时取得发票但服务已经发生的费用，应按照制度进行合理预提，并在后续期间冲回或调整。\n\n月结期间发现重大差异时，责任部门需要提供解释、影响金额、预计修正时间和防止重复发生的措施。财务部不得通过随意调整科目或跨期转移费用掩盖差异。"),
        ("四、资金与付款安全", "付款申请应关联采购订单、验收记录或合同付款节点。大额付款和新供应商付款必须执行双人复核。任何通过邮件或即时通讯要求紧急修改收款账户的请求，都必须通过已备案的联系人和电话进行第二渠道确认。\n\n财务系统权限按岗位授予，临时权限应设置到期时间。员工离职、转岗或长期休假时，财务负责人应确认权限关闭和未完成事项交接。支付密钥、网银令牌和验证码不得在团队群中传递。"),
    ]
    finance_tables = [("常见财务申请审批矩阵", [
        ["申请类型", "金额范围", "业务审批", "财务处理"],
        ["普通费用", "低于 5,000 元", "直属主管", "共享中心初审"],
        ["项目采购", "5,000-50,000 元", "部门负责人 + 采购", "合同与预算复核"],
        ["重大采购", "超过 50,000 元", "部门负责人 + 采购 + 法务", "三方报价与付款计划"],
        ["供应商账户变更", "不以金额区分", "业务负责人确认", "主数据和第二渠道核验"],
        ["红字发票", "不以金额区分", "业务负责人说明原因", "原发票关联与税务复核"],
    ])]

    build_pdf(OUTPUT / "customer_service_manual.pdf", "客户服务运营手册", "版本 2026.1 · 用于企业知识库解析、表格和引用测试", customer_sections, customer_tables)
    build_pdf(OUTPUT / "finance_shared_service_guide.pdf", "财务共享服务操作指南", "版本 2026.1 · 用于制度问答、审批矩阵和跨页表格测试", finance_sections, finance_tables)


if __name__ == "__main__":
    main()
