"""PDF operations for office_tool."""


def _run_pdf_op(op: str, args: dict) -> str:
    """Eksekusi operasi PDF menggunakan PyMuPDF (fitz)."""
    input_path = args.get("input", "")
    output_path = args.get("output", "")

    if op == "extract_text":
        try:
            import fitz

            doc = fitz.open(input_path)
            try:
                texts = [page.get_text() for page in doc]
            finally:
                doc.close()
            return "\n---\n".join(texts)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "merge_pdfs":
        try:
            import fitz

            inputs = args.get("inputs", [input_path])
            merged = fitz.open()
            try:
                for f in inputs:
                    src = fitz.open(f)
                    try:
                        merged.insert_pdf(src)
                    finally:
                        src.close()
                merged.save(output_path)
            finally:
                merged.close()
            return f"OK: {len(inputs)} PDF digabung -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "split_pdf":
        try:
            import fitz

            pages = args.get("pages", [])
            doc = fitz.open(input_path)
            try:
                for i, (start, end) in enumerate(pages):
                    writer = fitz.open()
                    try:
                        begin = start - 1
                        end_idx = min(end - 1, len(doc) - 1)
                        if begin <= end_idx:
                            writer.insert_pdf(doc, from_page=begin, to_page=end_idx)
                        out = output_path.replace(".pdf", f"_part{i + 1}.pdf") if len(pages) > 1 else output_path
                        writer.save(out)
                    finally:
                        writer.close()
            finally:
                doc.close()
            return f"OK: PDF split -> {output_path} ({len(pages)} bagian)"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "compress_pdf":
        try:
            import fitz

            doc = fitz.open(input_path)
            try:
                doc.save(output_path, garbage=4, deflate=True)
            finally:
                doc.close()
            return f"OK: PDF dikompres -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "add_watermark":
        try:
            import fitz

            text = args.get("text", "CONFIDENTIAL")
            fontsize = args.get("fontsize", 72)
            color = args.get("color", [1, 0, 0])
            rotation = args.get("rotation", 45)
            doc = fitz.open(input_path)
            try:
                for page in doc:
                    rect = page.rect
                    point = fitz.Point(rect.width / 3, rect.height / 2)
                    page.insert_text(
                        point, text, fontsize=fontsize, color=color, rotate=rotation, overlay=True, fontname="helv"
                    )
                doc.save(output_path)
            finally:
                doc.close()
            return f"OK: Watermark '{text}' ditambahkan -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "fill_pdf_form":
        try:
            import fitz

            form_data = args.get("data", {})
            doc = fitz.open(input_path)
            try:
                for page in doc:
                    for widget in page.widgets() or []:
                        field_name = widget.field_name
                        if field_name in form_data:
                            widget.field_value = str(form_data[field_name])
                            widget.update()
                doc.save(output_path)
            finally:
                doc.close()
            return f"OK: Form diisi ({len(form_data)} field) -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "get_pdf_metadata":
        try:
            import json as _json

            import fitz

            doc = fitz.open(input_path)
            try:
                meta = doc.metadata
                info = {
                    "pages": len(doc),
                    "title": meta.get("title", ""),
                    "author": meta.get("author", ""),
                    "subject": meta.get("subject", ""),
                }
            finally:
                doc.close()
            return _json.dumps(info, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "extract_tables":
        try:
            import json as _json

            import fitz

            doc = fitz.open(input_path)
            try:
                all_tables = []
                for i, page in enumerate(doc):
                    text = page.get_text()
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if lines:
                        all_tables.append({"page": i + 1, "rows": len(lines), "preview": lines[:5]})
            finally:
                doc.close()
            return _json.dumps(all_tables, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "convert_pdf":
        try:
            import fitz

            target = args.get("target_format", "txt")
            doc = fitz.open(input_path)
            try:
                if target == "txt":
                    texts = [page.get_text() for page in doc]
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write("\n---\n".join(texts))
                elif target == "images":
                    import os

                    os.makedirs(output_path, exist_ok=True)
                    for i, page in enumerate(doc):
                        pix = page.get_pixmap(dpi=150)
                        pix.save(f"{output_path}/page_{i + 1}.png")
            finally:
                doc.close()
            return f"OK: PDF dikonversi ke {target} -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    else:
        return f"Error: Operasi PDF '{op}' tidak dikenal."
