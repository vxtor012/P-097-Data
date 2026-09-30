"""src/data_pipeline/task1_crawl_data.py
Task 1: Thu thập dữ liệu thô (Raw Data) lưu trữ vào tầng Bronze theo Medallion Architecture.

1. Nguồn dữ liệu:
   - VinFast Auto API: Dữ liệu quan hệ thô (bảng giá & chi phí lăn bánh).
   - VinFast Auto Web: HTML thô trang Câu hỏi thường gặp (FAQ).
   - sources.csv: Crawl HTML thô từ danh sách URLs đã kiểm chứng (có cấu trúc title, url, category).
     + Nếu domain là vinfastauto / vinfast -> lưu vào data/bronze/vinfast/articles/
     + Nếu domain ngoài (techcombank, baoviet, xehay...) -> lưu vào data/bronze/web_scraping/raw_html/

2. Cấu trúc tầng Bronze:
   data/
   └── bronze/
       ├── vinfast/
       │   ├── relational/
       │   │   └── vinfast_rolling_raw_snapshot.json
       │   ├── faq/
       │   │   └── vinfast_faq_raw.html
       │   ├── articles/          (nếu có URL từ nguồn vinfastauto trong sources.csv)
       │   └── vinfast_sources_manifest.json
       └── web_scraping/
           ├── raw_html/          (HTML thô các bài viết từ domain ngoài)
           └── web_scraping_manifest.json
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

# Đường dẫn tầng Bronze
BRONZE_DIR = DATA_DIR / "bronze"
BRONZE_VINFAST_DIR = BRONZE_DIR / "vinfast"
BRONZE_WEBSCRAPING_DIR = BRONZE_DIR / "web_scraping"

# Endpoint & URL nguồn
VINFAST_ROLLING_API = (
    "https://shop.vinfastauto.com/on/demandware.store/Sites-app_vinfast_vn-Site/vi_VN/"
    "RollingUpCost-GetInfoRolling"
)
VINFAST_ROLLING_PAGE = "https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh"
VINFAST_FAQ_PAGE = "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap"

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


def random_delay(min_s: float = 0.8, max_s: float = 1.6) -> None:
    """Tạm dừng ngẫu nhiên tránh rate-limit."""
    time.sleep(round(random.uniform(min_s, max_s), 2))


def fetch_url_content(url: str, timeout: int = 20) -> str:
    """Tải nội dung từ URL (ưu tiên urllib, tự động fallback sang curl.exe)."""
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
        # Fallback sang curl.exe gốc
        cmd = [
            "curl.exe", "-sL", "--http1.1", "--compressed",
            "-m", str(timeout + 5), url,
            "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
            "-H", "Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        ]
        res = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout + 10
        )
        return res.stdout or ""


# ==============================================================================
# 1. CRAWL DỮ LIỆU QUAN HỆ VINFAST (RAW JSON)
# ==============================================================================

def crawl_vinfast_relational_raw() -> dict[str, Any]:
    """Crawl snapshot JSON thô từ API RollingUpCost của VinFast lưu vào Bronze."""
    print("\n[1/3] 📊 CRAWL DỮ LIỆU QUAN HỆ THÔ TỪ VINFAST API...")
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

    # Handshake nhận cookie phiên
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
# 2. CRAWL CÂU HỎI THƯỜNG GẶP VINFAST (RAW HTML)
# ==============================================================================

def crawl_vinfast_faq_raw() -> dict[str, Any]:
    """Crawl trang FAQ chính thức của VinFast lưu HTML thô vào Bronze."""
    print("\n[2/3] ❓ CRAWL FAQ THÔ TỪ TRANG CHỦ VINFAST...")
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
# 3. CRAWL BÀI VIẾT TỪ SOURCES.CSV (PHÂN GIẢI DOMAIN & CATEGORY LƯU BRONZE THÔ)
# ==============================================================================

def crawl_sources_raw(csv_path: Path | None = None) -> dict[str, Any]:
    """Crawl HTML thô từ file sources.csv đã kiểm chứng (schema: title, url, category).

    Quy tắc phân giải:
    - Đọc các trường: title, url, category từ sources.csv
    - Nếu domain chứa 'vinfastauto' hoặc 'vinfast' -> lưu vào data/bronze/vinfast/articles/
    - Nếu domain khác -> lưu vào data/bronze/web_scraping/raw_html/
    """
    print("\n[3/3] 🌐 CRAWL CÁC BÀI VIẾT TỪ SOURCES.CSV ĐÃ KIỂM CHỨNG...")
    target_csv = csv_path or SOURCES_CSV_PATH
    if not target_csv.exists():
        print(f"❌ Không tìm thấy file nguồn: {target_csv}")
        return {"status": "error", "total": 0}

    vinfast_articles_dir = BRONZE_VINFAST_DIR / "articles"
    webscraping_html_dir = BRONZE_WEBSCRAPING_DIR / "raw_html"

    vinfast_articles_dir.mkdir(parents=True, exist_ok=True)
    webscraping_html_dir.mkdir(parents=True, exist_ok=True)

    # Đọc danh sách URLs từ sources.csv
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    with open(target_csv, encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or row.get("Title") or "").strip()
            url = (row.get("url") or row.get("Url") or row.get("link") or "").strip()
            category = (row.get("category") or row.get("Category") or "chua_phan_loai").strip()

            if url and url not in seen:
                seen.add(url)
                records.append({
                    "title": title,
                    "url": url,
                    "category": category,
                })

    print(f"📄 Đọc được {len(records)} liên kết kiểm chứng từ: {target_csv.name}")

    vinfast_manifest: list[dict[str, Any]] = []
    webscraping_manifest: list[dict[str, Any]] = []

    for idx, item in enumerate(records, 1):
        title = item["title"]
        url = item["url"]
        category = item["category"]

        if idx > 1:
            random_delay(0.7, 1.4)

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
        description="Task 1: Thu thập toàn bộ dữ liệu thô (Raw Data) từ sources.csv vào tầng Bronze"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Chạy toàn bộ crawl (VinFast Relational + VinFast FAQ + Sources.csv)",
    )
    parser.add_argument(
        "--vinfast",
        action="store_true",
        help="Chỉ crawl dữ liệu VinFast Auto (Relational & FAQ)",
    )
    parser.add_argument(
        "--relational",
        action="store_true",
        help="Chỉ crawl API dữ liệu bảng giá VinFast",
    )
    parser.add_argument(
        "--faq",
        action="store_true",
        help="Chỉ crawl trang FAQ VinFast",
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
        help="Đường dẫn tùy chọn tới file sources.csv (Mặc định: src/data_pipeline/sources.csv)",
    )
    return parser.parse_args()


def main() -> None:
    """Điểm khởi chạy Task 1."""
    args = parse_arguments()
    run_all = args.all or not any([args.vinfast, args.relational, args.faq, args.sources])

    start_time = time.time()
    print("=" * 70)
    print("🚀 DATA PIPELINE (TASK 1) - RAW DATA BRONZE LANDING")
    print(f"   File nguồn kiểm chứng: {args.sources_csv or SOURCES_CSV_PATH}")
    print(f"   Thư mục đích:          {BRONZE_DIR}")
    print("   Phân vùng:             vinfast/ & web_scraping/ (phân giải theo domain)")
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

    # 3. Sources.csv Articles Raw HTML
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
    print("📊 BÁO CÁO KẾT QUẢ TẦNG BRONZE:")
    for k, v in results.items():
        print(f"   - {k:<25}: {v}")
    print(f"\n📂 Dữ liệu thô đã được lưu tại: {BRONZE_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
