import json

from services.risk_scoring import calculate_preliminary_risk


sample_risk_scan = {
    "company_name": "测试企业",
    "factors": [
        {
            "name": "失信信息",
            "count": 1,
            "detail_tool": "get_dishonest_info",
            "has_records": True,
        },
        {
            "name": "经营异常",
            "count": 2,
            "detail_tool": "get_business_exception",
            "has_records": True,
        },
        {
            "name": "裁判文书",
            "count": 100,
            "detail_tool": "get_judicial_documents",
            "has_records": True,
        },
        {
            "name": "行政处罚",
            "count": 0,
            "detail_tool": "get_administrative_penalty",
            "has_records": False,
        },
    ],
}


result = calculate_preliminary_risk(
    sample_risk_scan
)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    )
)