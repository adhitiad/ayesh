"""Konfigurasi LLM terpusat untuk NVIDIA NIM."""

import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA


load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "moonshotai/kimi-k3")


def get_llm() -> ChatNVIDIA:
    """Inisialisasi dan kembalikan instance ChatNVIDIA untuk NVIDIA NIM."""
    if not NVIDIA_API_KEY or NVIDIA_API_KEY == "your_gemini_api_key_here":
        raise RuntimeError("NVIDIA_API_KEY belum diisi di .env")
    return ChatNVIDIA(
        model=LLM_MODEL,
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        temperature=0.7,
    )
