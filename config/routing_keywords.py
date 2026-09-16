# Keyword routing untuk long term memory
# Format: agent_type -> list of keywords

ROUTING_KEYWORDS = {
    "admin_agent": [
        "draf", "gaji", "upah", "surat", "izin",
        "saham", "harga", "app", "aplikasi", "kos", "kontrakan", "sewa", "cari",
        "berita", "informasi", "update"
    ],
    "coder_agent": [
        "kode", "program", "python", "programming", "script", "fungsi", "class",
        "tulis_kode", "buat file", "automation"
    ]
}

# Default fallback
DEFAULT_AGENT = "casual_agent"
