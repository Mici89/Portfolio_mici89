import json
from typing import Any

import httpx

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from services.risk_scoring import RISK_RULES


SCORING_STANDARD_VERSION = "企信雷达固定评分标准 V1.0"


SYSTEM_PROMPT = """你是一家大型企业风控部门的负责人，负责审阅交易相对方的企业尽调报告。

必须遵守以下规则：
1. 只能依据用户提供的结构化数据分析，不得补充、猜测或引用外部事实。
2. 风险分和风险等级已经由固定规则引擎计算。必须逐字引用，不得重新计算、调整或建议修改。
3. 裁判文书、立案、开庭、法院公告、送达公告等计数只表示存在记录。在没有角色、金额和案件状态明细时，不得认定企业违法、败诉或违约。
4. “未查询到记录”只能表述为“本次查询未发现记录”，不得表述为“绝对不存在风险”。
5. 明确区分客观事实、风险判断、待核查事项和建议措施。
6. 不输出Markdown，不输出代码块，只输出合法JSON。

输出JSON结构必须为：
{
  "executive_summary": "150至300字的综合意见",
  "decision": "建议通过|有条件通过|建议暂缓|建议拒绝",
  "fixed_score": 0,
  "fixed_level": "低风险|中风险|高风险|严重风险",
  "key_risks": [{"title": "", "evidence": "", "severity": "低|中|高"}],
  "positive_signals": [{"title": "", "evidence": ""}],
  "due_diligence_actions": ["下一步核查事项"],
  "risk_controls": ["如果继续合作，应采取的风控措施"],
  "limitations": ["数据或结论限制"]
}
"""


def _build_user_prompt(report: dict[str, Any]) -> str:
    assessment = report["risk_assessment"]
    scoring_rules = {
        "standard": SCORING_STANDARD_VERSION,
        "factor_points": RISK_RULES,
        "level_thresholds": {
            "低风险": "0-19",
            "中风险": "20-49",
            "高风险": "50-79",
            "严重风险": "80-100",
        },
        "fixed_score": assessment["score"],
        "fixed_level": assessment["level"],
        "instruction": "必须原样返回fixed_score和fixed_level，不得重新评分。",
    }
    source_data = {
        "company": report["company"],
        "risk_scan": report["risk_scan"],
        "risk_assessment": assessment,
        "company_details": report["company_details"],
        "risk_details": report["risk_details"],
        "query_errors": report["errors"],
    }
    return (
        "请按照固定评分标准，以风控部门负责人身份给出综合意见。\n\n"
        "固定评分标准：\n"
        + json.dumps(scoring_rules, ensure_ascii=False, indent=2)
        + "\n\n全部查询结果：\n"
        + json.dumps(source_data, ensure_ascii=False, indent=2)
    )


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise RuntimeError("DeepSeek没有返回JSON对象")
    return parsed


async def generate_ai_analysis(report: dict[str, Any]) -> dict[str, Any]:
    assessment = report["risk_assessment"]
    request_body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(report)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 2400,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(90)) as client:
        response = await client.post(
            DEEPSEEK_BASE_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY.strip()}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()

    body = response.json()
    content = body["choices"][0]["message"]["content"]
    analysis = _parse_json_content(content)

    # 评分始终以规则引擎为准，防止模型输出漂移。
    analysis["fixed_score"] = assessment["score"]
    analysis["fixed_level"] = assessment["level"]
    analysis["scoring_standard"] = SCORING_STANDARD_VERSION

    for key in (
        "key_risks",
        "positive_signals",
        "due_diligence_actions",
        "risk_controls",
        "limitations",
    ):
        if not isinstance(analysis.get(key), list):
            analysis[key] = []
    if analysis.get("decision") not in {
        "建议通过",
        "有条件通过",
        "建议暂缓",
        "建议拒绝",
    }:
        analysis["decision"] = "有条件通过"
    analysis.setdefault("executive_summary", "大模型未返回综合意见。")
    return analysis
