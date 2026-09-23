"""Standardized tool exception and error formatting.

ToolError exception untuk internal tool error handling.
Semua tool tool_return() mengembalikan string konsisten: "Error: {message}".
"""


class ToolError(Exception):
    """Exception basis untuk error pada tool plugin.

    Semua tool yang throw ToolError akan ditangkap dan dikonversi
    ke string error konsisten: "Error: {message}".
    """


def tool_error(message: str) -> str:
    """Standarisasi format error return.

    Args:
        message: Pesan error deskriptif.

    Returns:
        String error format: "Error: {message}".
    """
    return f"Error: {message}"


def tool_error_from_exception(e: Exception, context: str = "") -> str:
    """Konversi exception ke string error konsisten.

    Args:
        e: Exception yang ditangkap.
        context: Konteks opsional (misalnya "approval denied", "policy denied").

    Returns:
        String error format: "Error: {context} {exception_message}".
    """
    if context:
        return f"Error: {context}: {e!s}"
    return f"Error: {e!s}"
