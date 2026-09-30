"""src/data_pipeline/task1_crawl_data.py
Task 1: Thu thập dữ liệu thô (Raw Data) lưu trữ vào tầng Bronze & data/pdf theo Medallion Architecture.

1. NGUYÊN TẮC THU THẬP DỮ LIỆU:
   - `gia_ca_lan_banh`       : Crawl từ VinFast Auto API RollingUpCost -> lưu JSON thô vào `data/bronze/vinfast/relational/` (Single Source of Truth, không crawl giá từ web ngoài).
   - `thong_so_ky_thuat`     : CHỈ CRAWL TỪ TRANG CHỦ VINFAST & BROCHURE PDF CHÍNH HÃNG -> lưu PDF vào `data/pdf/thong_so_ky_thuat/` & HTML vào `data/bronze/vinfast/articles/`.
   - `chinh_sach_uu_dai`     : Crawl từ VinFast Auto (vinfastauto.com/vn_vi/uu-dai) & văn bản ưu đãi -> lưu PDF vào `data/pdf/chinh_sach_uu_dai/` & HTML vào `data/bronze/vinfast/articles/`.
   - `thu_tuc_phap_ly`       : Lưu các tài liệu pháp lý (Nghị định, Thông tư, Luật) tại `data/pdf/thu_tuc_phap_ly/` và HTML bảo hiểm tại `data/bronze/web_scraping/raw_html/`.
   - `trai_nghiem_danh_gia`  : Crawl bài viết review xe uy tín -> lưu vào `data/bronze/web_scraping/raw_html/`.
   - `tai_chinh_tra_gop`     : Crawl thông tin lãi suất ngân hàng Techcombank -> lưu vào `data/bronze/web_scraping/raw_html/`.
   - `he_thong_tram_sac`     : Crawl trạm sạc V-GREEN & VinFast -> lưu vào `data/bronze/web_scraping/raw_html/` hoặc `vinfast/`.

2. CẤU TRÚC THƯ MỤC LƯU TRỮ:
   data/
   ├── bronze/
   │   ├── vinfast/
   │   │   ├── relational/
   │   │   │   └── vinfast_rolling_raw_snapshot.json
   │   │   ├── faq/
   │   │   │   └── vinfast_faq_raw.html
   │   │   ├── articles/
   │   │   └── vinfast_sources_manifest.json
   │   └── web_scraping/
   │       ├── raw_html/
   │       └── web_scraping_manifest.json
   └── pdf/
       ├── thu_tuc_phap_ly/       (18+ văn bản luật, nghị định, thông tư)
       ├── thong_so_ky_thuat/     (brochure PDF thông số chi tiết các dòng xe)
       ├── chinh_sach_uu_dai/     (tài liệu PDF chính sách & ưu đãi)
       └── pdf_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import http.cookiejar
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
from pathlib import Path
from typing import Any

# Tự động cấu hình mã hóa UTF-8 cho stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Định vị thư mục gốc
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
SOURCES_CSV_PATH = DATA_DIR / "sources.csv"

# Đường dẫn tầng Bronze & PDF
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_VINFAST_DIR = BRONZE_DIR / "vinfast"
BRONZE_WEBSCRAPING_DIR = BRONZE_DIR / "web_scraping"

PDF_DIR = DATA_DIR / "pdf"
PDF_LEGAL_DIR = PDF_DIR / "thu_tuc_phap_ly"
PDF_SPECS_DIR = PDF_DIR / "thong_so_ky_thuat"
PDF_PROMO_DIR = PDF_DIR / "chinh_sach_uu_dai"

# Endpoint & URL nguồn chính hãng VinFast
VINFAST_ROLLING_API = (
    "https://shop.vinfastauto.com/on/demandware.store/Sites-app_vinfast_vn-Site/vi_VN/"
    "RollingUpCost-GetInfoRolling"
)
VINFAST_ROLLING_PAGE = "https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh"
VINFAST_FAQ_PAGE = "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap"

# Danh mục các nguồn Brochure thông số kỹ thuật xe VinFast chính hãng
VINFAST_BROCHURE_TARGETS: list[dict[str, str]] = [
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 3",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/16062026-Brochure-VF-3.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf3.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 6",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/14052026/VF%206_Brochure_Final_130526%20(12AM)_compressed.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf6.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 7",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/10042026-Brochur-%20VF-7.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf7.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 8",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF8_Brochure_03022026.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf8.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 8 The All New",
        "url": "https://static-cms-prod.vinfastauto.com/brochure/26052026/VF%208%20The%20he%20moi_Brochure_final%2020.05.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf8_the_all_new.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF 9",
        "url": "https://storage.googleapis.com/vinfast-data-01/brochure/VF%209_%20Brochure.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf9.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast EC Van",
        "url": "https://static-cms-prod.vinfastauto.com/brochure-ec-van-040726-e.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_ecvan.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast VF MPV 7",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/05022026-Brochure-VF-MPV-7.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_vf_mpv7.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast Herio Green",
        "url": "https://static-cms-prod.vinfastauto.com/06082025-brochure-herio.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_herio_green.pdf",
    },
    {
        "title": "Brochure Thông số kỹ thuật VinFast Limo Green",
        "url": "https://static-cms-prod.vinfastauto.com/09012026-brochure-limo-green.pdf",
        "category": "thong_so_ky_thuat",
        "filename": "brochure_vinfast_limo_green.pdf",
    },
]

VINFAST_POLICY_PAGES = [
    "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/",
    "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-oto",
]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_current_iso_timestamp() -> str:
    """Thời gian hiện tại định dạng ISO 8601 UTC."""
    return datetime.now(UTC).isoformat()


def save_json(data: Any, file_path: Path, indent: int = 2) -> None:
    """Lưu dữ liệu cấu trúc vào file JSON định dạng UTF-8."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def random_delay(min_s: float = 0.6, max_s: float = 1.2) -> None:
    """Tạm dừng ngẫu nhiên tránh rate-limit."""
    time.sleep(round(random.uniform(min_s, max_s), 2))


def fetch_url_content(url: str, timeout: int = 8) -> str:
    """Tải nội dung từ URL (ưu tiên curl.exe -4, fallback sang urllib)."""
    cmd = [
        "curl.exe", "-4", "-sL", "--http1.1", "--compressed",
        "-m", str(timeout), url,
        "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
        "-H", "Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    ]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout + 2
        )
        if res.stdout and len(res.stdout) > 200:
            return res.stdout
    except Exception:
        pass

    # Fallback sang urllib
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
        return ""


def download_binary_pdf(url: str, target_path: Path, timeout: int = 20) -> bool:
    """Tải file nhị phân (PDF) về thư mục cục bộ và chỉ chấp nhận file bắt đầu bằng header %PDF."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    clean_url = urllib.parse.quote(url, safe=":/%?=&+")
    cmd = [
        "curl.exe", "-4", "-sL", "--http1.1",
        "-m", str(timeout), clean_url,
        "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
        "-o", str(target_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout + 3)
        if target_path.exists():
            if target_path.stat().st_size > 1000:
                header = open(target_path, "rb").read(10)
                if header.startswith(b"%PDF"):
                    return True
            target_path.unlink(missing_ok=True)
    except Exception:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
    return False


# ==============================================================================
# 1. CRAWL DỮ LIỆU QUAN HỆ VINFAST (RAW JSON RELATIONAL SNAPSHOT)
# ==============================================================================

def crawl_vinfast_relational_raw() -> dict[str, Any]:
    """Crawl snapshot JSON thô từ API RollingUpCost của VinFast lưu vào Bronze."""
    print("\n[1/4] 📊 CRAWL DỮ LIỆU QUAN HỆ THÔ TỪ VINFAST API (GIÁ VÀ CHI PHÍ LĂN BÁNH)...")
    target_dir = BRONZE_VINFAST_DIR / "relational"
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = target_dir / "vinfast_rolling_raw_snapshot.json"

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": VINFAST_ROLLING_PAGE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        handshake = urllib.request.Request(VINFAST_ROLLING_PAGE, headers={"User-Agent": DEFAULT_USER_AGENT})
        with opener.open(handshake, timeout=15) as _:
            pass
    except Exception as e:
        print(f"⚠️ Handshake cảnh báo: {e}")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🌐 Đang gọi API: {VINFAST_ROLLING_API} (lần {attempt}/{max_retries})...")
            req = urllib.request.Request(VINFAST_ROLLING_API, headers=headers)
            with opener.open(req, timeout=25) as resp:
                content = resp.read().decode("utf-8")
                raw_json = json.loads(content)
                if isinstance(raw_json, dict) and ("vehicles" in raw_json or "objects" in raw_json):
                    save_json(raw_json, snapshot_file)
                    print(f"✅ Đã lưu raw snapshot: {snapshot_file.name} ({len(content):,} bytes)")
                    return {
                        "status": "success",
                        "file": str(snapshot_file),
                        "bytes": len(content),
                    }
        except Exception as err:
            print(f"⚠️ Lần {attempt} thất bại: {err}")
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))

    if snapshot_file.exists():
        print(f"📂 Đã có snapshot dự phòng tại: {snapshot_file.name}")
        return {"status": "fallback", "file": str(snapshot_file), "bytes": snapshot_file.stat().st_size}

    raise RuntimeError("Không thể tải raw API VinFast và chưa có snapshot!")


# ==============================================================================
# 2. CRAWL CÂU HỎI THƯỜNG GẶP VINFAST (RAW FAQ HTML)
# ==============================================================================

def crawl_vinfast_faq_raw() -> dict[str, Any]:
    """Crawl trang FAQ chính thức của VinFast lưu HTML thô vào Bronze."""
    print("\n[2/4] ❓ CRAWL FAQ THÔ TỪ TRANG CHỦ VINFAST...")
    target_dir = BRONZE_VINFAST_DIR / "faq"
    target_dir.mkdir(parents=True, exist_ok=True)
    html_file = target_dir / "vinfast_faq_raw.html"

    print(f"🌐 Đang tải: {VINFAST_FAQ_PAGE}")
    html = fetch_url_content(VINFAST_FAQ_PAGE)
    if not html:
        print("❌ Không tải được nội dung FAQ!")
        return {"status": "error", "bytes": 0}

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Đã lưu raw FAQ HTML: {html_file.name} ({len(html):,} chars)")
    return {"status": "success", "file": str(html_file), "bytes": len(html)}


# ==============================================================================
# 3. CRAWL BÀI VIẾT ƯU ĐÃI TỪ TRANG CHỦ VINFAST (RAW HTML)
# ==============================================================================

def crawl_vinfast_uudai_articles(max_pages: int = 3) -> list[dict[str, Any]]:
    """Crawl toàn bộ các bài viết ưu đãi và khuyến mại Ô TÔ ĐIỆN từ vinfastauto.com/vn_vi/uu-dai lưu vào Bronze."""
    print("\n[3/5] 🎁 CRAWL CÁC BÀI VIẾT ƯU ĐÃI Ô TÔ ĐIỆN TỪ TRANG CHỦ VINFAST (UU-DAI)...")
    articles_dir = BRONZE_VINFAST_DIR / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    from bs4 import BeautifulSoup

    motorbike_keywords = [
        "xe-may", "xe máy", "xmd", "xe dap", "xe-dap", "xedap", "feliz",
        "evo", "klara", "vento", "theon", "viper", "drgnfly", "ebike",
        "e-scooter", "xe hai banh", "xe 2 banh", "scooter"
    ]

    # Dọn dẹp các bài viết xe máy cũ nếu có
    for f in list(articles_dir.glob("*.html")):
        if any(k in f.name.lower() for k in motorbike_keywords):
            f.unlink(missing_ok=True)

    seen_urls: set[str] = set()
    promo_articles: list[dict[str, str]] = []

    # Quét qua các trang phân trang ưu đãi
    for page_idx in range(0, max_pages):
        page_url = f"https://vinfastauto.com/vn_vi/uu-dai?page={page_idx}" if page_idx > 0 else "https://vinfastauto.com/vn_vi/uu-dai"
        print(f"🌐 Đang quét danh sách ưu đãi: {page_url}...")
        html = fetch_url_content(page_url, timeout=12)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = a["href"].strip()
            t = a.get_text(strip=True)

            # Bỏ qua hoàn toàn tin tức xe máy / xe đạp điện
            if any(k in h.lower() or k in t.lower() for k in motorbike_keywords):
                continue

            # Lọc các liên kết bài viết ưu đãi ô tô
            if any(k in h for k in [
                "uu-dai", "khuyen-mai", "chuong-trinh", "vi-tuong-lai-xanh",
                "thu-xang-doi-dien", "mcredit", "tang-bao-hiem",
                "mua-1-tang-1", "chuyen-doi-xanh", "tri-an"
            ]) and h not in ["/vn_vi/uu-dai", "https://vinfastauto.com/vn_vi/uu-dai"]:
                full_url = f"https://vinfastauto.com{h}" if h.startswith("/") else h
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    slug_title = h.split("/")[-1].replace(".html", "").replace("-", " ").capitalize()
                    promo_articles.append({
                        "url": full_url,
                        "title": t or slug_title,
                    })

    print(f"📄 Tìm thấy tổng cộng {len(promo_articles)} bài viết ưu đãi ô tô điện trên trang VinFast.")
    manifest_entries: list[dict[str, Any]] = []

    for idx, item in enumerate(promo_articles, 1):
        url = item["url"]
        title = item["title"]
        slug = url.split("/")[-1].replace(".html", "").replace("-", "_").replace("%20", "_").replace("%25", "pct")
        slug = re.sub(r"[^a-zA-Z0-9_]+", "", slug)
        filename = f"vinfastauto_com_vn_vi_{slug}.html"
        dest_file = articles_dir / filename

        print(f"🌐 [{idx}/{len(promo_articles)}] Đang tải: {title[:42]}...")
        art_html = fetch_url_content(url, timeout=12)
        if art_html and len(art_html) > 500:
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(art_html)
            print(f"   ✅ Đã lưu -> {filename} ({len(art_html):,} bytes)")
            manifest_entries.append({
                "title": title,
                "url": url,
                "category": "chinh_sach_uu_dai",
                "domain": "vinfastauto.com",
                "file": filename,
                "bytes": len(art_html),
                "crawled_at": get_current_iso_timestamp(),
            })
        else:
            print(f"   ⚠️ Không tải được nội dung từ {url}")
        random_delay(0.2, 0.5)

    # Cập nhật vinfast_sources_manifest.json (chỉ giữ file ô tô)
    manifest_path = BRONZE_VINFAST_DIR / "vinfast_sources_manifest.json"
    existing_manifest: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                raw_list = json.load(f)
                existing_manifest = [
                    e for e in raw_list
                    if not any(k in e.get("file", "").lower() or k in e.get("title", "").lower() for k in motorbike_keywords)
                ]
        except Exception:
            existing_manifest = []

    existing_files = {e.get("file") for e in existing_manifest}
    for entry in manifest_entries:
        if entry["file"] not in existing_files:
            existing_manifest.append(entry)

    save_json(existing_manifest, manifest_path)
    return manifest_entries


# ==============================================================================
# 4. CRAWL TÀI LIỆU PDF (CHỈ LẤY CHÍNH SÁCH 2026 CHO XE ĐIỆN & BROCHURE CÁC DÒNG XE)
# ==============================================================================

def crawl_vinfast_pdf_documents() -> dict[str, Any]:
    """Crawl tài liệu PDF: chỉ lấy chính sách 2026 dành cho xe điện và Brochure thông số các dòng xe."""
    print("\n[4/5] 📑 CRAWL VÀ TỔ CHỨC TÀI LIỆU PDF (CHÍNH SÁCH 2026 XE ĐIỆN & BROCHURE)...")
    PDF_LEGAL_DIR.mkdir(parents=True, exist_ok=True)
    PDF_SPECS_DIR.mkdir(parents=True, exist_ok=True)
    PDF_PROMO_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Dọn dẹp các file cũ không thuộc 2026 hoặc xe xăng / xe máy trong chinh_sach_uu_dai
    petrol_and_motorbike_keywords = [
        "xang", "lux", "fadil", "president", "chevrolet", "xmd", "xe-may",
        "xe_may", "xemay", "xedap", "xe-dap", "feliz", "evo", "klara",
        "vento", "theon", "viper", "drgnfly", "ebike", "scooter"
    ]
    for f in list(PDF_PROMO_DIR.iterdir()):
        name_lower = f.name.lower()
        is_2026 = "2026" in name_lower
        is_petrol_or_moto = any(k in name_lower for k in petrol_and_motorbike_keywords)
        is_pdf = f.name.endswith(".pdf")
        if not is_2026 or is_petrol_or_moto or not is_pdf:
            f.unlink(missing_ok=True)

    # Dọn dẹp tài liệu pháp lý xe máy nếu có
    for f in list(PDF_LEGAL_DIR.iterdir()):
        if any(k in f.name.lower() for k in ["xe_may", "xemay", "xe-may"]):
            f.unlink(missing_ok=True)

    # 2. Quét và tải chính sách năm 2026 dành cho ô tô điện từ các trang chính sách VinFast
    for page_url in VINFAST_POLICY_PAGES:
        print(f"🌐 Đang quét trang chính sách: {page_url}...")
        html = fetch_url_content(page_url, timeout=12)
        if not html:
            continue
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            preview_links = soup.find_all("a", class_="button-preview")
            print(f"   -> Đang lọc chính sách năm 2026 dành cho ô tô điện...")
            saved_count = 0
            for a in preview_links:
                pdf_url = a["href"]
                fname = pdf_url.split("/")[-1].split("?")[0]
                fname_lower = fname.lower()

                # Chỉ lấy chính sách 2026 và dành cho ô tô điện (bỏ qua xe xăng & xe máy)
                is_2026 = "2026" in fname_lower
                is_petrol_or_moto = any(k in fname_lower for k in petrol_and_motorbike_keywords)
                if is_2026 and not is_petrol_or_moto:
                    dest = PDF_PROMO_DIR / fname
                    if not dest.exists():
                        if download_binary_pdf(pdf_url, dest, timeout=15):
                            saved_count += 1
                    else:
                        saved_count += 1
            print(f"   -> Đã tải / cập nhật {saved_count} chính sách ô tô điện năm 2026.")
        except Exception as e:
            print(f"   ⚠️ Lỗi phân tích trang chính sách: {e}")

    # 3. Tải Brochure thông số kỹ thuật cho các dòng xe trong relational data
    for target in VINFAST_BROCHURE_TARGETS:
        dest = PDF_SPECS_DIR / target["filename"]
        if not dest.exists():
            print(f"📥 Đang tải Brochure: {target['title']}...")
            download_binary_pdf(target["url"], dest, timeout=20)

    # 4. Lập manifest tổng hợp toàn bộ các PDF hợp lệ
    pdf_manifest: list[dict[str, Any]] = []

    # 4.1 Pháp lý
    for f in sorted(PDF_LEGAL_DIR.glob("*.pdf")):
        if f.stat().st_size > 1000:
            pdf_manifest.append({
                "title": f.stem.replace("_", " ").title(),
                "category": "thu_tuc_phap_ly",
                "relative_path": f"data/pdf/thu_tuc_phap_ly/{f.name}",
                "size_bytes": f.stat().st_size,
                "type": "legal_document",
            })

    # 4.2 Thông số kỹ thuật
    for f in sorted(PDF_SPECS_DIR.glob("*.pdf")):
        if f.stat().st_size > 1000:
            pdf_manifest.append({
                "title": f.stem.replace("_", " ").title(),
                "category": "thong_so_ky_thuat",
                "relative_path": f"data/pdf/thong_so_ky_thuat/{f.name}",
                "size_bytes": f.stat().st_size,
                "type": "vehicle_brochure",
            })

    # 4.3 Chính sách & ưu đãi 2026
    for f in sorted(PDF_PROMO_DIR.glob("*.pdf")):
        if f.stat().st_size > 1000:
            pdf_manifest.append({
                "title": f.stem.replace("_", " ").title(),
                "category": "chinh_sach_uu_dai",
                "relative_path": f"data/pdf/chinh_sach_uu_dai/{f.name}",
                "size_bytes": f.stat().st_size,
                "type": "policy_document_2026_ev",
            })

    save_json(pdf_manifest, PDF_DIR / "pdf_manifest.json")
    save_json(pdf_manifest, BRONZE_VINFAST_DIR / "vinfast_pdf_manifest.json")

    legal_cnt = len([p for p in pdf_manifest if p["category"] == "thu_tuc_phap_ly"])
    specs_cnt = len([p for p in pdf_manifest if p["category"] == "thong_so_ky_thuat"])
    promo_cnt = len([p for p in pdf_manifest if p["category"] == "chinh_sach_uu_dai"])

    print(f"\n✅ ĐÃ TỔNG HỢP {len(pdf_manifest)} FILE PDF HỢP LỆ VÀO MANIFEST:")
    print(f"   - Pháp lý & thủ tục        : {legal_cnt} files")
    print(f"   - Thông số kỹ thuật xe     : {specs_cnt} files (Brochures chính hãng)")
    print(f"   - Chính sách xe điện 2026  : {promo_cnt} files (Chính sách 2026)")

    return {
        "status": "success",
        "total_pdfs": len(pdf_manifest),
        "legal_count": legal_cnt,
        "specs_count": specs_cnt,
        "promo_count": promo_cnt,
    }


# ==============================================================================
# 4. CRAWL BÀI VIẾT TỪ SOURCES.CSV (PHÂN GIẢI DOMAIN & CATEGORY LƯU BRONZE THÔ)
# ==============================================================================

def crawl_sources_raw(csv_path: Path | None = None) -> dict[str, Any]:
    """Crawl HTML thô từ file sources.csv đã kiểm chứng (schema: title, url, category).

    Quy tắc phân giải:
    - Bỏ qua các URL 'gia_ca_lan_banh' bên ngoài (đã có API snapshot chính hãng).
    - Với 'thong_so_ky_thuat': CHỈ chấp nhận từ domain vinfastauto.com.
    - Nếu domain chứa 'vinfastauto' hoặc 'vinfast' -> lưu vào data/bronze/vinfast/articles/
    - Nếu domain khác -> lưu vào data/bronze/web_scraping/raw_html/
    """
    print("\n[4/4] 🌐 CRAWL CÁC BÀI VIẾT TỪ SOURCES.CSV ĐÃ KIỂM CHỨNG...")
    target_csv = csv_path or SOURCES_CSV_PATH
    if not target_csv.exists():
        print(f"❌ Không tìm thấy file nguồn: {target_csv}")
        return {"status": "error", "total": 0}

    vinfast_articles_dir = BRONZE_VINFAST_DIR / "articles"
    webscraping_html_dir = BRONZE_WEBSCRAPING_DIR / "raw_html"

    vinfast_articles_dir.mkdir(parents=True, exist_ok=True)
    webscraping_html_dir.mkdir(parents=True, exist_ok=True)

    motorbike_keywords = [
        "xe-may", "xe máy", "xmd", "xe dap", "xe-dap", "xedap", "feliz",
        "evo", "klara", "vento", "theon", "viper", "drgnfly", "ebike",
        "e-scooter", "xe hai banh", "xe 2 banh", "scooter"
    ]

    # Đọc danh sách URLs từ sources.csv
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    with open(target_csv, encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or row.get("Title") or "").strip()
            url = (row.get("url") or row.get("Url") or row.get("link") or "").strip()
            category = (row.get("category") or row.get("Category") or "chua_phan_loai").strip()

            # Bỏ qua chủ đề giá lăn bánh để tránh xung đột
            if category == "gia_ca_lan_banh":
                continue

            # Bỏ qua toàn bộ xe máy
            if any(k in title.lower() or k in url.lower() for k in motorbike_keywords):
                continue

            # Thông số kỹ thuật chỉ cho phép từ VinFast
            if category == "thong_so_ky_thuat" and "vinfast" not in url.lower():
                continue

            if url and url not in seen:
                seen.add(url)
                records.append({
                    "title": title,
                    "url": url,
                    "category": category,
                })

    print(f"📄 Đọc được {len(records)} liên kết hợp lệ từ: {target_csv.name}")

    vinfast_manifest: list[dict[str, Any]] = []
    webscraping_manifest: list[dict[str, Any]] = []

    for idx, item in enumerate(records, 1):
        title = item["title"]
        url = item["url"]
        category = item["category"]

        if idx > 1:
            random_delay(0.5, 1.0)

        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.replace("www.", "").lower()
        path_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", parsed_url.path.strip("/")).strip("_")
        domain_slug = domain.replace(".", "_")
        slug = f"{domain_slug}_{path_slug}" if path_slug else domain_slug

        print(f"🌐 [{idx}/{len(records)}] [{category}] Đang tải: {title[:32]}... ({domain})")
        html = fetch_url_content(url)
        if not html or len(html) < 200:
            print(f"   ⚠️ Lỗi hoặc nội dung rỗng từ {url}")
            continue

        is_vinfast = "vinfast" in domain or "vinfastauto" in domain

        entry_metadata = {
            "title": title,
            "url": url,
            "category": category,
            "domain": domain,
            "file": f"{slug}.html",
            "bytes": len(html),
            "crawled_at": get_current_iso_timestamp(),
        }

        if is_vinfast:
            out_file = vinfast_articles_dir / f"{slug}.html"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html)
            vinfast_manifest.append(entry_metadata)
            print(f"   🚗 [VINFAST] -> {out_file.name} ({len(html):,} bytes)")
        else:
            out_file = webscraping_html_dir / f"{slug}.html"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html)
            webscraping_manifest.append(entry_metadata)
            print(f"   🌐 [WEB_SCRAPING] -> {out_file.name} ({len(html):,} bytes)")

    # Lưu manifest kèm thông tin category
    if vinfast_manifest:
        save_json(vinfast_manifest, BRONZE_VINFAST_DIR / "vinfast_sources_manifest.json")
    save_json(webscraping_manifest, BRONZE_WEBSCRAPING_DIR / "web_scraping_manifest.json")

    print(f"\n✅ Đã lưu {len(vinfast_manifest)} bài VinFast và {len(webscraping_manifest)} bài Web Scraping ngoài.")
    return {
        "vinfast_count": len(vinfast_manifest),
        "webscraping_count": len(webscraping_manifest),
    }


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def parse_arguments() -> argparse.Namespace:
    """Xử lý tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="Task 1: Thu thập toàn bộ dữ liệu thô (Raw Data) vào tầng Bronze & data/pdf"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Chạy toàn bộ crawl (Relational API + FAQ + Uudai Articles + PDFs + Sources.csv)",
    )
    parser.add_argument(
        "--vinfast",
        action="store_true",
        help="Chỉ crawl dữ liệu VinFast Auto (Relational, FAQ, Uudai Articles, PDFs)",
    )
    parser.add_argument(
        "--relational",
        action="store_true",
        help="Chỉ crawl API dữ liệu bảng giá & chi phí lăn bánh VinFast",
    )
    parser.add_argument(
        "--faq",
        action="store_true",
        help="Chỉ crawl trang FAQ VinFast",
    )
    parser.add_argument(
        "--uudai",
        action="store_true",
        help="Chỉ crawl các bài viết ưu đãi từ VinFast uu-dai",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Chỉ crawl và tổ chức danh mục tài liệu PDF (Brochures, Chính sách 2026)",
    )
    parser.add_argument(
        "--sources",
        action="store_true",
        help="Chỉ crawl các bài viết từ sources.csv",
    )
    parser.add_argument(
        "--sources-csv",
        type=str,
        default=None,
        help="Đường dẫn tùy chọn tới file sources.csv (Mặc định: data/sources.csv)",
    )
    return parser.parse_args()


def main() -> None:
    """Điểm khởi chạy Task 1."""
    args = parse_arguments()
    run_all = args.all or not any([args.vinfast, args.relational, args.faq, args.uudai, args.pdf, args.sources])

    start_time = time.time()
    print("=" * 70)
    print("🚀 DATA PIPELINE (TASK 1) - RAW DATA BRONZE & PDF LANDING")
    print(f"   File nguồn kiểm chứng: {args.sources_csv or SOURCES_CSV_PATH}")
    print(f"   Thư mục tầng Bronze:   {BRONZE_DIR}")
    print(f"   Thư mục PDF:           {PDF_DIR}")
    print("   Quy tắc đặc biệt:")
    print("   - Giá cả lăn bánh: API snapshot duy nhất từ VinFast Auto")
    print("   - Thông số kỹ thuật: Chỉ crawl từ vinfastauto.com & Brochure PDF")
    print("   - Chính sách ưu đãi: PDF 2026 xe điện & bài viết uu-dai vào Bronze")
    print("=" * 70)

    results: dict[str, str] = {}

    # 1. VinFast Relational Raw API
    if run_all or args.vinfast or args.relational:
        try:
            res_rel = crawl_vinfast_relational_raw()
            results["VinFast Relational Raw"] = f"✅ {res_rel['bytes']:,} bytes"
        except Exception as e:
            results["VinFast Relational Raw"] = f"❌ Lỗi: {e}"

    # 2. VinFast FAQ Raw HTML
    if run_all or args.vinfast or args.faq:
        try:
            res_faq = crawl_vinfast_faq_raw()
            results["VinFast FAQ Raw HTML"] = f"✅ {res_faq['bytes']:,} chars"
        except Exception as e:
            results["VinFast FAQ Raw HTML"] = f"❌ Lỗi: {e}"

    # 3. VinFast Uudai Articles Raw HTML
    if run_all or args.vinfast or args.uudai:
        try:
            res_uudai = crawl_vinfast_uudai_articles()
            results["VinFast Uu Dai Articles"] = f"✅ {len(res_uudai)} bài viết ưu đãi"
        except Exception as e:
            results["VinFast Uu Dai Articles"] = f"❌ Lỗi: {e}"

    # 4. VinFast PDF Documents (Brochures & Policies)
    if run_all or args.vinfast or args.pdf:
        try:
            res_pdf = crawl_vinfast_pdf_documents()
            results["PDF Documents"] = (
                f"✅ {res_pdf['total_pdfs']} file (Pháp lý: {res_pdf['legal_count']}, "
                f"Thông số: {res_pdf['specs_count']}, Ưu đãi 2026: {res_pdf['promo_count']})"
            )
        except Exception as e:
            results["PDF Documents"] = f"❌ Lỗi: {e}"

    # 5. Sources.csv Articles Raw HTML
    if run_all or args.sources:
        try:
            src_csv = Path(args.sources_csv) if args.sources_csv else None
            res_src = crawl_sources_raw(src_csv)
            results["Sources.csv Articles"] = (
                f"✅ {res_src['webscraping_count']} bài web_scraping, {res_src['vinfast_count']} bài vinfast"
            )
        except Exception as e:
            results["Sources.csv Articles"] = f"❌ Lỗi: {e}"

    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT TASK 1 TRONG {duration:.2f} GIÂY!")
    print("📊 BÁO CÁO KẾT QUẢ TẦNG BRONZE & PDF:")
    for k, v in results.items():
        print(f"   - {k:<25}: {v}")
    print(f"\n📂 Dữ liệu thô đã được lưu tại: {BRONZE_DIR} và {PDF_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
