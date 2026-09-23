"""Google provider implementation."""


from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class GoogleProvider(LLMProvider):
    name = "google"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model or "gemini-3.5-flash-lite",
            google_api_key=config.api_key,
            temperature=config.temperature,
        )


ProviderRegistry.register(GoogleProvider())
