import json
from typing import Any

import streamlit as st

from services.pdf_report import generate_pdf_report


def _display_value(value: Any) -> str:
    if value in (None, "", []):
        return "暂无数据"
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def render_risk_assessment(assessment: dict[str, Any]) -> None:
    score_col, level_col, review_col = st.columns(3)
    score_col.metric("风险分", f"{assessment['score']} / 100")
    level_col.metric("风险等级", assessment["level"])
    review_col.metric("待核查维度", assessment["attention_factor_count"])

    messages = {
        "严重风险": (st.error, "命中严重风险规则，建议暂停并进行人工核查。"),
        "高风险": (st.error, "风险较高，建议谨慎合作并进行专项核查。"),
        "中风险": (st.warning, "存在需要关注的风险，建议人工复核。"),
        "低风险": (st.success, "当前明确负面风险因子的初步评分较低。"),
    }
    renderer, message = messages[assessment["level"]]
    renderer(message)
    st.caption(assessment["disclaimer"])

    if assessment["reasons"]:
        st.write("**风险扣分原因**")
        st.dataframe(
            [
                {
                    "风险因子": item["factor"],
                    "记录数": item["count"],
                    "分值": item["points"],
                    "说明": item["description"],
                }
                for item in assessment["reasons"]
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_ai_analysis(ai_result: dict[str, Any]) -> None:
    st.subheader("风控负责人综合意见")
    if not ai_result["ok"]:
        st.warning(f"大模型综合分析暂不可用：{ai_result['error']}")
        return

    analysis = ai_result["data"]
    decision_col, score_col, level_col = st.columns(3)
    decision_col.metric("综合建议", analysis["decision"])
    score_col.metric("固定规则评分", f"{analysis['fixed_score']} / 100")
    level_col.metric("固定风险等级", analysis["fixed_level"])
    st.write(analysis["executive_summary"])
    st.caption(f"评分标准：{analysis['scoring_standard']}。大模型无权修改规则评分。")

    if analysis["key_risks"]:
        st.write("**重点风险**")
        st.dataframe(analysis["key_risks"], use_container_width=True, hide_index=True)
    if analysis["positive_signals"]:
        st.write("**积极信号**")
        st.dataframe(analysis["positive_signals"], use_container_width=True, hide_index=True)

    action_col, control_col = st.columns(2)
    with action_col:
        st.write("**建议补充核查**")
        for item in analysis["due_diligence_actions"]:
            st.write(f"- {item}")
    with control_col:
        st.write("**建议风控措施**")
        for item in analysis["risk_controls"]:
            st.write(f"- {item}")
    if analysis["limitations"]:
        with st.expander("分析限制"):
            for item in analysis["limitations"]:
                st.write(f"- {item}")


def render_registration(data: dict[str, str]) -> None:
    st.subheader("工商登记信息")
    cols = st.columns(3)
    fields = [
        ("法定代表人", "legal_representative"),
        ("成立日期", "established_date"),
        ("注册资本", "registered_capital"),
        ("实缴资本", "paid_in_capital"),
        ("企业类型", "company_type"),
        ("所属行业", "industry"),
        ("所属地区", "region"),
        ("人员规模", "staff_size"),
        ("参保人数", "insured_count"),
    ]
    for index, (label, key) in enumerate(fields):
        with cols[index % 3]:
            st.write(f"**{label}**")
            st.write(_display_value(data.get(key)))

    st.write("**注册地址**")
    st.write(_display_value(data.get("registered_address")))
    st.write("**登记机关**")
    st.write(_display_value(data.get("registration_authority")))
    with st.expander("查看经营范围"):
        st.write(_display_value(data.get("business_scope")))


def render_payload(payload: Any) -> None:
    if payload in (None, {}, []):
        st.info("暂无数据")
        return
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            st.dataframe(payload, use_container_width=True, hide_index=True)
        else:
            st.json(payload, expanded=False)
        return
    if not isinstance(payload, dict):
        st.write(payload)
        return

    scalar_rows = []
    complex_items = []
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            complex_items.append((key, value))
        else:
            scalar_rows.append({"字段": key, "内容": _display_value(value)})
    if scalar_rows:
        st.dataframe(scalar_rows, use_container_width=True, hide_index=True)
    for key, value in complex_items:
        st.write(f"**{key}**")
        render_payload(value)


def render_risk_scan(scan: dict[str, Any], assessment: dict[str, Any]) -> None:
    metric_cols = st.columns(3)
    metric_cols[0].metric("扫描因子", len(scan["factors"]))
    metric_cols[1].metric("有记录", scan["hit_factor_count"])
    metric_cols[2].metric("无记录", scan["clear_factor_count"])

    st.info("风险因子计数只用于分诊；诉讼类记录需结合企业角色、金额和状态判断。")
    hit_factors = [factor for factor in scan["factors"] if factor["has_records"]]
    if hit_factors:
        st.dataframe(
            [
                {
                    "风险因子": factor["name"],
                    "条目数": factor["count"],
                    "处理方式": (
                        "已计入初步评分"
                        if any(reason["factor"] == factor["name"] for reason in assessment["reasons"])
                        else "待进一步核查"
                    ),
                }
                for factor in hit_factors
            ],
            use_container_width=True,
            hide_index=True,
        )
    with st.expander("查看全部35项扫描结果"):
        st.dataframe(
            [{"风险因子": f["name"], "条目数": f["count"]} for f in scan["factors"]],
            use_container_width=True,
            hide_index=True,
        )


def render_company_report(report: dict[str, Any]) -> None:
    company = report["company"]
    st.divider()
    st.title(company["name"])
    st.caption(f"报告生成时间：{report['generated_at']}")

    header_cols = st.columns(3)
    header_cols[0].metric("登记状态", company["registration_status"] or "暂无")
    header_cols[1].metric("统一社会信用代码", company["credit_code"] or "暂无")
    header_cols[2].metric("所属行业", company["industry"] or "暂无")

    overview_tab, registration_tab, governance_tab, risk_tab, raw_tab = st.tabs(
        ["风险结论", "工商信息", "股权与治理", "风险扫描", "完整数据"]
    )

    with overview_tab:
        render_risk_assessment(report["risk_assessment"])
        st.divider()
        render_ai_analysis(report["ai_analysis"])
        if report["risk_assessment"]["attention_items"]:
            st.write("**待核查事项**")
            st.dataframe(
                [
                    {
                        "维度": item["factor"],
                        "记录数": item["count"],
                        "说明": item["description"],
                    }
                    for item in report["risk_assessment"]["attention_items"]
                ],
                use_container_width=True,
                hide_index=True,
            )
        st.caption(report["methodology"]["note"])

    with registration_tab:
        render_registration(company)
        profile = report["company_details"]["profile"]
        st.subheader("企业画像")
        if profile["ok"]:
            render_payload(profile["data"])
        else:
            st.warning(profile["error"])

    with governance_tab:
        for key in ("shareholders", "controller", "personnel", "changes"):
            section = report["company_details"][key]
            with st.expander(section["title"], expanded=key in ("shareholders", "controller")):
                if section["ok"]:
                    render_payload(section["data"])
                else:
                    st.warning(section["error"])

    with risk_tab:
        render_risk_scan(report["risk_scan"], report["risk_assessment"])
        if report["risk_details"]:
            st.subheader("明确负面风险明细")
            for name, detail in report["risk_details"].items():
                with st.expander(name, expanded=True):
                    if detail["ok"]:
                        render_payload(detail["data"])
                    else:
                        st.warning(detail["error"])

    with raw_tab:
        st.json(report, expanded=False)
        if report["errors"]:
            st.warning("部分非关键数据查询失败，基础报告仍可使用。")
            st.dataframe(report["errors"], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("下载报告")
    download_col, note_col = st.columns([1, 2])
    with download_col:
        st.download_button(
            "下载中文PDF报告",
            data=generate_pdf_report(report),
            file_name=f"{company['name']}_风险报告.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
    with note_col:
        st.info("PDF适合阅读、打印和转发，包含结论、企业概况、风险摘要与治理信息。")

    with st.expander("开发者数据"):
        st.caption("JSON用于调试或系统对接，普通用户无需下载。")
        st.download_button(
            "下载JSON原始报告",
            data=json.dumps(report, ensure_ascii=False, indent=2),
            file_name=f"{company['name']}_风险报告.json",
            mime="application/json",
            use_container_width=True,
        )
