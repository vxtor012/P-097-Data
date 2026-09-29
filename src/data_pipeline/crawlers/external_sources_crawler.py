"""src/data_pipeline/crawlers/external_sources_crawler.py
Thu thập dữ liệu các bài viết, chính sách đơn lẻ từ file source.csv / sources.csv:
- Các nguồn sưu tầm bên ngoài (Techcombank, Bảo Việt, XeHay...).
- Phân loại dữ liệu nghiêm ngặt:
    + Chính sách bảo hiểm, lãi suất, thủ tục trả góp ngân hàng -> data/landing/policies/
    + Bài viết đánh giá, tin tức thị trường xe -> data/landing/news/
- LƯU Ý BẢO MẬT DỮ LIỆU: Tuyệt đối KHÔNG ghi vào thư mục relational (dành riêng cho VinFast Auto).
"""

from __future__ import annotations

import csv
import re
import urllib.parse
from pathlib import Path
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    NEWS_DIR,
    POLICIES_DIR,
    PROJECT_ROOT,
    build_rag_metadata,
    clean_html,
    extract_related_models,
    fetch_html,
    get_current_iso_timestamp,
    random_delay,
    save_json,
)

# Các vị trí tìm kiếm file nguồn CSV (hỗ trợ cả source.csv và sources.csv)
CANDIDATE_CSV_PATHS = [
    PROJECT_ROOT / "src" / "data_pipeline" / "sources.csv",
    PROJECT_ROOT / "src" / "data_pipeline" / "source.csv",
    PROJECT_ROOT / "sources.csv",
    PROJECT_ROOT / "source.csv",
]


# Alias để giữ tính tương thích nội bộ
_extract_related_models = extract_related_models


def read_all_sources_csv(specific_path: Path | None = None) -> tuple[list[dict[str, str]], list[Path]]:
    """Đọc và chuẩn hóa danh sách các liên kết từ các file CSV hợp lệ, tự động khử trùng lặp."""
    targets = [specific_path] if specific_path else CANDIDATE_CSV_PATHS
    records: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    found_paths: list[Path] = []

    for path in targets:
        if path and path.exists() and path.is_file():
            found_paths.append(path)
            with open(path, encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = (row.get("title") or row.get("Title") or "").strip()
                    url = (row.get("url") or row.get("Url") or row.get("link") or "").strip()
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        records.append({"title": title, "url": url})
    return records, found_paths


def parse_external_article(title_hint: str, url: str) -> dict[str, Any] | None:
    """Crawl và trích xuất nội dung văn bản từ một liên kết đơn lẻ trong source.csv."""
    html = fetch_html(url)
    if not html:
        return None

    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc.replace("www.", "")

    # Trích xuất tiêu đề bài viết
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
    title = clean_html(h1_m.group(1)) if h1_m else ""
    if not title:
        t_m = re.search(r"<title>(.*?)</title>", html, re.I)
        title = clean_html(t_m.group(1)) if t_m else title_hint
    if "|" in title:
        title = title.split("|")[0].strip()

    # Ngày xuất bản
    date_m = re.search(r"(\d{2}/\d{2}/\d{4})", html)
    if not date_m:
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", html)
    pub_date = date_m.group(1) if date_m else ""

    # Trích xuất thân bài viết
    body_m = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.I)
    raw_text = ""
    if body_m:
        raw_text = clean_html(body_m.group(1), strip_nav=True)
    if len(raw_text) < 200:
        main_m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.I)
        if main_m:
            raw_text = clean_html(main_m.group(1), strip_nav=True)
    if len(raw_text) < 200:
        raw_text = clean_html(html, strip_nav=True)

    if len(raw_text) < 100:
        return None

    # Tạo slug an toàn cho tên file
    path_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", parsed_url.path.strip("/")).strip("_")
    domain_slug = domain.replace(".", "_")
    slug = f"{domain_slug}_{path_slug}" if path_slug else domain_slug

    # Phân loại: Chính sách vs Tin tức
    # - Tài chính, lãi suất, ngân hàng, bảo hiểm -> Chính sách (Policy)
    # - Tổng hợp tin tức, đánh giá xe (XeHay) -> Tin tức (News)
    url_lower = url.lower()
    title_lower = f"{title_hint} {title}".lower()

    if any(k in url_lower or k in title_lower for k in ["bao-hiem", "bảo hiểm", "lai-suat", "lãi suất", "vay", "tra-gop", "trả góp", "thu-tuc", "thủ tục"]):
        is_policy = True
        doc_type = "policy"
        if "baoviet" in domain:
            category = "Chính sách Bảo hiểm"
            subcategory = "Bảo hiểm phương tiện ô tô - xe máy Bảo Việt"
            applies_to = "Chủ sở hữu ô tô và xe máy tham gia giao thông"
        else:
            category = "Chính sách Tài chính & Ngân hàng"
            subcategory = "Vay mua ô tô & xe máy trả góp"
            applies_to = "Khách hàng có nhu cầu vay mua xe trả góp"
    else:
        is_policy = False
        doc_type = "news"
        category = "Tin tức Thị trường & Đánh giá xe"
        subcategory = "Tin tức chuyên ngành ô tô xe máy"
        applies_to = "Khách hàng quan tâm xu hướng và thông tin thị trường xe"

    related_models = _extract_related_models(f"{title} {raw_text}")

    metadata = build_rag_metadata(
        doc_id=f"doc_ext_{doc_type}_{slug}",
        doc_type=doc_type,
        title=title,
        domain=domain,
        source_url=url,
        category=category,
        subcategory=subcategory,
        applies_to=applies_to,
        related_models=related_models,
        raw_content=raw_text,
        extra_fields={
            "published_date": pub_date,
            "source_type": "external_collected_source",
        },
    )

    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    summary = paragraphs[0] if paragraphs else raw_text[:250]
    if len(summary) > 300:
        summary = summary[:297] + "..."

    return {
        "metadata": metadata,
        "is_policy": is_policy,
        "slug": slug,
        "summary": summary,
        "published_date": pub_date,
        "raw_content": raw_text,
    }


def run_external_sources_crawl(csv_path: Path | None = None) -> dict[str, Any]:
    """Crawl toàn bộ các liên kết được chỉ định trong source.csv / sources.csv."""
    print("=" * 65)
    print("🌐 BẮT ĐẦU CRAWL BÀI VIẾT TỪ FILE NGUỒN (source.csv / sources.csv)")
    print("=" * 65)

    items, found_paths = read_all_sources_csv(csv_path)
    if not items:
        msg = "❌ Không tìm thấy hoặc file source.csv / sources.csv rỗng trong các thư mục dự án!"
        print(msg)
        return {"status": "error", "message": msg, "policies_count": 0, "news_count": 0}

    paths_str = ", ".join(str(p.name) for p in found_paths)
    print(f"📄 Đang đọc dữ liệu từ: {paths_str}")
    print(f"   Tìm thấy {len(items)} liên kết cần thu thập.")

    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    ext_policies_dir = POLICIES_DIR / "external"
    ext_policies_dir.mkdir(parents=True, exist_ok=True)
    ext_news_dir = NEWS_DIR / "articles"
    ext_news_dir.mkdir(parents=True, exist_ok=True)

    crawled_policies: list[dict[str, Any]] = []
    crawled_news: list[dict[str, Any]] = []

    for idx, item in enumerate(items):
        title_hint = item["title"]
        url = item["url"]

        if idx > 0:
            random_delay(1.0, 1.8)

        print(f"🌐 [{idx+1}/{len(items)}] Đang crawl: {title_hint[:40]}... ({url})")
        doc = parse_external_article(title_hint, url)
        if not doc:
            print(f"   ⚠️ Không lấy được nội dung từ {url}")
            continue

        slug = doc["slug"]
        if doc["is_policy"]:
            out_file = ext_policies_dir / f"ext_policy_{slug}.json"
            save_json(doc, out_file)
            crawled_policies.append(doc)
            print(f"   📜 [POLICY] -> {out_file.name} ({doc['metadata']['char_count']:,} ký tự)")
        else:
            out_file = ext_news_dir / f"ext_news_{slug}.json"
            save_json(doc, out_file)
            crawled_news.append(doc)
            print(f"   📰 [NEWS]   -> {out_file.name} ({doc['metadata']['char_count']:,} ký tự)")

    # Lưu tập tin tổng hợp cho Policies
    ext_policies_file = POLICIES_DIR / "external_sources_policies.json"
    save_json(crawled_policies, ext_policies_file)
    print(f"\n📁 Đã xuất tổng hợp chính sách bên ngoài: {ext_policies_file.name} ({len(crawled_policies)} tài liệu)")

    # Lưu tập tin tổng hợp cho News
    ext_news_file = NEWS_DIR / "external_sources_news.json"
    save_json(crawled_news, ext_news_file)
    print(f"📁 Đã xuất tổng hợp tin tức bên ngoài: {ext_news_file.name} ({len(crawled_news)} bài viết)")

    report = {
        "status": "success",
        "csv_file": str(csv_path),
        "crawled_at": get_current_iso_timestamp(),
        "total_sources_read": len(items),
        "total_policies_collected": len(crawled_policies),
        "total_news_collected": len(crawled_news),
        "policies_file": ext_policies_file.name,
        "news_file": ext_news_file.name,
    }
    summary_file = POLICIES_DIR / "external_sources_summary.json"
    save_json(report, summary_file)
    print(f"📁 Đã lưu báo cáo: {summary_file.name}")

    return report


if __name__ == "__main__":
    run_external_sources_crawl()
