"""Contoh tool marketplace: kalkulator aritmatika sederhana."""

from langchain_core.tools import tool


@tool
def kalkulator_sederhana(a: float, b: float, operasi: str = "tambah") -> str:
    """Hitung operasi aritmatika sederhana.

    Args:
        a: bilangan pertama.
        b: bilangan kedua.
        operasi: tambah | kurang | kali | bagi.
    """
    ops = operasi.strip().lower()
    if ops == "tambah":
        return str(a + b)
    if ops == "kurang":
        return str(a - b)
    if ops == "kali":
        return str(a * b)
    if ops == "bagi":
        if b == 0:
            return "Error: pembagian dengan nol"
        return str(a / b)
    return f"Error: operasi tidak dikenal: {operasi}"
