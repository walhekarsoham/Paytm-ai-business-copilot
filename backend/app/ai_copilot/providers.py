import json
from typing import Protocol

import httpx
from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai_copilot.prompts import SYSTEM_PROMPT
from app.ai_copilot.schemas import MerchantBusinessContext, ProviderAnalysis


class AIProviderError(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    def analyze(self, context: MerchantBusinessContext, evidence_keys: list[str], question: str | None) -> ProviderAnalysis:
        ...


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="AI_", extra="ignore")

    provider: str = Field(default="rules", pattern="^(rules|openai-compatible)$")
    api_key: SecretStr | None = None
    model: str = "gpt-4o-mini"
    base_url: AnyHttpUrl = AnyHttpUrl("https://api.openai.com/v1")
    timeout_seconds: float = Field(default=20, gt=0, le=120)


ai_settings = AISettings()


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, settings: AISettings):
        if settings.api_key is None or not settings.api_key.get_secret_value().strip():
            raise AIProviderError("AI_PROVIDER is openai-compatible but AI_API_KEY is not configured on the backend.")
        self._settings = settings

    def analyze(self, context: MerchantBusinessContext, evidence_keys: list[str], question: str | None) -> ProviderAnalysis:
        payload = context.model_dump(mode="json", by_alias=True)
        payload.get("merchant", {}).pop("id", None)
        user_message = {
            "question": question,
            "allowed_evidence_keys": evidence_keys,
            "merchant_context": payload,
        }
        base_url = str(self._settings.base_url).rstrip("/")
        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.api_key.get_secret_value()}", "Content-Type": "application/json"},
                json={
                    "model": self._settings.model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(user_message, ensure_ascii=True)},
                    ],
                },
                timeout=self._settings.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return ProviderAnalysis.model_validate_json(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise AIProviderError("The configured AI provider could not return a valid structured analysis.") from error


def configured_provider() -> AIProvider | None:
    if ai_settings.provider == "rules":
        return None
    return OpenAICompatibleProvider(ai_settings)