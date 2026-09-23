"""Groq provider implementation."""


from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class GroqProvider(LLMProvider):
    name = "groq"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_groq import ChatGroq
        from pydantic import SecretStr

        return ChatGroq(
            model=config.model or "llama-3.3-70b-versatile",
            api_key=SecretStr(config.api_key),
            temperature=config.temperature,
        )


ProviderRegistry.register(GroqProvider())
