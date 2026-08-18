import re


email_pattern = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

mobile_pattern = re.compile(
    r"(?<!\d)1[3-9]\d{9}(?!\d)"
)

id_card_pattern = re.compile(
    r"(?<!\d)\d{17}[\dXx](?!\d)"
)

wechat_pattern = re.compile(
    r"(微[\s\u3000]*信[\s\u3000]*[：:][\s\u3000]*)"
    r"[A-Za-z][A-Za-z0-9_-]{5,19}",
    re.IGNORECASE,
)

def redact_personal_information(text: str) -> str:
    text = email_pattern.sub("[邮箱已脱敏]", text)
    text = mobile_pattern.sub("[手机号已脱敏]", text)
    text = id_card_pattern.sub("[身份证号已脱敏]", text)
    text = wechat_pattern.sub(
        r"\1[微信号已脱敏]",
        text,
    )

    return text