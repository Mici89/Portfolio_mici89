RISK_RULES = {
    "失信信息": 40,
    "被执行人": 25,
    "限制高消费": 30,
    "终本案件": 35,
    "破产重整": 40,
    "严重违法": 35,
    "注销备案": 40,
    "清算信息": 35,
    "税务非正常户": 25,
    "税收违法": 25,
    "欠税公告": 20,
    "经营异常": 15,
    "股权冻结": 20,
    "行政处罚": 10,
    "违约事项": 35,
}


ATTENTION_FACTORS = {
    "裁判文书",
    "立案信息",
    "开庭公告",
    "法院公告",
    "送达公告",
    "诉前调解",
    "劳动仲裁",
    "股权出质",
    "股权质押",
    "动产抵押",
    "土地抵押",
    "担保信息",
}


def get_risk_level(score: int) -> str:
    if score >= 80:
        return "严重风险"

    if score >= 50:
        return "高风险"

    if score >= 20:
        return "中风险"

    return "低风险"


def calculate_preliminary_risk(
    risk_scan: dict,
) -> dict:
    score = 0
    reasons = []
    attention_items = []

    for factor in risk_scan.get("factors", []):
        name = factor.get("name", "")
        count = int(factor.get("count", 0) or 0)

        if count <= 0:
            continue

        if name in RISK_RULES:
            points = RISK_RULES[name]
            score += points

            reasons.append(
                {
                    "factor": name,
                    "count": count,
                    "points": points,
                    "description": (
                        f"{name}存在{count}条当前记录"
                    ),
                }
            )

        elif name in ATTENTION_FACTORS:
            attention_items.append(
                {
                    "factor": name,
                    "count": count,
                    "description": (
                        f"{name}存在{count}条记录，"
                        "需要结合角色、金额、时间和状态进一步核查"
                    ),
                }
            )

        else:
            attention_items.append(
                {
                    "factor": name,
                    "count": count,
                    "description": (
                        f"{name}存在{count}条记录，"
                        "当前规则尚未自动评分"
                    ),
                }
            )

    score = min(score, 100)
    level = get_risk_level(score)

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "attention_items": attention_items,
        "scored_factor_count": len(reasons),
        "attention_factor_count": len(attention_items),
        "disclaimer": (
            "该评分是企信雷达根据当前风险因子生成的初步评分，"
            "不是企查查官方评分，也不能替代人工尽调。"
        ),
    }