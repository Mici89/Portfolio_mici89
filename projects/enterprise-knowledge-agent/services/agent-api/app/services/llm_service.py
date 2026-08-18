from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings


class GenerationError(RuntimeError):
    pass


@lru_cache
def get_deepseek_client() -> OpenAI:
    settings = get_settings()

    if settings.deepseek_api_key is None:
        raise GenerationError("DeepSeek API key is not configured")

    return OpenAI(
        api_key=settings.deepseek_api_key.get_secret_value(),
        base_url=settings.deepseek_base_url,
    )


def generate_answer(
    *,
    question: str,
    contexts: list[str],
) -> str:
    settings = get_settings()

    context_text = "\n\n".join(
        f"[资料 {index}]\n{content}"
        for index, content in enumerate(contexts, start=1)
    )

    try:
        response = get_deepseek_client().chat.completions.create(
            model=settings.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是企业知识库助手。"
                        "只能根据提供的资料回答问题，不得编造信息。"
                        "如果资料不足，请回答："
                        "根据现有知识库资料，无法回答该问题。"
                        "请使用 [资料 1] 这样的标记注明答案依据。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"资料：\n{context_text}\n\n"
                        f"问题：{question}"
                    ),
                },
            ],
            max_tokens=500,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
        )
    except Exception as error:
        raise GenerationError(
            "Failed to generate answer with DeepSeek"
        ) from error

    answer = response.choices[0].message.content

    if answer is None or not answer.strip():
        raise GenerationError("DeepSeek returned an empty answer")

    return answer.strip()