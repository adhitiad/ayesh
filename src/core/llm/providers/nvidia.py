"""NVIDIA provider implementation."""


from langchain_core.language_models import BaseChatModel

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class NVIDIAProvider(LLMProvider):
    name = "nvidia"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(
            model=config.model or "meta/llama-3.1-8b-instruct",
            api_key=config.api_key,
            base_url=config.base_url or "https://integrate.api.nvidia.com/v1",
            temperature=config.temperature,
        )


# Register on import
ProviderRegistry.register(NVIDIAProvider())
