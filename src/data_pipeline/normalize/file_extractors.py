"""src/data_pipeline/normalize/file_extractors.py
Bộ trích xuất nội dung đa định dạng: PDF, JSON, CSV.

Mỗi extractor trả về một ``ExtractionResult`` dataclass chứa:
- raw_text: Văn bản thô trích xuất
- total_pages: Số trang (chỉ PDF)
- has_tables: Có bảng biểu hay không
- pdf_title: Tiêu đề từ PDF metadata
- pdf_creation_date / pdf_mod_date: Ngày tạo/sửa từ PDF metadata
- extra_metadata: Metadata bổ sung chuẩn RAG (doc_id, title, category, domain, source_url...)
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data_pipeline.normalize.text_cleaner import _is_noise_line

# ---------------------------------------------------------------------------
# Extraction Result
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Kết quả trích xuất nội dung từ một file."""

    raw_text: str = ""
    total_pages: int = 0
    has_tables: bool = False
    pdf_title: str = ""
    pdf_creation_date: str = ""
    pdf_mod_date: str = ""
    extra_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PDF Extractor (sử dụng pymupdf/fitz cho tốc độ và độ chính xác)
# ---------------------------------------------------------------------------


def extract_pdf(file_path: Path) -> ExtractionResult:
    """Trích xuất nội dung từ file PDF sử dụng PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF (pymupdf) chưa được cài đặt. "
            "Chạy: pip install pymupdf"
        ) from exc

    result = ExtractionResult()

    doc = fitz.open(str(file_path))
    result.total_pages = len(doc)

    # Trích xuất metadata từ PDF (loại bỏ tiêu đề rác như about:blank, untitled)
    meta = doc.metadata
    if meta:
        title = (meta.get("title", "") or "").strip()
        if title and title.lower() not in {"about:blank", "untitled", ""}:
            result.pdf_title = title
        result.pdf_creation_date = _parse_pdf_date(meta.get("creationDate", ""))
        result.pdf_mod_date = _parse_pdf_date(meta.get("modDate", ""))

    text_parts: list[str] = []
    tables_found = False

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Trích xuất bảng biểu (PyMuPDF >= 1.23.0)
        try:
            page_tables = page.find_tables()
            if page_tables and page_tables.tables:
                tables_found = True
                for table in page_tables.tables:
                    md_table = _table_to_markdown(table.extract())
                    if md_table:
                        text_parts.append(md_table)
        except (AttributeError, Exception):
            pass

        # Trích xuất text thường
        page_text = page.get_text("text")
        if page_text.strip():
            text_parts.append(page_text)

    doc.close()

    result.raw_text = "\n\n".join(text_parts)
    result.has_tables = tables_found

    return result


def _parse_pdf_date(date_str: str) -> str:
    """Parse ngày tháng từ PDF metadata (format D:YYYYMMDDHHmmSS)."""
    if not date_str:
        return ""

    clean = date_str.replace("D:", "").strip()
    m = re.match(r"(\d{4})(\d{2})(\d{2})", clean)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return ""


def _table_to_markdown(table_data: list[list[str | None]]) -> str:
    """Chuyển đổi dữ liệu bảng thành Markdown table format."""
    if not table_data or len(table_data) < 2:
        return ""

    cleaned: list[list[str]] = []
    for row in table_data:
        cleaned_row = [
            (cell or "").replace("\n", " ").replace("|", "\\|").strip()
            for cell in row
        ]
        cleaned.append(cleaned_row)

    max_cols = max(len(row) for row in cleaned)
    for row in cleaned:
        while len(row) < max_cols:
            row.append("")

    header = cleaned[0]
    separator = [":---"] * max_cols
    body = cleaned[1:]

    lines: list[str] = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON Extractor chuyên biệt cho RAG (Specs, FAQs, Policies, News)
# ---------------------------------------------------------------------------


def _extract_specs_json(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Trích xuất chuyên biệt cho file thông số kỹ thuật xe (specs).

    Tạo bảng thông số markdown sạch, không lặp lại và loại bỏ các nút bấm rác.
    """
    meta = obj.get("metadata", {}) or {}
    model_name = obj.get("model_name") or (meta.get("related_models") or [""])[0] or "Xe VinFast"
    segment = obj.get("segment") or meta.get("segment", "")
    seats = obj.get("seats") or meta.get("seats", "")
    description = obj.get("description", "").strip()

    title = f"Thông số kỹ thuật xe VinFast {model_name}"
    parts: list[str] = [f"# {title}\n"]

    # Thông tin tổng quan
    overview = [f"- **Dòng xe**: VinFast {model_name}"]
    if segment:
        overview.append(f"- **Phân khúc**: {segment}")
    if seats:
        overview.append(f"- **Số chỗ ngồi**: {seats}")
    parts.append("\n".join(overview))

    # Mô tả giới thiệu
    if description:
        parts.append(f"\n## Giới thiệu\n\n{description}")

    # Bảng thông số kỹ thuật chi tiết
    specs = obj.get("specifications", {})
    if specs and isinstance(specs, dict):
        noise_keys = {
            "tải brochure", "đặt cọc", "so sánh xe", "xem tất cả", "đóng",
            "kích thước & trọng lượng", "chi tiết", "xem thêm"
        }
        valid_specs = []
        for k, v in specs.items():
            k_clean = str(k).strip()
            v_clean = str(v).strip()
            if not k_clean or not v_clean:
                continue
            if k_clean.lower() in noise_keys:
                continue
            if "pin & sạc" in v_clean.lower() and "công nghệ" in v_clean.lower():
                continue
            valid_specs.append((k_clean, v_clean))

        if valid_specs:
            parts.append("\n## Thông số kỹ thuật chi tiết\n")
            table_lines = ["| Hạng mục | Thông số |", "| :--- | :--- |"]
            for k_spec, v_spec in valid_specs:
                table_lines.append(f"| {k_spec} | {v_spec} |")
            parts.append("\n".join(table_lines))

    # Tính năng nổi bật (nếu có nội dung thực tế)
    features = obj.get("key_features", [])
    if features and isinstance(features, list):
        valid_feats = [
            f.strip() for f in features
            if isinstance(f, str) and f.strip() and f.strip().lower() not in {"đang cập nhật", "none"}
        ]
        if valid_feats:
            parts.append("\n## Tính năng nổi bật\n")
            parts.append("\n".join(f"- {feat}" for feat in valid_feats))

    extra_meta: dict[str, Any] = {
        "doc_id": meta.get("doc_id") or f"doc_specs_{obj.get('slug', model_name.lower())}",
        "title": title,
        "category": "specs",
        "domain": meta.get("domain", "vinfastauto.com"),
        "source_url": meta.get("source_url", ""),
        "target_vehicles": [model_name] if model_name else [],
        "summary": description,
    }

    return "\n\n".join(parts), extra_meta


def _extract_faq_item(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Trích xuất một câu hỏi FAQ đơn lẻ, không lặp lại nội dung."""
    meta = obj.get("metadata", {}) or {}
    q = obj.get("question", "").strip()
    a = obj.get("answer", "").strip()

    # Khử đoạn trùng lặp bên trong answer (nhiễu hotline lặp)
    a_paras = [p.strip() for p in a.split("\n\n") if p.strip()]
    seen_paras: set[str] = set()
    unique_a: list[str] = []
    for p in a_paras:
        p_norm = re.sub(r"\s+", " ", p).lower()
        if p_norm not in seen_paras:
            seen_paras.add(p_norm)
            unique_a.append(p)
    a_clean = "\n\n".join(unique_a)

    content = f"### Câu hỏi: {q}\n\n**Trả lời:** {a_clean}"

    extra_meta: dict[str, Any] = {
        "doc_id": meta.get("doc_id", ""),
        "title": q,
        "category": "faq",
        "subcategory": meta.get("subcategory", ""),
        "domain": meta.get("domain", "vinfastauto.com"),
        "source_url": meta.get("source_url", ""),
        "target_vehicles": meta.get("related_models", []),
    }

    return content, extra_meta


def _extract_specs_summary_json(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Trích xuất bảng tổng hợp danh mục các dòng xe VinFast (specs_summary)."""
    models = obj.get("models", [])
    title = "Tổng hợp danh mục xe VinFast"
    parts = [f"# {title}\n"]
    if models:
        parts.append("| Dòng xe | Phân khúc | Số lượng thông số |")
        parts.append("| :--- | :--- | :--- |")
        for m in models:
            parts.append(f"| {m.get('model_name', '')} | {m.get('segment', '')} | {m.get('specs_count', '')} |")
    content = "\n\n".join(parts)
    extra_meta = {
        "doc_id": "doc_specs_summary",
        "title": title,
        "category": "specs",
        "domain": "vinfastauto.com",
        "target_vehicles": [m.get("model_name") for m in models if m.get("model_name")],
    }
    return content, extra_meta


def _extract_sections_policy(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Trích xuất tài liệu chính sách có cấu trúc sections, loại bỏ triệt để navbar và TOC rác."""
    meta = obj.get("metadata", {}) or {}
    title = meta.get("title") or obj.get("title", "")
    sections = obj.get("sections", [])
    parts: list[str] = []

    if title:
        parts.append(f"# {title}\n")

    # Thu thập tất cả section titles để phát hiện anchor links / TOC list bị cào lẫn vào nội dung
    all_sec_titles = {
        s.get("section_title", "").strip().lower()
        for s in sections
        if isinstance(s, dict) and s.get("section_title")
    }

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        sec_title = sec.get("section_title", "").strip()
        sec_content = sec.get("content", "").strip()
        if not sec_content:
            continue

        # Lọc từng dòng trong section
        cleaned_lines: list[str] = []
        for line in sec_content.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            line_lower = line_str.lower()
            # Bỏ nếu là dòng nhiễu kỹ thuật / web UI
            if _is_noise_line(line_str):
                continue
            # Bỏ nếu dòng trùng với tiêu đề section khác (anchor link web TOC)
            if line_lower in all_sec_titles and line_lower != sec_title.lower():
                continue
            # Bỏ nếu dòng lặp lại chính tiêu đề bài viết
            if title and line_lower == title.lower():
                continue
            # Đối với section 'Tổng quan': bỏ các dòng cụm từ ngắn không dấu câu (< 30 ký tự)
            if sec_title.lower() == "tổng quan" and len(line_str) < 35 and line_str[-1] not in ".!?:":
                continue
            cleaned_lines.append(line_str)

        clean_sec_body = "\n\n".join(cleaned_lines).strip()
        if not clean_sec_body:
            continue

        # Nếu là section 'Tổng quan' chứa đoạn mô tả giới thiệu
        if sec_title.lower() == "tổng quan":
            parts.append(clean_sec_body)
        elif sec_title and sec_title.lower() != title.lower():
            parts.append(f"## {sec_title}\n\n{clean_sec_body}")
        else:
            parts.append(clean_sec_body)

    extra_meta: dict[str, Any] = {
        "doc_id": meta.get("doc_id", ""),
        "title": title,
        "category": "policy",
        "subcategory": meta.get("subcategory", ""),
        "domain": meta.get("domain", "vinfastauto.com"),
        "source_url": meta.get("source_url", ""),
        "target_vehicles": meta.get("related_models", []),
    }

    return "\n\n".join(parts), extra_meta


def _extract_article_json(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Trích xuất bài viết tin tức/chính sách đơn nguồn (không chồng lấn raw_content và content)."""
    meta = obj.get("metadata", {}) or {}
    title = meta.get("title") or obj.get("title", "")
    summary = obj.get("summary", "").strip()

    # Làm sạch summary khỏi brand trailer và tránh lặp tiêu đề
    if summary:
        summary = re.sub(r"\s*\|\s*(?:VinFast|Techcombank|Xe Hay|V-Green)\s*$", "", summary, flags=re.IGNORECASE).strip()
        if title and (summary.lower() == title.lower() or (len(title) > 20 and title.lower() in summary.lower() and len(summary) < len(title) + 20)):
            summary = ""

    # Chọn duy nhất MỘT nguồn nội dung tốt nhất
    content = obj.get("content") or obj.get("body") or obj.get("raw_content") or ""

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if summary and len(summary) > 20:
        parts.append(f"> {summary}\n")
    if content:
        parts.append(content)

    extra_meta: dict[str, Any] = {
        "doc_id": meta.get("doc_id", ""),
        "title": title,
        "category": meta.get("category") or meta.get("doc_type") or "news",
        "subcategory": meta.get("subcategory", ""),
        "domain": meta.get("domain", ""),
        "source_url": meta.get("source_url", ""),
        "published_date": meta.get("published_date") or obj.get("published_date", ""),
        "target_vehicles": meta.get("related_models", []),
        "summary": summary,
    }

    return "\n\n".join(parts), extra_meta


def _extract_single_json_object(obj: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Dispatcher trích xuất theo từng loại JSON schema cụ thể."""
    # 1. Summary of all models
    if "models" in obj and isinstance(obj["models"], list) and "total_models" in obj:
        return _extract_specs_summary_json(obj)

    # 2. Vehicle specs format
    if "specifications" in obj or "model_name" in obj:
        return _extract_specs_json(obj)

    # 3. FAQ item format
    if "question" in obj and "answer" in obj:
        return _extract_faq_item(obj)

    # 4. Policy with sections format
    if "sections" in obj and isinstance(obj["sections"], list):
        return _extract_sections_policy(obj)

    # 5. Standard article format (News / Policy)
    return _extract_article_json(obj)


def extract_json(file_path: Path) -> ExtractionResult:
    """Trích xuất nội dung từ file JSON."""
    result = ExtractionResult()

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        result.raw_text, result.extra_metadata = _extract_single_json_object(data)
        result.has_tables = bool(re.search(r"\|.*\|.*\|", result.raw_text))
    elif isinstance(data, list):
        text_parts: list[str] = []
        combined_meta: dict[str, Any] = {}

        for item in data:
            if isinstance(item, dict):
                text, meta = _extract_single_json_object(item)
                if text:
                    text_parts.append(text)
                if not combined_meta and meta:
                    combined_meta = meta

        result.raw_text = "\n\n---\n\n".join(text_parts)
        result.extra_metadata = combined_meta
        result.has_tables = bool(re.search(r"\|.*\|.*\|", result.raw_text))
    else:
        result.raw_text = str(data)

    return result


# ---------------------------------------------------------------------------
# CSV Extractor (chuyển CSV thành Markdown Table)
# ---------------------------------------------------------------------------


def extract_csv(file_path: Path) -> ExtractionResult:
    """Trích xuất nội dung từ file CSV, chuyển thành Markdown Table."""
    result = ExtractionResult()
    result.has_tables = True

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(content[:2048])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        result.raw_text = ""
        return result

    title = file_path.stem.replace("_", " ").title()
    text_parts = [f"# {title}\n"]

    md_table = _table_to_markdown(rows)
    if md_table:
        text_parts.append(md_table)
    else:
        text_parts.append(content)

    result.raw_text = "\n".join(text_parts)
    result.total_pages = 1

    return result


# ---------------------------------------------------------------------------
# Dispatcher: Chọn extractor phù hợp theo extension
# ---------------------------------------------------------------------------

_SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".json", ".csv"}


def is_supported_file(file_path: Path) -> bool:
    """Kiểm tra file có được hỗ trợ trích xuất hay không."""
    return file_path.suffix.lower() in _SUPPORTED_EXTENSIONS


def extract_file(file_path: Path) -> ExtractionResult:
    """Dispatcher: trích xuất nội dung file dựa trên extension."""
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        return extract_pdf(file_path)
    elif ext == ".json":
        return extract_json(file_path)
    elif ext == ".csv":
        return extract_csv(file_path)
    else:
        raise ValueError(f"Định dạng file không được hỗ trợ: {ext}")
