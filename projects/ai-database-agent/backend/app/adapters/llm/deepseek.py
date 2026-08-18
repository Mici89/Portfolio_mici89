import json
from typing import Any

import httpx

from app.adapters.llm.base import BaseLLMClient, LLMJsonResult
from app.core.exceptions import LLMProviderError, LLMResponseValidationError
from app.models import LLMTokenUsage


class DeepSeekLLMClient(BaseLLMClient):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        temperature: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
                response.raise_for_status()
        except httpx.TimeoutException:
            raise LLMProviderError("大模型服务响应超时") from None
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                message = "大模型服务身份验证失败"
            elif status_code == 429:
                message = "大模型服务请求过于频繁"
            else:
                message = f"大模型服务返回错误状态：{status_code}"
            raise LLMProviderError(message) from None
        except httpx.HTTPError:
            raise LLMProviderError("无法连接到大模型服务") from None

        try:
            body = response.json()
            content_text = body["choices"][0]["message"]["content"]
            content = self._parse_json_object(content_text)
            usage_data = body.get("usage") or {}
            usage = LLMTokenUsage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                completion_tokens=int(usage_data.get("completion_tokens", 0)),
                total_tokens=int(usage_data.get("total_tokens", 0)),
            )
            response_model = str(body.get("model") or self.model)
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMResponseValidationError() from None

        return LLMJsonResult(
            content=content,
            provider="deepseek",
            model=response_model,
            usage=usage,
        )

    @staticmethod
    def _parse_json_object(content: Any) -> dict[str, Any]:
        if not isinstance(content, str):
            raise LLMResponseValidationError()
        cleaned = content.strip()
        if cleaned.startswith("```"):
            first_line_end = cleaned.find("\n")
            cleaned = cleaned[first_line_end + 1 :] if first_line_end >= 0 else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            raise LLMResponseValidationError("大模型没有返回有效JSON") from None
        if not isinstance(parsed, dict):
            raise LLMResponseValidationError("大模型返回结果必须是JSON对象")
        return parsed
