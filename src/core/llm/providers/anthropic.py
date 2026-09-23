"""Anthropic provider implementation."""


from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        from pydantic import SecretStr

        kwargs = {
            "model": config.model or "claude-sonnet-4-5",
            "api_key": SecretStr(config.api_key),
            "temperature": config.temperature,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatAnthropic(**kwargs)


ProviderRegistry.register(AnthropicProvider())
