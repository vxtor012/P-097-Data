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


def extract_related_models(text: str) -> list[str]:
    """Phát hiện và trích xuất danh sách các dòng xe (ô tô & xe máy điện) được nhắc tới trong văn bản.

    Cải tiến chống false positives (PR review feedback):
    1. Sử dụng word boundary (\\b) nghiêm ngặt cho tất cả các model, tránh match nhầm các từ
       như 'evolution', 'revolution', 'development' (với Evo) hay 'green' trong bài viết trạm sạc.
    2. Chuẩn hóa linh hoạt khoảng trắng và dấu gạch nối (ví dụ: 'Evo 200 Lite' / 'Evo200 Lite',
       'Theon-S' / 'Theon S', 'VF 8' / 'VF8').
    3. Ưu tiên so khớp cụm từ cụ thể dài hơn trước để gán metadata chính xác nhất.
    """
    if not text:
        return []

    text_upper = text.upper()
    found: set[str] = set()

    # 1. Trích xuất ô tô điện
    for car in CRAWLED_CAR_MODELS:
        car_clean = car.strip()
        # Xử lý các dòng xe có thương hiệu Green (Limo Green, Herio Green, Minio Green)
        if "GREEN" in car_clean.upper():
            pat = r"\b" + re.escape(car_clean.upper()).replace(r"\ ", r"\s+") + r"\b"
            if re.search(pat, text_upper):
                found.add(car)
            continue

        # Xử lý xe van
        if car_clean.upper() == "EC VAN":
            if re.search(r"\bEC\s*VAN\b", text_upper):
                found.add(car)
            continue

        # Xử lý xe concept / đặc biệt (VF Wild, VF MPV 7, VF 8 The All New)
        if "THE ALL NEW" in car_clean.upper():
            if re.search(r"\bVF\s*8\s+(?:THE\s+ALL\s+NEW|ALL\s+NEW)\b", text_upper):
                found.add(car)
            continue

        if car_clean.upper() == "VF WILD":
            if re.search(r"\bVF\s*WILD\b", text_upper):
                found.add(car)
            continue

        if car_clean.upper() == "VF MPV 7":
            if re.search(r"\bVF\s*MPV\s*7\b", text_upper):
                found.add(car)
            continue

        # Các dòng xe VF số (VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 9)
        m = re.match(r"^VF\s*(\d+)$", car_clean, re.I)
        if m:
            num = m.group(1)
            # Match "VF 3", "VF3", "VF-3", tránh false positive như "VF 30"
            pat = rf"\bVF[\s\-]?{num}\b"
            if re.search(pat, text_upper):
                found.add(car)
            continue

        # Fallback chuẩn cho các ô tô khác
        pat = r"\b" + re.escape(car_clean.upper()).replace(r"\ ", r"[\s\-]+") + r"\b"
        if re.search(pat, text_upper):
            found.add(car)

    # 2. Trích xuất xe máy điện
    for bike in CRAWLED_BIKE_MODELS:
        bike_clean = bike.strip()
        # Chuẩn hóa regex cho xe máy: hỗ trợ dấu cách, gạch nối linh hoạt giữa các từ
        # Ví dụ: "Evo200 Lite" -> r"\bEVO\s*200\s+LITE\b"
        # "Klara S (2022)" -> r"\bKLARA[\s\-]+S(?:\s*\(?2022\)?)?\b"
        if "KLARA S" in bike_clean.upper():
            pat = r"\bKLARA[\s\-]+S(?:\s*\(?2022\)?)?\b"
        elif "EVO200" in bike_clean.upper():
            suffix = bike_clean.upper().replace("EVO200", "").strip()
            suffix_pat = rf"\s+{re.escape(suffix)}" if suffix else ""
            pat = rf"\bEVO\s*200{suffix_pat}\b"
        else:
            # Tách các từ và dấu nối
            tokens = [re.escape(t) for t in re.split(r"[\s\-]+", bike_clean.upper()) if t]
            pat = r"\b" + r"[\s\-]+".join(tokens) + r"\b"

        if re.search(pat, text_upper):
            found.add(bike)

    return sorted(found)

