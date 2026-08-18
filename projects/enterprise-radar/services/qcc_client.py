import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config import QCC_API_KEY, QCC_COMPANY_MCP_URL, QCC_RISK_MCP_URL


def get_authorization_headers() -> dict[str, str]:
    api_key = QCC_API_KEY.strip()
    authorization = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
    return {"Authorization": authorization}


async def _call_tool(endpoint: str, tool_name: str, arguments: dict[str, Any]):
    timeout = httpx.Timeout(timeout=25, read=90)
    async with httpx.AsyncClient(
        headers=get_authorization_headers(),
        timeout=timeout,
    ) as http_client:
        async with streamable_http_client(
            url=endpoint,
            http_client=http_client,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool(name=tool_name, arguments=arguments)


async def _list_tools(endpoint: str):
    timeout = httpx.Timeout(timeout=25, read=90)
    async with httpx.AsyncClient(
        headers=get_authorization_headers(),
        timeout=timeout,
    ) as http_client:
        async with streamable_http_client(
            url=endpoint,
            http_client=http_client,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return (await session.list_tools()).tools


def extract_tool_payload(result) -> Any:
    if result.isError:
        raise RuntimeError("企查查工具返回错误")

    payloads: list[Any] = []
    for item in result.content:
        if getattr(item, "type", None) != "text":
            continue
        text = item.text.strip()
        if not text:
            continue
        try:
            payloads.append(json.loads(text))
        except json.JSONDecodeError:
            payloads.append({"文本结果": text})

    if not payloads:
        raise RuntimeError("企查查没有返回可解析的数据")
    return payloads[0] if len(payloads) == 1 else payloads


async def list_company_tools():
    return await _list_tools(QCC_COMPANY_MCP_URL)


async def list_risk_tools():
    return await _list_tools(QCC_RISK_MCP_URL)


async def call_company_tool(tool_name: str, arguments: dict[str, Any]):
    return await _call_tool(QCC_COMPANY_MCP_URL, tool_name, arguments)


async def call_risk_tool(tool_name: str, arguments: dict[str, Any]):
    return await _call_tool(QCC_RISK_MCP_URL, tool_name, arguments)


async def get_company_tool_data(tool_name: str, credit_code: str) -> Any:
    result = await call_company_tool(tool_name, {"searchKey": credit_code})
    return extract_tool_payload(result)


async def get_risk_tool_data(
    tool_name: str,
    credit_code: str,
    extra_arguments: dict[str, Any] | None = None,
) -> Any:
    arguments: dict[str, Any] = {"searchKey": credit_code}
    if extra_arguments:
        arguments.update(extra_arguments)
    result = await call_risk_tool(tool_name, arguments)
    return extract_tool_payload(result)


async def search_companies(keyword: str) -> list[dict[str, Any]]:
    result = await call_company_tool("get_company_by_query", {"searchKey": keyword})
    raw_data = extract_tool_payload(result)
    raw_companies = raw_data.get("企业信息", []) if isinstance(raw_data, dict) else []

    companies = []
    for company in raw_companies:
        companies.append(
            {
                "name": str(company.get("企业名称", "")).strip(),
                "credit_code": str(company.get("统一社会信用代码", "")).strip(),
                "established_date": str(company.get("成立日期", "")).strip(),
                "legal_representatives": company.get("法定代表人名称", []),
                "status": str(company.get("状态", "")).strip(),
            }
        )
    return companies


async def get_company_registration(credit_code: str) -> dict[str, str]:
    raw_data = await get_company_tool_data("get_company_registration_info", credit_code)
    if not isinstance(raw_data, dict):
        raise RuntimeError("工商登记信息格式不正确")

    def value(*keys: str) -> str:
        for key in keys:
            if key in raw_data and raw_data[key] is not None:
                return str(raw_data[key]).strip()
        return ""

    return {
        "name": value("企业名称"),
        "credit_code": value("统一社会信用代码"),
        "legal_representative": value("法定代表人"),
        "registration_status": value("登记状态"),
        "established_date": value("成立日期"),
        "registered_capital": value("注册资本"),
        "paid_in_capital": value("实缴资本"),
        "company_type": value("企业类型"),
        "operating_period": value("营业期限"),
        "taxpayer_qualification": value("纳税人资质"),
        "staff_size": value("人员规模"),
        "insured_count": value("参保人数", "参 保人数"),
        "approval_date": value("核准日期"),
        "region": value("所属地区"),
        "registration_authority": value("登记机关"),
        "industry": value("国标行业"),
        "short_name": value("企业简称"),
        "english_name": value("英文名"),
        "registered_address": value("注册地址"),
        "mailing_address": value("通信地址"),
        "business_scope": value("经营范围"),
    }


async def get_company_risk_scan(credit_code: str) -> dict[str, Any]:
    raw_data = await get_risk_tool_data("get_company_risk_scan", credit_code)
    if not isinstance(raw_data, dict):
        raise RuntimeError("风险扫描数据格式不正确")

    factors = []
    for raw_factor in raw_data.get("风险因子扫描", []):
        factor = {"".join(str(key).split()): value for key, value in raw_factor.items()}
        factor_name = "".join(str(factor.get("风险因子", "")).split())
        count = int(factor.get("条目数", 0) or 0)
        factors.append(
            {
                "name": factor_name,
                "count": count,
                "detail_tool": str(factor.get("明细工具", "")).strip(),
                "has_records": count > 0,
            }
        )

    return {
        "company_name": str(raw_data.get("企业名称", "")).strip(),
        "summary": str(raw_data.get("摘要", "")).strip(),
        "hit_factor_count": int(raw_data.get("有记录因子数", 0) or 0),
        "clear_factor_count": int(raw_data.get("无记录因子数", 0) or 0),
        "factors": factors,
    }
