"""Ollama provider implementation."""


from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class OllamaProvider(LLMProvider):
    name = "ollama"

    def requires_api_key(self) -> bool:
        return False

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.model or "llama3.1:8b",
            temperature=config.temperature,
        )


ProviderRegistry.register(OllamaProvider())
