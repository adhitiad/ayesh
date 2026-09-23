"""Office tool wrapper: office_tool, _run_office_op dispatch."""


from langchain_core.tools import tool

from src.plugins.office_document import _run_document_op
from src.plugins.office_pdf import _run_pdf_op
from src.plugins.office_presentation import _run_presentation_op
from src.plugins.office_spreadsheet import _run_spreadsheet_op
from src.plugins.tool_error import tool_error_from_exception

_OFFICE_CATEGORIES = {
    "PDF": [
        "extract_text", "merge_pdfs", "split_pdf", "compress_pdf", "add_watermark",
        "fill_pdf_form", "get_pdf_metadata", "extract_tables", "convert_pdf",
    ],
    "Spreadsheet": [
        "read_xlsx", "create_xlsx", "apply_formula", "create_chart", "analyze_data",
        "format_cells", "xlsx_to_csv", "csv_to_xlsx", "json_to_xlsx", "xlsx_to_json",
    ],
    "Document": [
        "create_docx", "edit_docx", "merge_docx", "template_fill", "docx_to_md",
        "md_to_docx", "html_to_docx",
    ],
    "Presentation": [
        "create_pptx", "extract_pptx", "md_to_pptx", "md_to_slides", "add_notes", "export_pptx",
    ],
}


def _run_office_op(op: str, args: dict) -> str:
    """Eksekusi operasi office menggunakan library khusus per kategori."""
    if op in _OFFICE_CATEGORIES["PDF"]:
        return _run_pdf_op(op, args)
    elif op in _OFFICE_CATEGORIES["Spreadsheet"]:
        return _run_spreadsheet_op(op, args)
    elif op in _OFFICE_CATEGORIES["Document"]:
        return _run_document_op(op, args)
    elif op in _OFFICE_CATEGORIES["Presentation"]:
        return _run_presentation_op(op, args)
    else:
        available = []
        for ops in _OFFICE_CATEGORIES.values():
            available.extend(ops)
        return (
            f"Error: Operasi '{op}' belum diimplementasi.\n"
            f"Operasi yang tersedia:\n{', '.join(sorted(set(available)))}"
        )


@tool
def office_tool(operation: str, args_json: str = "{}") -> str:
    """Tool Office untuk operasi dokumen (PDF, Word, Excel, PowerPoint).

    39 operasi tersedia untuk manipulasi dokumen. File input harus ada di
    sistem. File output disimpan di output/ atau path yang ditentukan.

    Args:
        operation: Nama operasi. Lihat daftar lengkap di bawah.
        args_json: Argumen sebagai JSON string. Contoh:
            '{"input": "file.pdf", "output": "output.pdf", "text": "CONFIDENTIAL"}'

    Kategori operasi:
    - PDF: extract_text, merge_pdfs, split_pdf, compress_pdf, add_watermark,
           fill_pdf_form, get_pdf_metadata, extract_tables, convert_pdf
    - Spreadsheet: read_xlsx, create_xlsx, apply_formula, create_chart,
                   analyze_data, format_cells, xlsx_to_csv, csv_to_xlsx,
                   json_to_xlsx, xlsx_to_json
    - Document: create_docx, edit_docx, merge_docx, template_fill,
                docx_to_md, md_to_docx, html_to_docx
    - Presentation: create_pptx, extract_pptx, md_to_pptx, md_to_slides,
                    add_notes, export_pptx
    """
    import json as _json

    try:
        op = operation.strip()
        all_ops = set()
        for ops in _OFFICE_CATEGORIES.values():
            all_ops.update(ops)

        if op not in all_ops:
            available = []
            for _cat, ops in _OFFICE_CATEGORIES.items():
                available.extend(ops)
            return f"Error: Operasi '{op}' tidak dikenal.\nOperasi yang tersedia:\n{', '.join(sorted(available))}"

        try:
            args = _json.loads(args_json) if args_json.strip() else {}
        except _json.JSONDecodeError:
            return "Error: args_json bukan JSON valid."
        if not isinstance(args, dict):
            return "Error: args_json harus object JSON."

        # Approval gate
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "office_tool",
                {"operation": op, "args": args},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as exc:
            return tool_error_from_exception(exc)

        return _run_office_op(op, args)
    except Exception as e:
        return tool_error_from_exception(e)
