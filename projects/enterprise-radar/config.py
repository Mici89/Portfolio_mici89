import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"缺少环境变量：{name}")

    return value


QCC_API_KEY = get_required_env("QCC_API_KEY")
QCC_COMPANY_MCP_URL = get_required_env("QCC_COMPANY_MCP_URL")
QCC_RISK_MCP_URL = get_required_env("QCC_RISK_MCP_URL")
DEEPSEEK_API_KEY = get_required_env("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com/chat/completions",
)
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
