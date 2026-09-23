"""LLM Provider abstraction layer (ABC + factory)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel


@dataclass
class LLMConfig:
    """Konfigurasi standar untuk provider LLM."""

    model: str
    temperature: float = 0.7
    api_key: str | None = None
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class untuk provider LLM."""

    name: str = "base"

    @abstractmethod
    def create(self, config: LLMConfig) -> BaseChatModel:
        """Buat instance LLM dari config."""
        pass

    def is_available(self, config: LLMConfig) -> bool:
        """Cek apakah provider ini bisa diinisialisasi dengan config."""
        return bool(config.api_key or not self.requires_api_key())

    @abstractmethod
    def requires_api_key(self) -> bool:
        """Apakah provider ini butuh API key?"""
        pass


class ProviderRegistry:
    """Registry untuk mendaftarkan dan mencari provider."""

    _providers: ClassVar[dict[str, LLMProvider]] = {}

    @classmethod
    def register(cls, provider: LLMProvider) -> None:
        cls._providers[provider.name.lower()] = provider

    @classmethod
    def get(cls, name: str) -> LLMProvider | None:
        return cls._providers.get(name.lower())

    @classmethod
    def list(cls) -> list[str]:
        return list(cls._providers.keys())
