"""src/data_pipeline/crawlers/faq_crawler.py
Thu thập và bóc tách toàn bộ Câu hỏi thường gặp (FAQ) từ VinFast Auto:
  https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap
Lọc và phân loại theo các dòng xe ô tô / xe máy điện và chính sách chung.
Dữ liệu được xuất dạng JSON có cấu trúc tại data/landing/faqs/
"""

from __future__ import annotations

import re
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    CRAWLED_BIKE_MODELS,
    CRAWLED_CAR_MODELS,
    FAQS_DIR,
    build_rag_metadata,
    clean_html,
    fetch_html,
    get_current_iso_timestamp,
    random_delay,
    save_json,
)

FAQ_PAGE_URL = "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap"


def _extract_related_models(text: str) -> list[str]:
    """Tìm kiếm các dòng xe ô tô / xe máy được nhắc tới trong câu hỏi và câu trả lời."""
    text_upper = text.upper()
    found: set[str] = set()

    for car in CRAWLED_CAR_MODELS:
        # Ví dụ tìm VF 3, VF3, VF 8, VF8, Limo Green,...
        pattern = r"\b" + re.escape(car.upper()) + r"\b"
        compressed = car.upper().replace(" ", "")
        compressed_pattern = r"\b" + re.escape(compressed) + r"\b"
        if re.search(pattern, text_upper) or re.search(compressed_pattern, text_upper):
            found.add(car)

    for bike in CRAWLED_BIKE_MODELS:
        base_name = bike.split()[0].upper()
        if base_name in text_upper:
            found.add(bike)

    return sorted(found)


def parse_faqs_from_html(html: str) -> list[dict[str, Any]]:
    """Phân tích cú pháp HTML trang FAQ và trích xuất danh mục, câu hỏi & câu trả lời."""
    # Tách theo nhóm danh mục chính (<h2 class="cat-name">)
    cat_splits = re.split(r'<h2 class="cat-name">(.*?)</h2>', html)
    if len(cat_splits) <= 1:
        return []

    results: list[dict[str, Any]] = []
    item_idx = 1
    timestamp = get_current_iso_timestamp()

    # Legacy ICE models cần loại bỏ theo yêu cầu:
    # "chỉ các dòng, loại, option xe đã crawl được hoặc các thông tin chung"
    legacy_models = ["FADIL", "LUX A", "LUX SA", "PRESIDENTIAL", "PRESIDENT"]

    for i in range(1, len(cat_splits), 2):
        category = clean_html(cat_splits[i]).strip()
        cat_content = cat_splits[i + 1]

        # Tách theo nhóm danh mục con (<h3 class="child-name">)
        child_splits = re.split(r'<h3 class="child-name">(.*?)</h3>', cat_content)
        if len(child_splits) <= 1:
            child_splits = ["", "Chung", cat_content]

        for j in range(1, len(child_splits), 2):
            subcategory = clean_html(child_splits[j]).strip()
            child_content = child_splits[j + 1]

            # Trích xuất từng câu hỏi trong post
            posts = re.findall(
                r'<div[^>]*class="post"[^>]*>.*?<h2 class="post-title">(.*?)</h2>'
                r'.*?<div class="post-content"[^>]*>(.*?)</div>\s*</div>',
                child_content,
                re.DOTALL,
            )

            for raw_q, raw_a in posts:
                question = clean_html(raw_q)
                answer = clean_html(raw_a)

                if not question or not answer:
                    continue

                full_text = f"{question} {answer}"
                full_text_upper = full_text.upper()

                # Nếu câu hỏi chỉ nói về xe xăng cũ mà không liên quan đến xe điện đã crawl -> bỏ qua
                is_legacy = any(m in full_text_upper for m in legacy_models)
                related_ev = _extract_related_models(full_text)

                if is_legacy and not related_ev:
                    continue

                raw_content = f"Câu hỏi: {question}\n\nTrả lời: {answer}"
                doc_id = f"faq-{item_idx:04d}"

                metadata = build_rag_metadata(
                    doc_id=doc_id,
                    doc_type="faq",
                    title=question,
                    category=category,
                    subcategory=subcategory,
                    source_url=FAQ_PAGE_URL,
                    applies_to="Khách hàng sử dụng ô tô & xe máy điện VinFast",
                    related_models=related_ev,
                    raw_content=raw_content,
                )

                results.append({
                    "metadata": metadata,
                    "question": question,
                    "answer": answer,
                    "raw_content": raw_content,
                })
                item_idx += 1


    return results


def run_faq_crawl() -> dict[str, Any]:
    """Crawl, lọc và lưu trữ toàn bộ FAQ VinFast ra thư mục data/landing/faqs/."""
    print("=" * 65)
    print("❓ BẮT ĐẦU CRAWL CÂU HỎI THƯỜNG GẶP (FAQ) VINFAST AUTO")
    print(f"   Trang nguồn: {FAQ_PAGE_URL}")
    print(f"   Thư mục đích: {FAQS_DIR}")
    print("=" * 65)

    FAQS_DIR.mkdir(parents=True, exist_ok=True)
    html = fetch_html(FAQ_PAGE_URL)
    if not html:
        print("❌ Không thể tải trang FAQ!")
        return {"status": "error", "count": 0}

    faqs = parse_faqs_from_html(html)
    print(f"✅ Đã trích xuất & làm sạch thành công: {len(faqs)} câu hỏi FAQ phù hợp.")

    # 1. Lưu toàn bộ danh sách FAQ
    all_file = FAQS_DIR / "vinfast_faqs.json"
    save_json(faqs, all_file)
    print(f"📁 Đã xuất: {all_file.name} ({len(faqs)} câu hỏi)")

    # 2. Gom nhóm theo Category và Subcategory
    by_cat: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for item in faqs:
        c = item["metadata"]["category"]
        sc = item["metadata"]["subcategory"]
        by_cat.setdefault(c, {}).setdefault(sc, []).append(item)


    grouped_file = FAQS_DIR / "vinfast_faqs_by_category.json"
    save_json(by_cat, grouped_file)
    print(f"📁 Đã xuất: {grouped_file.name} (Phân cấp theo danh mục)")

    # 3. File thống kê tóm tắt
    summary = {
        "total_faqs": len(faqs),
        "source_url": FAQ_PAGE_URL,
        "crawled_at": get_current_iso_timestamp(),
        "categories_breakdown": {
            cat: {subcat: len(items) for subcat, items in subcats.items()}
            for cat, subcats in by_cat.items()
        },
    }
    summary_file = FAQS_DIR / "vinfast_faqs_summary.json"
    save_json(summary, summary_file)
    print(f"📁 Đã xuất: {summary_file.name} (Báo cáo tổng hợp)")

    return {
        "status": "success",
        "count": len(faqs),
        "files": [all_file.name, grouped_file.name, summary_file.name],
    }


if __name__ == "__main__":
    run_faq_crawl()
