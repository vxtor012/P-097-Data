"""src/data_pipeline/crawlers/news_crawler.py
Thu thập và bóc tách các bài viết tin tức, thông cáo báo chí, chính sách mới
từ chuyên mục Tin tức của VinFast Auto:
  - Ô tô điện: https://vinfastauto.com/vn_vi/tin-tuc/o-to-dien
  - Doanh nghiệp & Công ty: https://vinfastauto.com/vn_vi/tin-tuc/cong-ty
Lọc và gắn thẻ theo các dòng xe đã crawl và thông tin chung toàn công ty.
Dữ liệu được lưu dạng JSON tại data/landing/news/
"""

from __future__ import annotations

import re
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    CRAWLED_BIKE_MODELS,
    CRAWLED_CAR_MODELS,
    NEWS_DIR,
    build_rag_metadata,
    clean_html,
    fetch_html,
    get_current_iso_timestamp,
    random_delay,
    save_json,
)

BASE_URL = "https://vinfastauto.com"
NEWS_FEED_URLS = [
    {
        "category": "Ô tô điện",
        "url": f"{BASE_URL}/vn_vi/tin-tuc/o-to-dien",
    },
    {
        "category": "Doanh nghiệp & Công ty",
        "url": f"{BASE_URL}/vn_vi/tin-tuc/cong-ty",
    },
]


def _extract_related_models(text: str) -> list[str]:
    """Phát hiện các dòng xe được nhắc tới trong bài viết."""
    text_upper = text.upper()
    found: set[str] = set()

    for car in CRAWLED_CAR_MODELS:
        pattern = r"\b" + re.escape(car.upper()) + r"\b"
        compressed = r"\b" + re.escape(car.upper().replace(" ", "")) + r"\b"
        if re.search(pattern, text_upper) or re.search(compressed, text_upper):
            found.add(car)

    for bike in CRAWLED_BIKE_MODELS:
        base_name = bike.split()[0].upper()
        if base_name in text_upper:
            found.add(bike)

    return sorted(found)


def extract_article_links(feed_html: str) -> list[str]:
    """Tìm tất cả đường dẫn bài viết tin tức từ trang danh sách."""
    rows = re.findall(
        r'<div[^>]*class="[^"]*views-row[^"]*"[^>]*>(.*?)</div>\s*'
        r'(?=<div[^>]*class="[^"]*views-row|<div[^>]*class="[^"]*view-footer|</div>\s*</div>)',
        feed_html,
        re.DOTALL,
    )
    article_links: list[str] = []
    seen: set[str] = set()

    for r in rows:
        links = re.findall(r'href="(/vn_vi/[^"]+)"', r)
        for link in links:
            slug = link.replace("/vn_vi/", "").strip("/")
            # Bỏ qua các trang điều hướng hệ thống
            if slug in [
                "tin-tuc",
                "o-to-dien",
                "cong-ty",
                "xe-may-dien",
                "cau-hoi-thuong-gap",
            ]:
                continue
            if link not in seen:
                seen.add(link)
                article_links.append(link)

    return article_links


def crawl_single_article(link: str, default_category: str) -> dict[str, Any] | None:
    """Crawl và bóc tách nội dung chi tiết của một bài viết tin tức."""
    url = f"{BASE_URL}{link}" if link.startswith("/") else link
    html = fetch_html(url)
    if not html:
        return None

    # Tiêu đề
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
    if not title_m:
        title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    title = clean_html(title_m.group(1)) if title_m else ""
    if "|" in title:
        title = title.split("|")[0].strip()

    # Ngày xuất bản
    date_m = re.search(r"(\d{2}/\d{2}/\d{4})", html)
    pub_date = date_m.group(1) if date_m else ""

    # Thân bài viết
    body_m = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.I)
    if not body_m:
        body_m = re.search(
            r'<div[^>]*class="[^"]*field--name-body[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.I,
        )
    if not body_m:
        body_m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.I)

    body_text = clean_html(body_m.group(1)) if body_m else clean_html(html)

    # Nếu bài viết quá ngắn hoặc là trang chuyển hướng -> bỏ qua
    if len(body_text) < 150:
        return None

    slug = link.replace("/vn_vi/", "").strip("/")
    related_models = _extract_related_models(f"{title} {body_text}")

    # Tạo tóm tắt bài viết (2 đoạn đầu tiên hoặc 250 ký tự đầu)
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    summary = paragraphs[0] if paragraphs else body_text[:250]
    if len(summary) > 300:
        summary = summary[:297] + "..."

    metadata = build_rag_metadata(
        doc_id=f"doc_news_{slug}",
        doc_type="news",
        title=title,
        category="Tin tức",
        subcategory=default_category,
        source_url=url,
        applies_to="Khách hàng quan tâm ô tô điện & hệ sinh thái VinFast",
        related_models=related_models,
        raw_content=body_text,
        extra_fields={
            "published_date": pub_date,
        },
    )

    return {
        "metadata": metadata,
        "summary": summary,
        "published_date": pub_date,
        "raw_content": body_text,
    }


def run_news_crawl() -> dict[str, Any]:
    """Điều phối thu thập tin tức VinFast liên quan đến xe điện và chính sách."""
    print("=" * 65)
    print("📰 BẮT ĐẦU CRAWL TIN TỨC & THÔNG CÁO BÁO CHÍ VINFAST AUTO")
    print(f"   Thư mục đích: {NEWS_DIR}")
    print("=" * 65)

    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    articles_dir = NEWS_DIR / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    all_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for feed in NEWS_FEED_URLS:
        print(f"🌐 Đang lấy danh sách tin tức: {feed['category']} ...")
        feed_html = fetch_html(feed["url"])
        if not feed_html:
            continue

        links = extract_article_links(feed_html)
        print(f"   Tìm thấy {len(links)} liên kết bài viết.")

        for link in links:
            if link in seen_urls:
                continue
            seen_urls.add(link)

            # Delay ngẫu nhiên giữa các bài viết để chống chặn bot
            random_delay(1.0, 2.0)
            article = crawl_single_article(link, feed["category"])
            if not article:
                continue

            slug = article["metadata"]["doc_id"].replace("doc_news_", "")
            out_file = articles_dir / f"{slug}.json"
            save_json(article, out_file)

            all_articles.append(article)
            models_tag = (
                ", ".join(article["metadata"]["related_models"])
                if article["metadata"]["related_models"]
                else "Thông tin chung"
            )
            print(
                f"   ✅ [{article['published_date'] or 'N/A'}] "
                f"{article['metadata']['title'][:50]}... ({models_tag})"
            )

    # Lưu tập tin tổng hợp tất cả bài viết
    all_news_file = NEWS_DIR / "vinfast_news_articles.json"
    save_json(all_articles, all_news_file)
    print(f"\n📁 Đã xuất tập tin tổng hợp: {all_news_file.name} ({len(all_articles)} bài viết)")

    # Lưu báo cáo tổng quan
    summary = {
        "total_articles": len(all_articles),
        "crawled_at": get_current_iso_timestamp(),
        "categories": {
            feed["category"]: len([
                a for a in all_articles if a["metadata"]["subcategory"] == feed["category"]
            ])
            for feed in NEWS_FEED_URLS
        },
        "model_mentions_count": {
            car: len([a for a in all_articles if car in a["metadata"]["related_models"]])
            for car in CRAWLED_CAR_MODELS
            if any(car in a["metadata"]["related_models"] for a in all_articles)
        },
    }

    summary_file = NEWS_DIR / "news_summary.json"
    save_json(summary, summary_file)
    print(f"📁 Đã xuất: {summary_file.name} (Báo cáo tổng quan)")

    return {
        "status": "success",
        "count": len(all_articles),
        "articles_file": all_news_file.name,
    }


if __name__ == "__main__":
    run_news_crawl()
