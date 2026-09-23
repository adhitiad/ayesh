"""File operations: list_folder, buat_folder, hapus_file, rename_file, download_file, upload_file, buka_url, search_folder, info_file."""

import glob
import os
import time
import urllib.parse

from langchain_core.tools import tool

from src.plugins.file_safety import _safe_path
from src.plugins.tool_error import tool_error_from_exception
from src.plugins.web_tools import _open_pinned_connection, _validate_url_with_address

_MAX_DOWNLOAD_BYTES = 10_000_000
_MAX_REDIRECTS = 5
_CONNECT_TIMEOUT = 10
_ALLOWED_UPLOAD_METHODS = {"POST", "PUT", "PATCH"}


def _prepare_http_request(url: str, method: str) -> tuple:
    """Validate an HTTP(S) URL and resolve its connection address."""
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL harus http/https.")
    if not parsed.hostname:
        raise ValueError("URL tidak valid.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL tidak boleh mengandung kredensial.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Port URL tidak valid.") from exc
    valid, address = _validate_url_with_address(url)
    if not valid or not address:
        raise ValueError("URL ditolak (private/loopback/link-local/metadata endpoint).")
    return parsed, parsed.hostname, port, address


def _http_request(
    url: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict | None = None,
    prepared: tuple | None = None,
) -> tuple:
    """Fetch a URL with scheme, DNS, IP, redirect, and size protections."""
    method = method.upper()
    if method not in {"GET", *_ALLOWED_UPLOAD_METHODS}:
        raise ValueError("Metode HTTP tidak didukung.")
    current_url = url
    current_method = method
    current_body = body
    redirect_count = 0
    connection = None
    try:
        while True:
            parsed, hostname, port, address = prepared or _prepare_http_request(current_url, current_method)
            connection = _open_pinned_connection(hostname, port, parsed.scheme, address, _CONNECT_TIMEOUT)
            request_headers = dict(headers or {})
            request_headers.setdefault("User-Agent", "Ayesh/1.0")
            request_headers["Host"] = hostname
            connection.request(current_method, parsed.path or "/", body=current_body, headers=request_headers)
            response = connection.getresponse()
            status = response.status
            data = bytearray()
            try:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > _MAX_DOWNLOAD_BYTES:
                        raise ValueError("Ukuran respons terlalu besar.")
                location = response.getheader("Location", "")
            finally:
                response.close()
            if 300 <= status < 400:
                if not location:
                    return status, bytes(data)
                redirect_count += 1
                if redirect_count > _MAX_REDIRECTS:
                    raise ValueError("Jumlah redirect terlalu banyak.")
                if current_method != "GET":
                    raise ValueError("Redirect tidak diikuti untuk upload.")
                next_url = urllib.parse.urljoin(current_url, location)
                connection.close()
                connection = None
                # Revalidate redirect target: DNS + private IP check
                _prepare_http_request(next_url, "GET")
                current_url = next_url
                current_method = "GET"
                current_body = None
                prepared = None
                continue
            return status, bytes(data)
    finally:
        if connection is not None:
            connection.close()


def _http_error(message: str) -> str:
    """Return a stable tool error message for rejected URLs."""
    return f"Error: {message}"


@tool
def list_folder(path: str = ".") -> str:
    """Menampilkan isi dari direktori (folder)."""
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        if not os.path.isdir(path):
            return f"Error: '{path}' bukan direktori."
        items = []
        for item in sorted(os.listdir(path)):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                items.append(f"\U0001f4c1 {item}/")
            else:
                size = os.path.getsize(full_path)
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
                items.append(f"\U0001f4c4 {item} ({size_str})")
        if not items:
            return f"Folder '{path}' kosong."
        return f"Isi folder '{path}':\n" + "\n".join(items)
    except PermissionError:
        return f"Error: Tidak ada akses ke '{path}'."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def buat_folder(path: str) -> str:
    """Membuat folder baru."""
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved("buat_folder", {"path": path}, owner_user_id=get_current_user_id())
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        if os.path.exists(path):
            if os.path.isdir(path):
                return f"Folder '{path}' sudah ada."
            return f"Error: '{path}' sudah ada dan bukan folder."
        os.makedirs(path, exist_ok=True)
        return f"Folder '{path}' berhasil dibuat."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def hapus_file(path: str) -> str:
    """Menghapus file atau folder (rekursif)."""
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved("hapus_file", {"path": path}, owner_user_id=get_current_user_id())
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        if not os.path.exists(path):
            return f"Error: '{path}' tidak ditemukan."
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path)
            return f"Folder '{path}' berhasil dihapus (rekursif)."
        os.remove(path)
        return f"File '{path}' berhasil dihapus."
    except PermissionError:
        return f"Error: Tidak ada akses menghapus '{path}'."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def rename_file(source: str, destination: str) -> str:
    """Mengganti nama file atau folder."""
    try:
        _ok_src, source = _safe_path(source)
        if not _ok_src:
            return source
        _ok_dst, destination = _safe_path(destination)
        if not _ok_dst:
            return destination
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "rename_file", {"source": source, "destination": destination}, owner_user_id=get_current_user_id()
            )
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        if not os.path.exists(source):
            return f"Error: '{source}' tidak ditemukan."
        if os.path.exists(destination):
            return f"Error: '{destination}' sudah ada."
        os.rename(source, destination)
        return f"'{source}' berhasil di-rename ke '{destination}'."
    except PermissionError:
        return f"Error: Tidak ada akses rename '{source}'."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def download_file(url: str, destination: str = "") -> str:
    """Mengunduh file dari URL."""
    try:
        prepared = _prepare_http_request(url, "GET")
        if not destination:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or "downloaded_file"
            destination = os.path.join(".", filename)
        _path_ok, destination = _safe_path(destination)
        if not _path_ok:
            return destination
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "download_file", {"url": url, "destination": destination}, owner_user_id=get_current_user_id()
            )
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        status, data = _http_request(url, "GET", prepared=prepared)
        if not 200 <= status < 400:
            return f"Error: HTTP {status}."
        parent = os.path.dirname(destination)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(destination, "wb") as output:
            output.write(data)
        return f"File berhasil diunduh ke '{destination}' ({len(data)} bytes)."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def upload_file(filepath: str, url: str, method: str = "POST") -> str:
    """Mengupload file ke URL."""
    try:
        method = method.strip().upper()
        if method not in _ALLOWED_UPLOAD_METHODS:
            return "Error: Metode upload tidak didukung."
        _prepare_http_request(url, method)
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        if not os.path.exists(filepath):
            return f"Error: File '{filepath}' tidak ditemukan."
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "upload_file", {"filepath": filepath, "url": url, "method": method}, owner_user_id=get_current_user_id()
            )
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        with open(filepath, "rb") as source:
            data = source.read()
        status, _response = _http_request(url, method, data, {"Content-Type": "application/octet-stream"})
        if not 200 <= status < 400:
            return f"Error: HTTP {status}."
        return f"File '{filepath}' berhasil diupload ke '{url}' (HTTP {status})."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def buka_url(url: str) -> str:
    """Membuka URL di browser default (dengan validasi SSRF)."""
    try:
        import webbrowser

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "Error: URL harus http/https."
        valid, _address = _validate_url_with_address(url)
        if not valid:
            return "Error: URL ditolak (private/loopback/link-local/metadata endpoint)."
        webbrowser.open(url)
        return f"URL '{url}' berhasil dibuka di browser."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def search_folder(path: str = ".", pattern: str = "*") -> str:
    """Mencari file berdasarkan pola di folder."""
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        search_pattern = os.path.join(path, "**", pattern)
        matches = glob.glob(search_pattern, recursive=True)
        if not matches:
            return f"Tidak ditemukan file dengan pola '{pattern}' di '{path}'."
        results = []
        for match in sorted(matches)[:50]:
            rel_path = os.path.relpath(match, path)
            if os.path.isdir(match):
                results.append(f"\U0001f4c1 {rel_path}/")
            else:
                size = os.path.getsize(match)
                results.append(f"\U0001f4c4 {rel_path} ({size}B)")
        return f"Hasil pencarian '{pattern}' di '{path}':\n" + "\n".join(results)
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def info_file(path: str) -> str:
    """Menampilkan informasi detail tentang file."""
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        if not os.path.exists(path):
            return f"Error: '{path}' tidak ditemukan."
        stat = os.stat(path)
        is_dir = os.path.isdir(path)
        info = []
        info.append(f"Nama: {os.path.basename(path)}")
        info.append(f"Jenis: {'Folder' if is_dir else 'File'}")
        info.append(f"Path: {os.path.abspath(path)}")
        info.append(f"Ukuran: {stat.st_size} bytes")
        info.append(f"Dibuat: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_ctime))}")
        info.append(f"Diubah: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))}")
        if is_dir:
            items = os.listdir(path)
            info.append(f"Jumlah item: {len(items)}")
        return "\n".join(info)
    except Exception as e:
        return tool_error_from_exception(e)
