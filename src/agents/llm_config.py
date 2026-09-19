"""Konfigurasi LLM terpusat dengan multi-provider fallback."""

import logging
import os
import warnings
from dotenv import load_dotenv

load_dotenv()

# Redam noise yang aman diabaikan:
# 1. flash-lite pakai sampling default; temperature kita diabaikan API (muncul tiap call).
warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*")


class _DropAfcNotice(logging.Filter):
    """Buang notifikasi AFC sekali-per-proses; eksekusi tool memang ditangani LangGraph."""

    def filter(self, record):
        return "Direct use of automatic function calling" not in record.getMessage()


logging.getLogger("google_genai.models").addFilter(_DropAfcNotice())

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia").lower()
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# Urutan fallback provider (isi di .env: LLM_FALLBACK_ORDER=nvidia,groq,google,ollama)
FALLBACK_ORDER = [
    p.strip().lower()
    for p in os.getenv("LLM_FALLBACK_ORDER", "nvidia,groq,google,ollama").split(",")
    if p.strip()
]

# Nama native tool Gemini yang didukung (server-side, tanpa eksekusi lokal).
NATIVE_TOOLS = ("google_search", "code_execution", "url_context")

# Provider OpenAI-compatible: (ENV_API_KEY, ENV_BASE_URL, default_base_url, default_model).
# Model default hanya fallback bila LLM_MODEL kosong — isi LLM_MODEL di .env untuk pasti.
_OPENAI_COMPATIBLE = {
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
                 "https://api.deepseek.com", "deepseek-chat"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL",
                 "https://api.moonshot.ai/v1", "kimi-k2"),
    "minimax": ("MINIMAX_API_KEY", "MINIMAX_BASE_URL",
                "https://api.minimax.io/v1", "MiniMax-M2"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL",
                   "https://openrouter.ai/api/v1",
                   "meta-llama/llama-3.3-70b-instruct"),
    "grok": ("XAI_API_KEY", "XAI_BASE_URL",
             "https://api.x.ai/v1", "grok-4"),
    "xai": ("XAI_API_KEY", "XAI_BASE_URL",
            "https://api.x.ai/v1", "grok-4"),
    "zai": ("ZAI_API_KEY", "ZAI_BASE_URL",
            "https://api.z.ai/api/paas/v4", "glm-4.5"),
    "glm": ("ZAI_API_KEY", "ZAI_BASE_URL",
            "https://api.z.ai/api/paas/v4", "glm-4.5"),
    "zhipu": ("ZAI_API_KEY", "ZAI_BASE_URL",
              "https://api.z.ai/api/paas/v4", "glm-4.5"),
    "meta": ("META_API_KEY", "META_BASE_URL",
             "https://api.llama.com/v1", "Llama-4-Maverick-17B-128E-Instruct-FP8"),
}

_llm_cache = {}
# Provider yang benar-benar aktif (hasil fallback get_llm), bukan sekadar LLM_PROVIDER.
_active_provider = None


def get_active_provider():
    """Provider LLM efektif saat ini.

    Bila get_llm() sudah pernah berhasil, ini provider hasil fallback (bisa berbeda
    dari LLM_PROVIDER). Sebelum itu, nilai LLM_PROVIDER yang dipakai.
    """
    return _active_provider or LLM_PROVIDER


def _init_provider(provider: str):
    """Inisialisasi satu provider LLM, return instance atau None jika gagal."""
    provider = provider.lower().strip()
    try:
        if provider == "nvidia":
            from langchain_nvidia_ai_endpoints import ChatNVIDIA

            api_key = os.getenv("NVIDIA_API_KEY")
            if not api_key or api_key == "your_gemini_api_key_here":
                return None
            model = LLM_MODEL or "meta/llama-3.1-8b-instruct"
            base_url = os.getenv(
                "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
            )
            return ChatNVIDIA(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=LLM_TEMPERATURE,
            )

        elif provider == "groq":
            from langchain_groq import ChatGroq

            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                return None
            model = LLM_MODEL or "llama-3.3-70b-versatile"
            return ChatGroq(model=model, api_key=api_key, temperature=LLM_TEMPERATURE)

        elif provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return None
            model = LLM_MODEL or "gemini-3.5-flash-lite"
            return ChatGoogleGenerativeAI(
                model=model, google_api_key=api_key, temperature=LLM_TEMPERATURE
            )

        elif provider == "openai":
            from langchain_openai import ChatOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            model = LLM_MODEL or "gpt-4o-mini"
            base_url = os.getenv("OPENAI_BASE_URL")
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=LLM_TEMPERATURE,
            )

        elif provider == "ollama":
            from langchain_ollama import ChatOllama

            model = LLM_MODEL or "llama3.1:8b"
            return ChatOllama(model=model, temperature=LLM_TEMPERATURE)

        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return None
            model = LLM_MODEL or "claude-sonnet-4-5"
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            kwargs = {
                "model": model,
                "api_key": api_key,
                "temperature": LLM_TEMPERATURE,
            }
            if base_url:
                kwargs["base_url"] = base_url
            return ChatAnthropic(**kwargs)

        elif provider == "cohere":
            from langchain_cohere import ChatCohere

            api_key = os.getenv("COHERE_API_KEY")
            if not api_key:
                return None
            model = LLM_MODEL or "command-a-03-2025"
            base_url = os.getenv("COHERE_BASE_URL")
            kwargs = {
                "model": model,
                "api_key": api_key,
                "temperature": LLM_TEMPERATURE,
            }
            if base_url:
                kwargs["base_url"] = base_url
            return ChatCohere(**kwargs)

        elif provider in _OPENAI_COMPATIBLE:
            from langchain_openai import ChatOpenAI

            key_env, url_env, default_url, default_model = _OPENAI_COMPATIBLE[
                provider
            ]
            api_key = os.getenv(key_env)
            if not api_key:
                return None
            return ChatOpenAI(
                model=LLM_MODEL or default_model,
                api_key=api_key,
                base_url=os.getenv(url_env) or default_url,
                temperature=LLM_TEMPERATURE,
            )

        else:
            # Provider tak dikenal: coba pola OpenAI-compatible generik.
            # Cukup isi <NAMA>_API_KEY + <NAMA>_BASE_URL di .env
            # (mis. TINKER_API_KEY + TINKER_BASE_URL untuk LLM_PROVIDER=tinker),
            # plus LLM_MODEL. Tanpa BASE_URL -> tolak (hindari salah kirim
            # key ke endpoint default OpenAI).
            from langchain_openai import ChatOpenAI

            prefix = provider.upper().replace("-", "_")
            api_key = os.getenv(f"{prefix}_API_KEY")
            base_url = os.getenv(f"{prefix}_BASE_URL")
            if not base_url or not LLM_MODEL:
                return None
            return ChatOpenAI(
                model=LLM_MODEL,
                api_key=api_key or "not-needed",
                base_url=base_url,
                temperature=LLM_TEMPERATURE,
            )

    except Exception as e:
        logging.getLogger("llm_config").warning(f"Provider {provider} gagal init: {e}")
    return None


def get_llm():
    """Inisialisasi LLM dengan fallback otomatis. Cache instance per provider."""
    global _active_provider
    primary = LLM_PROVIDER
    # Bangun urutan: primary dulu, lalu fallback order tanpa duplikat
    order = [primary] + [p for p in FALLBACK_ORDER if p != primary]

    for provider in order:
        if provider in _llm_cache:
            _active_provider = provider
            return _llm_cache[provider]
        llm = _init_provider(provider)
        if llm is not None:
            _llm_cache[provider] = llm
            _active_provider = provider
            logging.getLogger("llm_config").info(f"LLM provider aktif: {provider}")
            return llm

    raise RuntimeError(
        f"Tidak ada provider LLM yang tersedia. Cek API keys untuk: {', '.join(order)}"
    )


def _parse_native_tool_names(raw: str, strict: bool) -> list:
    """Ubah string comma-separated jadi daftar nama native tool yang valid & unik.

    strict=True  (argumen eksplisit) -> nama tak dikenal raise ValueError (typo programmer).
    strict=False (dari env)          -> nama tak dikenal di-skip + warning, supaya
                                        salah ketik di .env tidak menjatuhkan tiap request.
    """
    selected = []
    for name in (n.strip().lower() for n in raw.split(",")):
        if not name:
            continue
        if name not in NATIVE_TOOLS:
            if strict:
                raise ValueError(
                    f"Native tool '{name}' tidak dikenal. Pilihan: {', '.join(NATIVE_TOOLS)}"
                )
            logging.getLogger("llm_config").warning(
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
    """Tools native Gemini (server-side, tanpa eksekusi lokal).

    names: comma-separated subset dari "google_search,code_execution,url_context".
    Default dari env GOOGLE_NATIVE_TOOLS (default: "" = mati).
    Hanya berlaku bila provider google benar-benar aktif (hasil fallback get_llm);
    provider lain return [] tanpa mengimpor google-genai.
    """
    raw = names if names is not None else os.getenv("GOOGLE_NATIVE_TOOLS", "")
    selected = _parse_native_tool_names(raw, strict=names is not None)
    if not selected:
        return []
    if get_active_provider() != "google":
        return []

    # Import ditunda: google-genai tidak wajib terpasang untuk provider non-google.
    try:
        from google.genai import types
    except ImportError as e:
        logging.getLogger("llm_config").warning(
            f"google-genai tidak tersedia, native tools dimatikan: {e}"
        )
        return []

    builders = {
        "google_search": lambda: types.Tool(google_search=types.GoogleSearch()),
        "code_execution": lambda: types.Tool(code_execution=types.ToolCodeExecution()),
        "url_context": lambda: types.Tool(url_context=types.UrlContext()),
    }
    return [builders[name]() for name in selected]


def bind_native_tools(llm, names: str | None = None):
    """Return llm yang di-bind native tools; llm asli bila tidak ada yang dipilih.

    Aman dipanggil tanpa syarat (mis. main.py): llm dikembalikan apa adanya bila
    provider aktif bukan google atau llm bukan model langchain-google-genai —
    mencegah native tool Gemini di-bind ke provider yang tak memahaminya.
    """
    tools = get_native_tools(names)
    if not tools:
        return llm
    if not _is_google_llm(llm):
        logging.getLogger("llm_config").warning(
            "Native tool Gemini diminta, tapi LLM aktif bukan ChatGoogleGenerativeAI; "
            "binding dilewati."
        )
        return llm
    return llm.bind_tools(tools)
