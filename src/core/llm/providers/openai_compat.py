"""OpenAI-compatible providers (Cohere, DeepSeek, Moonshot, Minimax, OpenRouter, Grok/XAI, ZAI/GLM, Meta, Generic)."""

from abc import abstractmethod

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.core.llm.providers import LLMConfig, LLMProvider, ProviderRegistry


class OpenAICompatibleProvider(LLMProvider):
    """Base class untuk provider yang kompatibel OpenAI API."""

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        return ChatOpenAI(
            model=config.model or self.default_model,
            api_key=SecretStr(config.api_key),
            base_url=config.base_url or self.default_base_url,
            temperature=config.temperature,
        )

    @property
    @abstractmethod
    def default_model(self) -> str:
        pass

    @property
    @abstractmethod
    def default_base_url(self) -> str:
        pass


class CohereProvider(OpenAICompatibleProvider):
    name = "cohere"
    default_model = "command-a-03-2025"
    default_base_url = "https://api.cohere.ai/v1"


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    default_model = "deepseek-chat"
    default_base_url = "https://api.deepseek.com"


class MoonshotProvider(OpenAICompatibleProvider):
    name = "moonshot"
    default_model = "kimi-k2"
    default_base_url = "https://api.moonshot.ai/v1"


class MinimaxProvider(OpenAICompatibleProvider):
    name = "minimax"
    default_model = "MiniMax-M2"
    default_base_url = "https://api.minimax.io/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    default_model = "meta-llama/llama-3.3-70b-instruct"
    default_base_url = "https://openrouter.ai/api/v1"


class GrokProvider(OpenAICompatibleProvider):
    name = "grok"
    default_model = "grok-4"
    default_base_url = "https://api.x.ai/v1"


class XAIProvider(OpenAICompatibleProvider):
    name = "xai"
    default_model = "grok-4"
    default_base_url = "https://api.x.ai/v1"


class ZAIProvider(OpenAICompatibleProvider):
    name = "zai"
    default_model = "glm-4.5"
    default_base_url = "https://api.z.ai/api/paas/v4"


class GLMProvider(OpenAICompatibleProvider):
    name = "glm"
    default_model = "glm-4.5"
    default_base_url = "https://api.z.ai/api/paas/v4"


class ZhipuProvider(OpenAICompatibleProvider):
    name = "zhipu"
    default_model = "glm-4.5"
    default_base_url = "https://api.z.ai/api/paas/v4"


class MetaProvider(OpenAICompatibleProvider):
    name = "meta"
    default_model = "Llama-4-Maverick-17B-128E-Instruct-FP8"
    default_base_url = "https://api.llama.com/v1"


class GenericProvider(LLMProvider):
    """Generic OpenAI-compatible provider: butuh <NAMA>_API_KEY + <NAMA>_BASE_URL + LLM_MODEL."""

    name = "generic"

    def requires_api_key(self) -> bool:
        return True

    def create(self, config: LLMConfig) -> BaseChatModel:
        return ChatOpenAI(
            model=config.model,
            api_key=SecretStr(config.api_key or "not-needed"),
            base_url=config.base_url,
            temperature=config.temperature,
        )


# Register all
ProviderRegistry.register(CohereProvider())
ProviderRegistry.register(DeepSeekProvider())
ProviderRegistry.register(MoonshotProvider())
ProviderRegistry.register(MinimaxProvider())
ProviderRegistry.register(OpenRouterProvider())
ProviderRegistry.register(GrokProvider())
ProviderRegistry.register(XAIProvider())
ProviderRegistry.register(ZAIProvider())
ProviderRegistry.register(GLMProvider())
ProviderRegistry.register(ZhipuProvider())
ProviderRegistry.register(MetaProvider())
ProviderRegistry.register(GenericProvider())
