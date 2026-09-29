"""src/data_pipeline/normalize/metadata_extractor.py
Trích xuất metadata phong phú phục vụ AI RAG & LLMOps (YAML Frontmatter).

Chức năng chính:
- Trích xuất định danh truy vết: doc_id, domain, source_url/source_path
- Nhận diện phân loại: category (specs, faq, policy, news, legal), subcategory
- Trích xuất thuộc tính pháp lý: document_code (số hiệu), issuing_authority (cơ quan ban hành), effective_date (ngày ban hành)
- Trích xuất đối tượng áp dụng: target_vehicles (các dòng xe liên quan phục vụ RAG filtering)
- Chỉ số định lượng: language, char_count, word_count, total_pages
- Tuyệt đối KHÔNG chứa trường rác (file size, file system timestamps, fallback_timestamp, null values)
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. Regex trích xuất số hiệu văn bản pháp quy Việt Nam
# ---------------------------------------------------------------------------

_DOCUMENT_CODE_PATTERNS: list[re.Pattern[str]] = [
    # "Số: 109/2024/NĐ-CP" hoặc "No. 89/2025/ND-CP"
    re.compile(
        r"(?:Số|So|No\.?)\s*:?\s*"
        r"(\d{1,5}\s*/\s*\d{4}\s*/\s*[A-ZĐa-zđ\-]+(?:\s*/\s*[A-ZĐa-zđ\-]+)?)",
        re.IGNORECASE,
    ),
    # "123/TB-BGDĐT", "12/2026/QĐ-TTg" nằm trong văn bản
    re.compile(
        r"\b(\d{1,5}/(?:\d{4}/)?(?:NĐ|ND|TT|QĐ|QD|NQ|CT|TB|CV|HD|BC|KH|TTLT)"
        r"-[A-ZĐa-zđ]+(?:\d+)?)\b",
        re.IGNORECASE,
    ),
    # Dạng "Nghị định số 153/2025/NĐ-CP"
    re.compile(
        r"(?:Nghị định|Thông tư|Quyết định|Chỉ thị|Nghị quyết|Công văn)\s+(?:số\s+)?"
        r"(\d{1,5}/\d{4}/[A-ZĐa-zđ\-]+)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# 2. Regex trích xuất ngày ban hành / ngày ký
# ---------------------------------------------------------------------------

# "ngày 29 tháng 8 năm 2024"
_VN_DATE_PATTERN: re.Pattern[str] = re.compile(
    r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE,
)

# "Hà Nội, ngày 15 tháng 01 năm 2022"
_VN_DATE_LOCATION_PATTERN: re.Pattern[str] = re.compile(
    r"(?:Hà Nội|TP\.?\s*HCM|Đà Nẵng|[A-ZĐÀ-Ỹ][a-zàáạảãăắằẳẵặâấầẩẫậ\s]+),\s*"
    r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
    re.IGNORECASE,
)

# "dd/mm/yyyy" hoặc "dd-mm-yyyy"
_NUMERIC_DATE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b"
)

# ---------------------------------------------------------------------------
# 3. Regex nhận diện cơ quan ban hành
# ---------------------------------------------------------------------------

_ISSUING_AUTHORITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(CHÍNH PHỦ)\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(BỘ\s+[A-ZĐÀ-Ỹ\s]+)\s*$", re.MULTILINE),
    re.compile(r"^(QUỐC HỘI)\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(THỦ TƯỚNG CHÍNH PHỦ)\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(ỦY BAN NHÂN DÂN\s+[A-ZĐÀ-Ỹ\s]+)\s*$", re.MULTILINE),
    re.compile(r"^(BỘ\s+CÔNG\s+AN)\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(BỘ\s+TÀI\s+CHÍNH)\s*$", re.MULTILINE | re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# 4. Bộ nhận diện loại tài liệu & Dòng xe VinFast
# ---------------------------------------------------------------------------

_DOCUMENT_TYPE_HINTS: dict[str, list[str]] = {
    "legal": [
        "nghị định", "thông tư", "quyết định", "nghị quyết",
        "chỉ thị", "công văn", "luật", "pháp lệnh",
    ],
    "policy": [
        "chính sách", "policy", "quy chế", "quy định", "điều khoản",
        "bảo hành", "warranty", "bảo hiểm", "insurance",
    ],
    "specs": [
        "thông số kỹ thuật", "specifications", "hướng dẫn sử dụng",
        "technical", "manual", "brochure",
    ],
    "news": [
        "tin tức", "thông cáo", "ra mắt", "press release",
        "news", "bài viết", "đánh giá",
    ],
    "faq": [
        "câu hỏi thường gặp", "faq", "hỏi đáp",
    ],
}

_KNOWN_VINFAST_MODELS: list[str] = [
    "VF 3", "VF 5", "VF 6", "VF 7", "VF 8", "VF 9", "VF Wild",
    "VF e34", "VF MPV 7", "EC Van", "Minio Green", "Herio Green",
    "Nerio Green", "Limo Green", "Evo Grand", "Evo 200", "Feliz S",
    "Feliz", "Klara S", "Klara", "Vento S", "Vento", "Theon S", "Theon",
    "Fadil", "Lux A2.0", "Lux SA2.0", "President",
]


def detect_vehicles(text: str) -> list[str]:
    """Phát hiện các dòng xe VinFast được nhắc đến trong văn bản để phục vụ RAG filtering."""
    found: list[str] = []
    text_sample = text[:5000]
    for model in _KNOWN_VINFAST_MODELS:
        pat = rf"\b{re.escape(model)}\b"
        if re.search(pat, text_sample, re.IGNORECASE) and model not in found:
            found.append(model)
    return found


def _slugify(text: str, max_len: int = 50) -> str:
    """Tạo slug an toàn cho filename / doc_id."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].strip("-")


def generate_doc_id(filename: str) -> str:
    """Tạo doc_id duy nhất định dạng: {slug}_{uuid8}."""
    stem = Path(filename).stem
    slug = _slugify(stem, max_len=40)
    uid = uuid.uuid4().hex[:8]
    return f"doc_{slug}_{uid}"


def compute_file_sha256(file_path: Path) -> str:
    """Tính mã băm SHA256 của file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_document_code(text: str) -> str:
    """Trích xuất số hiệu văn bản pháp quy từ nội dung."""
    head = text[:2000] if len(text) > 2000 else text

    for pattern in _DOCUMENT_CODE_PATTERNS:
        m = pattern.search(head)
        if m:
            code = m.group(1).strip()
            code = re.sub(r"\s*/\s*", "/", code)
            return code
    return ""


def extract_document_title(text: str, *, pdf_title: str = "") -> str:
    """Trích xuất tiêu đề văn bản, lọc bỏ các chuỗi rác như about:blank, untitled."""
    if pdf_title:
        clean_pdf_title = pdf_title.strip()
        invalid_titles = {"about:blank", "untitled", "microsoft word", "document"}
        if (
            len(clean_pdf_title) > 5
            and clean_pdf_title.lower() not in invalid_titles
            and not clean_pdf_title.startswith("http")
        ):
            return clean_pdf_title

    head = text[:3000] if len(text) > 3000 else text

    # Kiểm tra Markdown heading #
    m_head = re.search(r"^#\s+(.+)$", head, re.MULTILINE)
    if m_head:
        h_title = m_head.group(1).strip()
        if len(h_title) > 5 and h_title.lower() not in {"about:blank", "untitled"}:
            return h_title

    lines = head.split("\n")

    # Tìm dòng in hoa dài nhất (heuristic cho tiêu đề pháp lý VN)
    best_title = ""
    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 10:
            continue
        alpha_chars = [c for c in stripped if c.isalpha()]
        if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.7:
            if any(p.search(stripped) for p in _ISSUING_AUTHORITY_PATTERNS):
                continue
            if len(stripped) > len(best_title):
                best_title = stripped

    return best_title if best_title else ""


def extract_issuing_authority(text: str) -> str:
    """Nhận diện cơ quan / tổ chức ban hành từ đầu tài liệu."""
    head = text[:1500] if len(text) > 1500 else text

    for pattern in _ISSUING_AUTHORITY_PATTERNS:
        m = pattern.search(head)
        if m:
            return m.group(1).strip()
    return ""


def extract_effective_date(text: str) -> str:
    """Trích xuất ngày ban hành / ngày ký từ nội dung văn bản (ISO 8601 YYYY-MM-DD)."""
    head = text[:3000] if len(text) > 3000 else text

    m = _VN_DATE_LOCATION_PATTERN.search(head)
    if m:
        return _format_vn_date(m.group(1), m.group(2), m.group(3))

    m = _VN_DATE_PATTERN.search(head)
    if m:
        return _format_vn_date(m.group(1), m.group(2), m.group(3))

    m = _NUMERIC_DATE_PATTERN.search(head)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return ""


def _format_vn_date(day_str: str, month_str: str, year_str: str) -> str:
    """Format ngày tháng Việt Nam thành ISO 8601."""
    try:
        day = int(day_str)
        month = int(month_str)
        year = int(year_str)
        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, TypeError):
        pass
    return ""


def detect_document_type(
    text: str,
    *,
    filename: str = "",
    doc_type_hint: str = "",
) -> str:
    """Tự động phân loại tài liệu (legal, policy, specs, news, faq)."""
    if doc_type_hint:
        hint_clean = doc_type_hint.lower().replace("_document", "").replace("technical_manual", "specs")
        if hint_clean in {"legal", "policy", "specs", "news", "faq"}:
            return hint_clean

    combined = f"{filename} {text[:3000]}".lower()

    if any(k in combined for k in _DOCUMENT_TYPE_HINTS["faq"]):
        return "faq"
    if any(k in combined for k in _DOCUMENT_TYPE_HINTS["legal"]):
        return "legal"
    if any(k in combined for k in _DOCUMENT_TYPE_HINTS["specs"]):
        return "specs"
    if any(k in combined for k in _DOCUMENT_TYPE_HINTS["policy"]):
        return "policy"
    if any(k in combined for k in _DOCUMENT_TYPE_HINTS["news"]):
        return "news"

    return "general"


def detect_language(text: str) -> str:
    """Phát hiện ngôn ngữ dựa trên mật độ ký tự có dấu tiếng Việt."""
    if not text:
        return "vi"

    sample = text[:5000]
    vn_diacritics = re.findall(
        r"[àáạảãăắằẳẵặâấầẩẫậèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợ"
        r"ùúụủũưứừửữựỳýỵỷỹđ"
        r"ÀÁẠẢÃĂẮẰẲẴẶÂẤẦẨẪẬÈÉẸẺẼÊẾỀỂỄỆÌÍỊỈĨÒÓỌỎÕÔỐỒỔỖỘƠỚỜỞỠỢ"
        r"ÙÚỤỦŨƯỨỪỬỮỰỲÝỴỶỸĐ]",
        sample,
    )
    alpha_chars = re.findall(r"[a-zA-ZÀ-ỹĐđ]", sample)

    if alpha_chars and len(vn_diacritics) / len(alpha_chars) > 0.02:
        return "vi"
    return "en"


def estimate_tokens(text: str, *, language: str = "vi") -> int:
    """Ước tính số token: ~3.8 ký tự / token cho tiếng Việt."""
    if not text:
        return 0
    divisor = 3.8 if language == "vi" else 4.0
    return int(len(text) / divisor)


def build_frontmatter_metadata(
    *,
    file_path: Path,
    base_dir: Path,
    cleaned_text: str,
    raw_text: str = "",
    total_pages: int = 0,
    has_tables: bool = False,
    pdf_title: str = "",
    pdf_creation_date: str = "",
    pdf_mod_date: str = "",
    doc_type_hint: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Xây dựng bộ metadata chuẩn hóa tối ưu cho AI RAG & LLMOps.

    Loại bỏ toàn bộ trường rác (file size, file system timestamps, fallback timestamp, dev stage),
    chỉ lưu trữ các trường phục vụ tìm kiếm ngữ nghĩa, lọc metadata và trích dẫn nguồn.
    """
    content_for_analysis = raw_text if raw_text else cleaned_text
    rel_path = str(file_path.relative_to(base_dir)).replace("\\", "/")

    # 1. doc_id (Định danh duy nhất)
    doc_id = ""
    if extra_metadata and extra_metadata.get("doc_id"):
        doc_id = extra_metadata["doc_id"]
    else:
        doc_id = generate_doc_id(file_path.stem)

    # 2. Tiêu đề chuẩn xác
    clean_title = ""
    if extra_metadata and extra_metadata.get("title"):
        clean_title = extra_metadata["title"].strip()
    elif pdf_title and pdf_title.lower() not in {"about:blank", "untitled", ""}:
        clean_title = pdf_title.strip()
    else:
        clean_title = extract_document_title(content_for_analysis)

    if not clean_title or clean_title.lower() in {"about:blank", "untitled"}:
        clean_title = file_path.stem.replace("_", " ").title()

    # 3. Phân loại danh mục (category)
    category = ""
    if extra_metadata and extra_metadata.get("category"):
        cat_raw = str(extra_metadata["category"]).lower()
        if "faq" in cat_raw:
            category = "faq"
        elif "spec" in cat_raw:
            category = "specs"
        elif "chính sách" in cat_raw or "policy" in cat_raw:
            category = "policy"
        elif "tin tức" in cat_raw or "news" in cat_raw:
            category = "news"
        else:
            category = cat_raw
    else:
        category = detect_document_type(
            content_for_analysis, filename=file_path.name, doc_type_hint=doc_type_hint
        )

    # 4. Domain & Nguồn trích dẫn (provenance)
    domain = (extra_metadata.get("domain") if extra_metadata else "") or ""
    if not domain:
        fn_lower = file_path.name.lower()
        if "vinfast" in fn_lower:
            domain = "vinfastauto.com"
        elif "vgreen" in fn_lower:
            domain = "vgreen.net"
        elif "xehay" in fn_lower:
            domain = "xehay.vn"

    source = (extra_metadata.get("source_url") if extra_metadata else "") or rel_path

    # 5. Ngày tháng hiệu lực / ban hành
    effective_date = extract_effective_date(content_for_analysis)
    pub_date = (extra_metadata.get("published_date") if extra_metadata else "") or ""
    if not effective_date and pub_date:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", pub_date.strip())
        if m:
            effective_date = f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        elif re.match(r"^\d{4}-\d{2}-\d{2}", pub_date.strip()):
            effective_date = pub_date.strip()[:10]

    # 6. Thuộc tính pháp lý (nếu có)
    document_code = extract_document_code(content_for_analysis)
    issuing_authority = extract_issuing_authority(content_for_analysis)

    # 7. Dòng xe liên quan (target_vehicles - phục vụ RAG vehicle filter)
    candidates: list[str] = []
    if extra_metadata and extra_metadata.get("target_vehicles"):
        candidates = extra_metadata["target_vehicles"]
    elif extra_metadata and extra_metadata.get("related_models"):
        candidates = extra_metadata["related_models"]

    vehicles: list[str] = []
    text_for_veh = f"{clean_title} {cleaned_text}"
    detected = detect_vehicles(text_for_veh)

    if candidates:
        if len(candidates) <= 5:
            vehicles = [c for c in candidates if isinstance(c, str) and c.strip()]
        else:
            # Danh sách quá nhiều xe do cào nhầm menu navbar -> chỉ giữ xe thực sự xuất hiện trong nội dung
            vehicles = [c for c in candidates if c in detected]
    else:
        vehicles = detected

    # 8. Tóm tắt nội dung
    summary = (extra_metadata.get("summary") if extra_metadata else "") or ""
    if summary:
        summary = re.sub(r"\s*\|\s*(?:VinFast|Techcombank|Xe Hay|V-Green)\s*$", "", summary, flags=re.IGNORECASE).strip()
        if (
            summary.lower() == clean_title.lower()
            or (len(clean_title) > 20 and clean_title.lower() in summary.lower() and len(summary) < len(clean_title) + 20)
            or len(summary) < 15
        ):
            summary = ""

    # 9. Ngôn ngữ tài liệu
    language = detect_language(cleaned_text)

    # Build clean dictionary (chỉ giữ trường phục vụ AI RAG, loại bỏ toàn bộ metrics kỹ thuật rác)
    meta: dict[str, Any] = {
        "doc_id": doc_id,
        "title": clean_title,
        "category": category,
        "source": source,
    }

    if extra_metadata and extra_metadata.get("subcategory"):
        meta["subcategory"] = extra_metadata["subcategory"]

    if domain:
        meta["domain"] = domain

    if effective_date:
        meta["effective_date"] = effective_date

    if document_code:
        meta["document_code"] = document_code

    if issuing_authority:
        meta["issuing_authority"] = issuing_authority

    if vehicles:
        meta["target_vehicles"] = vehicles

    if summary:
        meta["summary"] = summary

    if language:
        meta["language"] = language

    return meta
