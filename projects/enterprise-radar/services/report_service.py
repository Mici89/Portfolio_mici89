import asyncio
from datetime import datetime
from typing import Any, Awaitable

from services.qcc_client import (
    get_company_registration,
    get_company_risk_scan,
    get_company_tool_data,
    get_risk_tool_data,
)
from services.ai_analysis import generate_ai_analysis
from services.risk_scoring import RISK_RULES, calculate_preliminary_risk


COMPANY_DETAIL_TOOLS = {
    "profile": ("企业画像", "get_company_profile"),
    "shareholders": ("股东信息", "get_shareholder_info"),
    "controller": ("实际控制人", "get_actual_controller"),
    "personnel": ("主要人员", "get_key_personnel"),
    "changes": ("工商变更", "get_change_records"),
}


async def _safe(coroutine: Awaitable[Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": await coroutine, "error": None}
    except Exception as error:
        return {"ok": False, "data": None, "error": str(error)}


async def build_company_report(credit_code: str) -> dict[str, Any]:
    keys = ["registration", "risk_scan", *COMPANY_DETAIL_TOOLS.keys()]
    tasks = [
        _safe(get_company_registration(credit_code)),
        _safe(get_company_risk_scan(credit_code)),
        *[
            _safe(get_company_tool_data(tool_name, credit_code))
            for _, tool_name in COMPANY_DETAIL_TOOLS.values()
        ],
    ]
    results = dict(zip(keys, await asyncio.gather(*tasks)))

    registration = results["registration"]["data"]
    risk_scan = results["risk_scan"]["data"]
    if not registration:
        raise RuntimeError(results["registration"]["error"] or "工商信息查询失败")
    if not risk_scan:
        raise RuntimeError(results["risk_scan"]["error"] or "风险扫描失败")

    assessment = calculate_preliminary_risk(risk_scan)
    scored_names = set(RISK_RULES)
    detail_factors = [
        factor
        for factor in risk_scan["factors"]
        if factor["has_records"]
        and factor["name"] in scored_names
        and factor["detail_tool"]
    ]

    risk_detail_results = await asyncio.gather(
        *[
            _safe(get_risk_tool_data(factor["detail_tool"], credit_code))
            for factor in detail_factors
        ]
    )
    risk_details = {
        factor["name"]: {
            "tool": factor["detail_tool"],
            **result,
        }
        for factor, result in zip(detail_factors, risk_detail_results)
    }

    company_details = {
        key: {
            "title": COMPANY_DETAIL_TOOLS[key][0],
            **results[key],
        }
        for key in COMPANY_DETAIL_TOOLS
    }
    errors = [
        {"section": key, "message": value["error"]}
        for key, value in results.items()
        if not value["ok"]
    ]
    errors.extend(
        {"section": name, "message": value["error"]}
        for name, value in risk_details.items()
        if not value["ok"]
    )

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "company": registration,
        "risk_scan": risk_scan,
        "risk_assessment": assessment,
        "company_details": company_details,
        "risk_details": risk_details,
        "errors": errors,
        "methodology": {
            "name": "企信雷达初步风险规则 V1",
            "note": "明确负面因子按是否命中计分；诉讼类计数只作分诊，不直接扣分。",
        },
    }

    try:
        report["ai_analysis"] = {
            "ok": True,
            "data": await generate_ai_analysis(report),
            "error": None,
        }
    except Exception as error:
        report["ai_analysis"] = {
            "ok": False,
            "data": None,
            "error": str(error),
        }

    return report
