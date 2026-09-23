"""LLM Factory: inisialisasi LLM dengan fallback otomatis menggunakan ProviderRegistry."""

import logging
import os
import warnings
from typing import Any

from dotenv import load_dotenv

from src.core.llm.providers import LLMConfig, ProviderRegistry

load_dotenv()

# Redam noise yang aman diabaikan:
warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*")


class _DropAfcNotice(logging.Filter):
    """Buang notifikasi AFC sekali-per-proses; eksekusi tool memang ditangani LangGraph."""

    def filter(self, record):
        return "Direct use of automatic function calling" not in record.getMessage()


logging.getLogger("google_genai.models").addFilter(_DropAfcNotice())

# Import providers to register them
from src.core.llm.providers import (  # noqa: E402,F401
    anthropic,
    google,
    groq,
    nvidia,
    ollama,
    openai,
    openai_compat,
)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").lower()
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# Urutan fallback provider
FALLBACK_ORDER = [
    p.strip().lower() for p in os.getenv("LLM_FALLBACK_ORDER", "nvidia,groq,google,ollama").split(",") if p.strip()
]

# Nama native tool Gemini yang didukung (server-side, tanpa eksekusi lokal).
NATIVE_TOOLS = ("google_search", "code_execution", "url_context")

_llm_cache: dict[str, Any] = {}
_active_provider: str | None = None


def get_active_provider() -> str:
    """Provider LLM efektif saat ini."""
    return _active_provider or LLM_PROVIDER


def _build_config(provider_name: str) -> LLMConfig | None:
    """Bangun LLMConfig dari env untuk provider tertentu."""
    provider = provider_name.lower()

    # Map provider ke env var names
    if provider in ProviderRegistry._providers:
        prov = ProviderRegistry._providers[provider]
        if hasattr(prov, "default_model"):  # OpenAICompatibleProvider
            default_model = getattr(prov, "default_model", "")
            default_url = getattr(prov, "default_base_url", "")
        else:
            # Special handling for base providers
            defaults = {
                "nvidia": ("meta/llama-3.1-8b-instruct", "https://integrate.api.nvidia.com/v1"),
                "groq": ("llama-3.3-70b-versatile", None),
                "google": ("gemini-3.5-flash-lite", None),
                "openai": ("gpt-4o-mini", None),
                "anthropic": ("claude-sonnet-4-5", None),
                "ollama": ("llama3.1:8b", None),
            }
            default_model, default_url = defaults.get(provider, ("", None))

        # Env var prefixes
        key_env_map = {
            "nvidia": "NVIDIA_API_KEY",
            "groq": "GROQ_API_KEY",
            "google": "GOOGLE_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "cohere": "COHERE_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "minimax": "MINIMAX_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "grok": "XAI_API_KEY",
            "xai": "XAI_API_KEY",
            "zai": "ZAI_API_KEY",
            "glm": "ZAI_API_KEY",
            "zhipu": "ZAI_API_KEY",
            "meta": "META_API_KEY",
            "ollama": None,
        }

        key_env = key_env_map.get(provider)
        if provider == "ollama":
            api_key = None
        elif provider == "generic":
            # Generic handled below — skip early key check
            api_key = None
        else:
            api_key = os.getenv(key_env, "")
            if (
                not api_key
                or api_key.startswith("your_")
                or api_key.lower().strip()
                in {
                    "sk-xxx",
                    "replace_me",
                    "changeme",
                    "api_key_here",
                    "dummy",
                    "placeholder",
                    "xxx",
                }
            ):
                return None

        base_url = os.getenv(f"{provider.upper()}_BASE_URL") or default_url
        model = LLM_MODEL or default_model

        if provider == "generic":
            # Generic provider: butuh API_KEY + BASE_URL + LLM_MODEL explicit
            prefix = provider.upper().replace("-", "_")
            api_key = os.getenv(f"{prefix}_API_KEY")
            base_url = os.getenv(f"{prefix}_BASE_URL")
            if not base_url or not model:
                return None

        return LLMConfig(
            model=model,
            temperature=LLM_TEMPERATURE,
            api_key=api_key,
            base_url=base_url,
        )

    return None


def get_llm() -> Any:
    """Inisialisasi LLM dengan fallback otomatis. Cache instance per provider."""
    global _active_provider

    primary = LLM_PROVIDER
    order = [primary] + [p for p in FALLBACK_ORDER if p != primary]

    for provider in order:
        if provider in _llm_cache:
            _active_provider = provider
            return _llm_cache[provider]

        config = _build_config(provider)
        if config is None:
            continue

        prov_cls = ProviderRegistry.get(provider)
        if prov_cls is None:
            continue

        try:
            llm = prov_cls.create(config)
            _llm_cache[provider] = llm
            _active_provider = provider
            logging.getLogger("llm_factory").info(f"LLM provider aktif: {provider}")
            return llm
        except Exception as e:
            logging.getLogger("llm_factory").warning(f"Provider {provider} gagal init: {e}")

    raise RuntimeError(f"Tidak ada provider LLM yang tersedia. Cek API keys untuk: {', '.join(order)}")


def get_llm_for_user(user_llm_config=None):
    """Inisialisasi LLM pakai config user. Bila user config kosong/incomplete, fallback ke global.

    user_llm_config: UserLLMConfig atau dict dengan key provider, api_key, model, temperature.
    """
    from src.core.auth.auth_context import UserLLMConfig

    if user_llm_config is None:
        return get_llm()

    # Normalize ke UserLLMConfig
    if isinstance(user_llm_config, dict):
        user_llm_config = UserLLMConfig(**user_llm_config)

    # Tanpa api_key → fallback global (user belum set key sendiri)
    if not user_llm_config.api_key:
        return get_llm()

    # Validasi API key: reject placeholder
    _PLACEHOLDER_KEYS = {
        "your_*_api_key_here",
        "sk-xxx",
        "replace_me",
        "changeme",
        "api_key_here",
        "insert_key",
        "your-key",
        "test_key",
        "dummy",
        "placeholder",
        "xxx",
    }
    key_lower = (user_llm_config.api_key or "").lower().strip()
    for pat in _PLACEHOLDER_KEYS:
        if pat.replace("*", "") in key_lower or key_lower == pat:
            logging.getLogger("llm_factory").warning(
                "User LLM config: API key adalah placeholder (%s), fallback global", user_llm_config.api_key[:8]
            )
            return get_llm()

    # Deteksi provider dari config user
    provider = (user_llm_config.provider or "").lower().strip()
    if not provider:
        # Coba deteksi dari model name pattern
        model_lower = (user_llm_config.model or "").lower()
        if "gemini" in model_lower:
            provider = "google"
        elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            provider = "openai"
        elif "claude" in model_lower:
            provider = "anthropic"
        elif "llama" in model_lower and user_llm_config.api_key:
            provider = "groq"
        elif "deepseek" in model_lower:
            provider = "deepseek"
        elif "grok" in model_lower:
            provider = "grok"
        else:
            # Tidak bisa deteksi → fallback global
            return get_llm()

    # Bangun config dari user settings
    prov_cls = ProviderRegistry.get(provider)
    if prov_cls is None:
        logging.getLogger("llm_factory").warning("Provider '%s' tidak dikenal untuk user LLM config", provider)
        return get_llm()

    # Default model per provider
    _provider_defaults = {
        "nvidia": "meta/llama-3.1-8b-instruct",
        "groq": "llama-3.3-70b-versatile",
        "google": "gemini-3.5-flash-lite",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-5",
        "ollama": "llama3.1:8b",
    }

    model = user_llm_config.model or _provider_defaults.get(provider, "")
    temperature = user_llm_config.temperature if user_llm_config.temperature is not None else LLM_TEMPERATURE

    config = LLMConfig(
        model=model,
        temperature=temperature,
        api_key=user_llm_config.api_key,
        base_url=user_llm_config.provider,  # placeholder, resolved below
    )

    # Resolve base_url per provider
    if provider == "ollama":
        config.base_url = None
    elif provider in ("nvidia",):
        config.base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    else:
        # OpenAI-compatible: cek env BASE_URL atau default provider
        prefix = provider.upper().replace("-", "_")
        config.base_url = os.getenv(f"{prefix}_BASE_URL") or None

    try:
        llm = prov_cls.create(config)
        logging.getLogger("llm_factory").info("LLM user aktif: provider=%s model=%s", provider, model)
        return llm
    except Exception as e:
        logging.getLogger("llm_factory").warning("Provider user '%s' gagal init: %s", provider, e)
        # Coba fallback chain jika ada
        if user_llm_config.fallback_config_ids:
            import json

            try:
                fallback_ids = json.loads(user_llm_config.fallback_config_ids)
            except json.JSONDecodeError, TypeError:
                fallback_ids = []
            for fb_id in fallback_ids:
                try:
                    from src.core.auth.auth_keys import get_user_llm_config_by_id

                    fb_cfg = get_user_llm_config_by_id(getattr(user_llm_config, "user_id", "") or "", fb_id)
                    if fb_cfg and fb_cfg.get("api_key"):
                        fb = get_llm_for_user(UserLLMConfig(**fb_cfg))
                        if fb is not None:
                            logging.getLogger("llm_factory").info(
                                "LLM user fallback ke config %s: %s:%s", fb_id, fb_cfg["provider"], fb_cfg["model"]
                            )
                            return fb
                except Exception as fb_err:
                    logging.getLogger("llm_factory").debug("Fallback config %s gagal: %s", fb_id, fb_err)
                    continue
        logging.getLogger("llm_factory").warning("Semua fallback gagal, menggunakan global LLM")
        return get_llm()


def _parse_native_tool_names(raw: str, strict: bool) -> list:
    """Ubah string comma-separated jadi daftar nama native tool yang valid & unik."""
    selected = []
    for name in (n.strip().lower() for n in raw.split(",")):
        if not name:
            continue
        if name not in NATIVE_TOOLS:
            if strict:
                raise ValueError(f"Native tool '{name}' tidak dikenal. Pilihan: {', '.join(NATIVE_TOOLS)}")
            logging.getLogger("llm_factory").warning(
                f"Native tool '{name}' di GOOGLE_NATIVE_TOOLS tidak dikenal, dilewati."
            )
            continue
        if name not in selected:
            selected.append(name)
    return selected


def _is_google_llm(llm) -> bool:
    """True bila llm adalah chat model langchain-google-genai (pemaham native tool)."""
    module = getattr(type(llm), "__module__", "") or ""
    return module.startswith("langchain_google_genai")


def get_native_tools(names: str | None = None):
    """Tools native Gemini (server-side, tanpa eksekusi lokal)."""
    raw = names if names is not None else os.getenv("GOOGLE_NATIVE_TOOLS", "")
    selected = _parse_native_tool_names(raw, strict=names is not None)
    if not selected:
        return []
    if get_active_provider() != "google":
        return []

    try:
        from google.genai import types
    except ImportError as e:
        logging.getLogger("llm_factory").warning(f"google-genai tidak tersedia, native tools dimatikan: {e}")
        return []

    builders = {
        "google_search": lambda: types.Tool(google_search=types.GoogleSearch()),
        "code_execution": lambda: types.Tool(code_execution=types.ToolCodeExecution()),
        "url_context": lambda: types.Tool(url_context=types.UrlContext()),
    }
    return [builders[name]() for name in selected]


def bind_native_tools(llm, names: str | None = None):
    """Return llm yang di-bind native tools; llm asli bila tidak ada yang dipilih."""
    tools = get_native_tools(names)
    if not tools:
        return llm
    if not _is_google_llm(llm):
        logging.getLogger("llm_factory").warning(
            "Native tool Gemini diminta, tapi LLM aktif bukan ChatGoogleGenerativeAI; binding dilewati."
        )
        return llm
    return llm.bind_tools(tools)
