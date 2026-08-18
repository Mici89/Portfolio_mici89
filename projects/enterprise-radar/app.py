import asyncio

import streamlit as st

from config import QCC_API_KEY, QCC_COMPANY_MCP_URL, QCC_RISK_MCP_URL
from services.qcc_client import search_companies
from services.report_service import build_company_report
from ui.report_view import render_company_report


st.set_page_config(page_title="企信雷达", page_icon="🔍", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 2rem; padding-bottom: 4rem;}
    [data-testid="stMetric"] {background: #f7f9fc; border: 1px solid #e5eaf1; padding: 14px; border-radius: 12px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("企信雷达")
st.caption("确认企业主体，生成可解释的企业风险报告")

with st.sidebar:
    st.subheader("系统状态")
    st.write("API Key", "✅ 已配置" if QCC_API_KEY else "❌ 未配置")
    st.write("企业信息服务", "✅ 已配置" if QCC_COMPANY_MCP_URL else "❌ 未配置")
    st.write("风险信息服务", "✅ 已配置" if QCC_RISK_MCP_URL else "❌ 未配置")
    st.divider()
    st.caption("数据来自企查查智能体数据平台。评分为本项目规则生成，不是企查查官方评分。")

for key, default in {
    "candidates": [],
    "selected_company": None,
    "report": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.form("company_search", clear_on_submit=False):
    keyword = st.text_input(
        "企业名称、简称或股票简称",
        placeholder="例如：小米、企查查",
    )
    search_submitted = st.form_submit_button("搜索企业", type="primary")

if search_submitted:
    if not keyword.strip():
        st.warning("请先输入企业名称")
    else:
        try:
            with st.spinner("正在匹配企业主体……"):
                st.session_state.candidates = asyncio.run(search_companies(keyword.strip()))
            st.session_state.selected_company = None
            st.session_state.report = None
            if not st.session_state.candidates:
                st.warning("没有找到匹配企业，请检查关键词。")
        except Exception as error:
            st.error(f"企业搜索失败：{error}")

candidates = st.session_state.candidates
if candidates:
    st.subheader("确认企业主体")
    st.caption("必须人工确认正确主体，系统不会自动选择第一条结果。")
    selected_index = st.selectbox(
        "候选企业",
        options=range(len(candidates)),
        index=None,
        placeholder="请选择正确企业",
        format_func=lambda index: (
            f"{candidates[index]['name']} ｜ {candidates[index]['status']} ｜ "
            f"{candidates[index]['credit_code']}"
        ),
    )

    if selected_index is not None:
        selected = candidates[selected_index]
        info_cols = st.columns(4)
        info_cols[0].metric("企业名称", selected["name"])
        info_cols[1].metric("状态", selected["status"] or "暂无")
        info_cols[2].metric("成立日期", selected["established_date"] or "暂无")
        info_cols[3].metric(
            "法定代表人",
            "、".join(selected["legal_representatives"]) or "暂无",
        )

        if st.button("生成风险报告", type="primary", use_container_width=True):
            try:
                with st.spinner("正在查询工商、股权、治理与风险数据，请稍候……"):
                    report = asyncio.run(build_company_report(selected["credit_code"]))
                st.session_state.selected_company = selected
                st.session_state.report = report
                st.success("风险报告生成完成")
            except Exception as error:
                st.error(f"报告生成失败：{error}")

if st.session_state.report:
    render_company_report(st.session_state.report)
