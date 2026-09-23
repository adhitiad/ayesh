"""OpenAI provider implementation."""

from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class OpenAIProvider(LLMProvider):
    name = "openai"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        return ChatOpenAI(
            model=config.model or "gpt-4o-mini",
            api_key=SecretStr(config.api_key),
            base_url=config.base_url,
            temperature=config.temperature,
        )


ProviderRegistry.register(OpenAIProvider())
