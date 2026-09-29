"""src/data_pipeline/crawlers/crawler_utils.py
Các hàm tiện ích dùng chung cho các module crawler VinFast Auto:
- Tải nội dung web HTTP an toàn (urllib kèm cơ chế fallback curl.exe cho Cloudflare)
- Làm sạch và trích xuất văn bản từ HTML
- Lưu trữ dữ liệu chuẩn hóa dạng JSON có cấu trúc
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

# Tự động cấu hình mã hóa UTF-8 cho stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
LANDING_DIR = DATA_DIR / "landing"

RELATIONAL_DIR = LANDING_DIR / "relational"
POLICIES_DIR = LANDING_DIR / "policies"
NEWS_DIR = LANDING_DIR / "news"
LEGAL_DIR = LANDING_DIR / "legal"
FAQS_DIR = LANDING_DIR / "faqs"
SPECS_DIR = LANDING_DIR / "specs"

# Danh mục các dòng xe ô tô và xe máy đã crawl được từ bảng giá
CRAWLED_CAR_MODELS = [
    "VF 2",
    "VF 3",
    "VF 5",
    "VF 6",
    "VF 7",
    "VF 8",
    "VF 8 The All New",
    "VF 9",
    "VF MPV 7",
    "VF Wild",
    "Limo Green",
    "Herio Green",
    "Minio Green",
    "EC Van",
]

CRAWLED_BIKE_MODELS = [
    "Evo Grand",
    "Evo Grand Lite",
    "Evo-Lite-Neo",
    "Evo-Neo",
    "Evo200",
    "Evo200 Lite",
    "Feliz 2025",
    "Feliz Lite",
    "Feliz S",
    "Feliz-Neo",
    "Flazz",
    "Klara S (2022)",
    "Klara-Neo",
    "Motio",
    "Theon-S",
    "Vento-Neo",
    "Vento-S",
    "Vero X",
    "Zgoo",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_current_iso_timestamp() -> str:
    """Trả về thời gian hiện tại định dạng ISO 8601 UTC."""
    return datetime.now(UTC).isoformat()


def random_delay(
    min_seconds: float = 1.0, max_seconds: float = 2.2, verbose: bool = False
) -> float:
    """Tạm dừng ngẫu nhiên giữa các request để giả lập người dùng thật, tránh bị chặn bot/rate-limit."""
    delay = round(random.uniform(min_seconds, max_seconds), 2)
    if verbose:
        print(f"   ⏳ Tạm dừng {delay}s để tránh kích hoạt cơ chế chặn bot...")
    time.sleep(delay)
    return delay


def compute_content_hash(text: str) -> str:
    """Tạo mã băm MD5 để định danh nội dung văn bản, phục vụ RAG deduplication và kiểm tra freshness."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def build_rag_metadata(
    *,
    doc_id: str,
    doc_type: str,
    title: str,
    category: str,
    subcategory: str = "",
    source_url: str = "",
    domain: str = "",
    applies_to: str = "Toàn bộ",
    related_models: list[str] | None = None,
    raw_content: str = "",
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tạo đối tượng metadata chuẩn hóa phục vụ phân đoạn (chunking) và vector hóa RAG.

    Bao gồm đầy đủ các thông tin: doc_id, doc_type, domain, language, category,
    related_models, hash nội dung, số lượng ký tự và từ, timestamp thu thập.
    """
    now_iso = get_current_iso_timestamp()
    clean_text = raw_content.strip() if raw_content else ""
    words = clean_text.split()

    if not domain:
        if source_url:
            parsed = urllib.parse.urlparse(source_url).netloc
            domain = parsed.replace("www.", "") if parsed else "vinfastauto.com"
        else:
            domain = "vinfastauto.com"

    meta: dict[str, Any] = {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "title": title,
        "domain": domain,
        "source_url": source_url,
        "language": "vi",
        "category": category,
        "subcategory": subcategory or category,
        "applies_to": applies_to,
        "related_models": related_models or [],
        "is_general_info": len(related_models or []) == 0,
        "pipeline_stage": "landing_raw",
        "crawled_at": now_iso,
        "content_hash": compute_content_hash(clean_text) if clean_text else "",
        "char_count": len(clean_text),
        "word_count": len(words),
    }
    if extra_fields:
        meta.update(extra_fields)
    return meta



def fetch_html(url: str, timeout: int = 15) -> str:
    """Tải nội dung HTML từ URL.

    Ưu tiên sử dụng urllib, tự động fallback sang curl.exe nếu gặp lỗi chặn
    bởi Cloudflare (403 Forbidden hoặc TLS fingerprint).
    """
    socket.setdefaulttimeout(timeout)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        # Fallback sang curl.exe gốc của Windows
        cmd = [
            "curl.exe",
            "-sL",
            "--http1.1",
            "--compressed",
            "-m",
            str(timeout + 5),
            url,
            "-H",
            f"User-Agent: {DEFAULT_USER_AGENT}",
            "-H",
            "Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout + 10,
        )
        return res.stdout or ""


def clean_html(html_content: str, strip_nav: bool = False) -> str:
    """Làm sạch HTML thành văn bản thuần túy, giữ ngắt dòng hợp lý."""
    if not html_content:
        return ""
    text = html_content
    if strip_nav:
        text = re.sub(
            r"<(?:header|footer|nav|aside)[^>]*>.*?</(?:header|footer|nav|aside)>",
            "",
            text,
            flags=re.DOTALL | re.I,
        )
    text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"</tr>", "\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)

    # Chuẩn hóa khoảng trắng và dòng trống
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    result_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                result_lines.append("")
                prev_empty = True
        else:
            result_lines.append(line)
            prev_empty = False
    return "\n".join(result_lines).strip()


def save_json(data: Any, file_path: Path, indent: int = 2) -> None:
    """Lưu dữ liệu cấu trúc vào file JSON với định dạng UTF-8 đẹp mắt."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def _compile_model_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Biên dịch trước toàn bộ regex cho các model xe một lần duy nhất lúc khởi tạo module."""
    patterns: list[tuple[re.Pattern[str], str]] = []

    # 1. Ô tô điện
    for car in CRAWLED_CAR_MODELS:
        car_clean = car.strip()
        if "GREEN" in car_clean.upper():
            pat = r"\b" + re.escape(car_clean.upper()).replace(r"\ ", r"\s+") + r"\b"
            patterns.append((re.compile(pat, re.IGNORECASE), car))
            continue

        if car_clean.upper() == "EC VAN":
            patterns.append((re.compile(r"\bEC\s*VAN\b", re.IGNORECASE), car))
            continue

        if "THE ALL NEW" in car_clean.upper():
            patterns.append(
                (re.compile(r"\bVF\s*8\s+(?:THE\s+ALL\s+NEW|ALL\s+NEW)\b", re.IGNORECASE), car)
            )
            continue

        if car_clean.upper() == "VF WILD":
            patterns.append((re.compile(r"\bVF\s*WILD\b", re.IGNORECASE), car))
            continue

        if car_clean.upper() == "VF MPV 7":
            patterns.append((re.compile(r"\bVF\s*MPV\s*7\b", re.IGNORECASE), car))
            continue

        m = re.match(r"^VF\s*(\d+)$", car_clean, re.I)
        if m:
            num = m.group(1)
            patterns.append((re.compile(rf"\bVF[\s\-]?{num}\b", re.IGNORECASE), car))
            continue

        pat = r"\b" + re.escape(car_clean.upper()).replace(r"\ ", r"[\s\-]+") + r"\b"
        patterns.append((re.compile(pat, re.IGNORECASE), car))

    # 2. Xe máy điện
    for bike in CRAWLED_BIKE_MODELS:
        bike_clean = bike.strip()
        if "KLARA S" in bike_clean.upper():
            pat = r"\bKLARA[\s\-]+S(?:\s*\(?2022\)?)?\b"
        elif "EVO200" in bike_clean.upper():
            suffix = bike_clean.upper().replace("EVO200", "").strip()
            suffix_pat = rf"\s+{re.escape(suffix)}" if suffix else ""
            pat = rf"\bEVO\s*200{suffix_pat}\b"
        else:
            tokens = [re.escape(t) for t in re.split(r"[\s\-]+", bike_clean.upper()) if t]
            pat = r"\b" + r"[\s\-]+".join(tokens) + r"\b"

        patterns.append((re.compile(pat, re.IGNORECASE), bike))

    return patterns


_COMPILED_MODEL_PATTERNS: list[tuple[re.Pattern[str], str]] = _compile_model_patterns()

# Bộ lọc nhanh (Fast hint regex): nếu đoạn văn bản lớn không hề chứa từ khóa nào về xe, trả về [] ngay lập tức
_VEHICLE_HINT_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:VF|Limo|Herio|Minio|Van|Evo|Feliz|Klara|Theon|Vento|Flazz|Motio|Vero|Zgoo|Wild|MPV)\b",
    re.IGNORECASE,
)


def extract_related_models(text: str) -> list[str]:
    """Phát hiện và trích xuất danh sách các dòng xe (ô tô & xe máy điện) được nhắc tới trong văn bản.

    Tối ưu hóa hiệu năng và độ chính xác (PR Review feedback):
    1. Precompiled Regex: Toàn bộ pattern được biên dịch trước lúc nạp module, tránh lặp lại
       re.compile và re.split trong mỗi lần gọi hàm.
    2. Fast-reject O(1): Kiểm tra nhanh bằng _VEHICLE_HINT_PATTERN trên văn bản lớn để bỏ qua
       các văn bản không liên quan mà không phải duyệt qua 30+ regex.
    3. Strict Word Boundaries: Chống hoàn toàn false positive (evolution, green, VF 30).
    """
    if not text:
        return []

    # Bước lọc nhanh O(1) chống quét lãng phí trên văn bản dài không chứa từ khóa xe
    if not _VEHICLE_HINT_PATTERN.search(text):
        return []

    found: set[str] = set()
    for compiled_pat, model_name in _COMPILED_MODEL_PATTERNS:
        if compiled_pat.search(text):
            found.add(model_name)

    return sorted(found)

