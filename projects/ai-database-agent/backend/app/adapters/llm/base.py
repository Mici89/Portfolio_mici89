from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.models import LLMTokenUsage


@dataclass(frozen=True, slots=True)
class LLMJsonResult:
    content: dict[str, Any]
    provider: str
    model: str
    usage: LLMTokenUsage


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResult:
        """Generate one JSON object without exposing provider details upstream."""
