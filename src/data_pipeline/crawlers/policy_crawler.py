"""src/data_pipeline/crawlers/policy_crawler.py
Thu thập và bóc tách toàn bộ chính sách bảo hành, pin, cứu hộ, bảo dưỡng
và điều khoản pháp lý từ VinFast Auto:
- Chính sách bảo hành ô tô & xe máy điện
- Dịch vụ pin & trạm sạc
- Dịch vụ cứu hộ 24/7, bảo dưỡng và sửa chữa
- Hợp đồng mua bán & chính sách bán hàng
- Điều khoản pháp lý và chính sách quyền riêng tư
Dữ liệu được lưu trữ dạng JSON tại data/landing/policies/ và data/landing/legal/
"""

from __future__ import annotations

import re
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    LEGAL_DIR,
    POLICIES_DIR,
    build_rag_metadata,
    clean_html,
    extract_related_models,
    fetch_html,
    random_delay,
    save_json,
)

BASE_URL = "https://vinfastauto.com"

# Danh sách cấu hình các trang chính sách & pháp lý cần crawl
POLICY_CONFIGS = [
    {
        "id": "warranty-car",
        "slug": "chinh-sach-bao-hanh-oto",
        "url": f"{BASE_URL}/vn_vi/chinh-sach-bao-hanh-oto",
        "type": "policies",
        "category": "Bảo hành",
        "applies_to": "Ô tô điện VinFast (VF 3, VF 5, VF 6, VF 7, VF 8, VF 9...)",
        "file_name": "vinfast_car_warranty_policy.json",
    },
    {
        "id": "warranty-bike",
        "slug": "chinh-sach-bao-hanh-xe-may",
        "url": f"{BASE_URL}/vn_vi/chinh-sach-bao-hanh-xe-may",
        "type": "policies",
        "category": "Bảo hành",
        "applies_to": "Xe máy điện VinFast (Evo, Feliz, Klara, Vento, Theon...)",
        "file_name": "vinfast_bike_warranty_policy.json",
    },
    {
        "id": "battery-car",
        "slug": "dich-vu-pin-oto-dien",
        "url": f"{BASE_URL}/vn_vi/dich-vu-pin-oto-dien",
        "type": "policies",
        "category": "Pin & Trạm sạc",
        "applies_to": "Ô tô điện VinFast",
        "file_name": "vinfast_car_battery_service.json",
    },
    {
        "id": "battery-bike",
        "slug": "dich-vu-pin-xe-may-dien",
        "url": f"{BASE_URL}/vn_vi/dich-vu-pin-xe-may-dien",
        "type": "policies",
        "category": "Pin & Trạm sạc",
        "applies_to": "Xe máy điện VinFast",
        "file_name": "vinfast_bike_battery_service.json",
    },
    {
        "id": "rescue-service",
        "slug": "thong-tin-cuu-ho-oto",
        "url": f"{BASE_URL}/vn_vi/thong-tin-cuu-ho-oto",
        "type": "policies",
        "category": "Hậu mãi & Cứu hộ",
        "applies_to": "Ô tô VinFast toàn quốc",
        "file_name": "vinfast_rescue_service.json",
    },
    {
        "id": "maintenance-car",
        "slug": "dich-vu-bao-duong-oto",
        "url": f"{BASE_URL}/vn_vi/dich-vu-bao-duong-oto",
        "type": "policies",
        "category": "Bảo dưỡng & Sửa chữa",
        "applies_to": "Ô tô điện VinFast",
        "file_name": "vinfast_maintenance_service.json",
    },
    {
        "id": "repair-car",
        "slug": "dich-vu-sua-chua-oto",
        "url": f"{BASE_URL}/vn_vi/dich-vu-sua-chua-oto",
        "type": "policies",
        "category": "Bảo dưỡng & Sửa chữa",
        "applies_to": "Ô tô điện VinFast",
        "file_name": "vinfast_repair_service.json",
    },
    {
        "id": "sales-contract",
        "slug": "hop-dong-va-chinh-sach",
        "url": f"{BASE_URL}/vn_vi/hop-dong-va-chinh-sach",
        "type": "policies",
        "category": "Hợp đồng & Bán hàng",
        "applies_to": "Khách hàng mua xe VinFast",
        "file_name": "vinfast_sales_contracts_and_policies.json",
    },
    {
        "id": "charging-stations",
        "slug": "pin-va-tram-sac",
        "url": f"{BASE_URL}/vn_vi/pin-va-tram-sac",
        "type": "policies",
        "category": "Pin & Trạm sạc",
        "applies_to": "Hệ sinh thái sạc VinFast & V-GREEN",
        "file_name": "vinfast_charging_stations_policy.json",
    },
    {
        "id": "legal-terms",
        "slug": "dieu-khoan-phap-ly",
        "url": f"{BASE_URL}/vn_vi/dieu-khoan-phap-ly",
        "type": "legal",
        "category": "Pháp lý",
        "applies_to": "Toàn bộ người dùng & khách hàng",
        "file_name": "vinfast_legal_terms.json",
    },
    {
        "id": "privacy-policy",
        "slug": "privacy-policy",
        "url": f"{BASE_URL}/vn_vi/privacy-policy",
        "type": "legal",
        "category": "Pháp lý",
        "applies_to": "Toàn bộ người dùng & khách hàng",
        "file_name": "vinfast_privacy_policy.json",
    },
]


# Alias để giữ tính tương thích nội bộ
_extract_related_models = extract_related_models


def _extract_sections(html: str) -> list[dict[str, str]]:
    """Phân tách nội dung trang thành các mục đề mục h2/h3 và nội dung tương ứng."""
    sections = []
    # Tìm các đoạn văn bản chính trong main hoặc article
    main_match = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.I)
    body_html = main_match.group(1) if main_match else html

    # Tách theo thẻ h2 hoặc h3
    parts = re.split(r"(<h[23][^>]*>.*?</h[23]>)", body_html, flags=re.DOTALL | re.I)
    current_title = "Tổng quan"
    for part in parts:
        h_match = re.match(r"<h[23][^>]*>(.*?)</h[23]>", part, re.DOTALL | re.I)
        if h_match:
            current_title = clean_html(h_match.group(1))
        else:
            text = clean_html(part)
            if len(text) > 40:
                sections.append({
                    "section_title": current_title,
                    "content": text,
                })
    return sections


def crawl_policy_page(cfg: dict[str, str]) -> dict[str, Any] | None:
    """Tải và phân tích cú pháp một trang chính sách."""
    url = cfg["url"]
    html = fetch_html(url)
    if not html:
        print(f"⚠️  Không tải được: {url}")
        return None

    # Trích xuất tiêu đề chính
    title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
    title = clean_html(title_m.group(1)) if title_m else cfg["id"]
    if "|" in title:
        title = title.split("|")[0].strip()

    h1 = clean_html(h1_m.group(1)) if h1_m else title

    # Phân tích sections và văn bản đầy đủ
    sections = _extract_sections(html)
    full_text = clean_html(html)

    # Lọc bỏ nội dung navbar & footer chung khỏi full_text nếu quá dài
    main_match = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.I)
    if main_match:
        main_text = clean_html(main_match.group(1))
    else:
        main_text = full_text

    related = _extract_related_models(main_text)
    doc_type = "legal" if cfg["type"] == "legal" else "policy"
    parent_category = "Pháp lý" if cfg["type"] == "legal" else "Chính sách"

    metadata = build_rag_metadata(
        doc_id=f"doc_{doc_type}_{cfg['id']}",
        doc_type=doc_type,
        title=h1 or title,
        category=parent_category,
        subcategory=cfg["category"],
        source_url=url,
        applies_to=cfg["applies_to"],
        related_models=related,
        raw_content=main_text,
    )

    return {
        "metadata": metadata,
        "sections": sections,
        "raw_content": main_text,
    }


def run_policy_crawl() -> dict[str, Any]:
    """Điều phối crawl toàn bộ các trang chính sách và pháp lý."""
    print("=" * 65)
    print("📜 BẮT ĐẦU CRAWL CHÍNH SÁCH & ĐIỀU KHOẢN PHÁP LÝ VINFAST AUTO")
    print(f"   Thư mục chính sách: {POLICIES_DIR}")
    print(f"   Thư mục pháp lý: {LEGAL_DIR}")
    print("=" * 65)

    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    LEGAL_DIR.mkdir(parents=True, exist_ok=True)

    policies_list: list[dict[str, Any]] = []
    legal_list: list[dict[str, Any]] = []
    created_files: list[str] = []

    for idx, cfg in enumerate(POLICY_CONFIGS):
        if idx > 0:
            random_delay(1.0, 2.0)

        print(f"🌐 Đang crawl: {cfg['slug']} ...")
        res = crawl_policy_page(cfg)
        if not res:
            continue

        target_dir = LEGAL_DIR if cfg["type"] == "legal" else POLICIES_DIR
        out_file = target_dir / cfg["file_name"]
        save_json(res, out_file)
        created_files.append(out_file.name)
        print(f"   ✅ Đã lưu: {cfg['type']}/{out_file.name} ({res['metadata']['char_count']:,} ký tự)")

        if cfg["type"] == "legal":
            legal_list.append(res)
        else:
            policies_list.append(res)


    # Lưu thêm file tổng hợp cho policies và legal
    all_policies_file = POLICIES_DIR / "vinfast_policies_all.json"
    save_json(policies_list, all_policies_file)
    created_files.append(all_policies_file.name)

    all_legal_file = LEGAL_DIR / "vinfast_legal_all.json"
    save_json(legal_list, all_legal_file)
    created_files.append(all_legal_file.name)

    print(f"\n🎉 Hoàn thành crawl: {len(policies_list)} chính sách, {len(legal_list)} văn bản pháp lý.")
    return {
        "status": "success",
        "policies_count": len(policies_list),
        "legal_count": len(legal_list),
        "created_files": created_files,
    }


if __name__ == "__main__":
    run_policy_crawl()
