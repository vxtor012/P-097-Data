"""src/data_pipeline/normalize/metadata_utils.py
Tiện ích trích xuất và định dạng metadata thành YAML Frontmatter cho các tệp Markdown chuẩn hóa (Silver Layer).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
import yaml


def compute_content_hash(text: str) -> str:
    """Tính toán chuỗi băm MD5 / SHA-256 từ chuỗi văn bản."""
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    """Tính toán SHA-256 của một tệp tin."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def count_words_and_chars(text: str) -> tuple[int, int]:
    """Đếm số từ và số ký tự trong văn bản."""
    clean = text.strip()
    char_count = len(clean)
    word_count = len(clean.split()) if clean else 0
    return char_count, word_count


def clean_metadata_dict(raw_meta: dict[str, Any]) -> dict[str, Any]:
    """Lọc và chuẩn hóa dictionary metadata trước khi xuất YAML."""
    cleaned: dict[str, Any] = {}
    
    # Thứ tự ưu tiên hiển thị các trường quan trọng
    priority_keys = [
        "doc_id",
        "title",
        "doc_type",
        "category",
        "subcategory",
        "domain",
        "source_url",
        "source_type",
        "published_date",
        "effective_date",
        "document_code",
        "issuing_authority",
        "applies_to",
        "related_models",
        "is_general_info",
        "language",
        "pipeline_stage",
        "crawled_at",
        "normalized_at",
        "content_hash",
        "char_count",
        "word_count",
        "token_estimate",
        "segment",
        "seats",
        "specifications_count",
    ]

    for key in priority_keys:
        if key in raw_meta and raw_meta[key] is not None:
            cleaned[key] = raw_meta[key]

    for key, value in raw_meta.items():
        if key not in cleaned and value is not None:
            cleaned[key] = value

    return cleaned


def build_yaml_frontmatter(metadata: dict[str, Any]) -> str:
    """Tạo khối YAML Frontmatter bao quanh bởi dấu `---`."""
    cleaned = clean_metadata_dict(metadata)
    yaml_str = yaml.dump(
        cleaned,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{yaml_str}\n---\n\n"


def extract_pdf_metadata(pdf_path: Path, doc_text: str = "") -> dict[str, Any]:
    """Tự động trích xuất metadata từ tệp PDF và nội dung (dành cho legal documents)."""
    filename = pdf_path.stem
    file_sha256 = compute_file_sha256(pdf_path)
    char_count, word_count = count_words_and_chars(doc_text)

    # Nhận diện số hiệu văn bản (Nghị định, Thông tư...)
    doc_code_match = re.search(
        r"(?:Số|Số:)\s*([0-9]+/[0-9]+/(?:NĐ-CP|TT-BTC|TT-BCA|TT-BGTVT|QĐ-[A-Z]+))",
        doc_text[:2000],
        re.IGNORECASE,
    )
    doc_code = doc_code_match.group(1) if doc_code_match else None

    # Nhận diện cơ quan ban hành
    issuing_authority = None
    if "CHÍNH PHỦ" in doc_text[:1000].upper():
        issuing_authority = "Chính phủ"
    elif "BỘ TÀI CHÍNH" in doc_text[:1000].upper():
        issuing_authority = "Bộ Tài chính"
    elif "BỘ GIAO THÔNG VẬN TẢI" in doc_text[:1000].upper():
        issuing_authority = "Bộ Giao thông Vận tải"
    elif "BỘ CÔNG AN" in doc_text[:1000].upper():
        issuing_authority = "Bộ Công an"

    # Nhận diện tiêu đề từ filename hoặc văn bản
    title = filename.replace("_", " ").replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()

    slug = re.sub(r"[^\w\-_]", "_", filename).lower()
    doc_id = f"doc_legal_{slug[:60]}"

    return {
        "doc_id": doc_id,
        "title": title,
        "doc_type": "legal_regulation",
        "category": "Văn bản Quy phạm Pháp luật",
        "subcategory": "Pháp lý & Đăng kiểm Ô tô - Xe máy điện",
        "source_file": pdf_path.name,
        "source_type": "official_legal_pdf",
        "document_code": doc_code,
        "issuing_authority": issuing_authority,
        "language": "vi",
        "pipeline_stage": "silver_standardized",
        "content_hash": file_sha256,
        "char_count": char_count,
        "word_count": word_count,
        "token_estimate": int(word_count * 1.3),
    }
