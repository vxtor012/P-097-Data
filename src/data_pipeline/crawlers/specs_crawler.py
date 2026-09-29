"""src/data_pipeline/crawlers/specs_crawler.py
Thu thập thông số kỹ thuật (specs), tính năng công nghệ và thông tin chi tiết
của các dòng xe ô tô điện VinFast đã crawl được từ bảng giá:
  - VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 8 The All New, VF 9, VF MPV 7, VF Wild
  - Các dòng xe dịch vụ thế hệ mới: Limo Green, Herio Green, Minio Green, EC Van
Dữ liệu được lưu trữ dạng JSON tại data/landing/specs/
"""

from __future__ import annotations

import re
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    SPECS_DIR,
    build_rag_metadata,
    clean_html,
    fetch_html,
    get_current_iso_timestamp,
    random_delay,
    save_json,
)

BASE_URL = "https://vinfastauto.com"

CAR_PRODUCT_PAGES = [
    {
        "model_name": "VF 3",
        "slug": "vf-3",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-dien-vf3",
        "segment": "Mini SUV",
        "seats": 4,
    },
    {
        "model_name": "VF 5",
        "slug": "vf-5",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-dien-vf5",
        "segment": "A-SUV",
        "seats": 5,
    },
    {
        "model_name": "VF 6",
        "slug": "vf-6",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-dien-vf6",
        "segment": "B-SUV",
        "seats": 5,
    },
    {
        "model_name": "VF 7",
        "slug": "vf-7",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-dien-vf7",
        "segment": "C-SUV",
        "seats": 5,
    },
    {
        "model_name": "VF 8",
        "slug": "vf-8",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf8",
        "segment": "D-SUV",
        "seats": 5,
    },
    {
        "model_name": "VF 8 The All New",
        "slug": "vf-8-the-all-new",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf8-the-all-new-2026",
        "segment": "D-SUV (Thế hệ mới 2026)",
        "seats": 5,
    },
    {
        "model_name": "VF 9",
        "slug": "vf-9",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf9",
        "segment": "E-SUV Full-size",
        "seats": 7,
    },
    {
        "model_name": "VF 2",
        "slug": "vf-2",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf2",
        "segment": "Micro City Car",
        "seats": 4,
    },
    {
        "model_name": "VF MPV 7",
        "slug": "vf-mpv-7",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf-mpv7",
        "segment": "MPV 7 chỗ",
        "seats": 7,
    },
    {
        "model_name": "VF Wild",
        "slug": "vf-wild",
        "url": f"{BASE_URL}/vn_vi/dat-coc-xe-vf-wild",
        "segment": "Bán tải điện (Electric Pickup)",
        "seats": 5,
    },
    {
        "model_name": "Limo Green",
        "slug": "limo-green",
        "url": f"{BASE_URL}/vn_vi/limo-green",
        "segment": "Xe dịch vụ cỡ lớn 7 chỗ",
        "seats": 7,
    },
    {
        "model_name": "Herio Green",
        "slug": "herio-green",
        "url": f"{BASE_URL}/vn_vi/herio-green",
        "segment": "Xe đô thị dịch vụ",
        "seats": 5,
    },
    {
        "model_name": "Minio Green",
        "slug": "minio-green",
        "url": f"{BASE_URL}/vn_vi/minio-green",
        "segment": "Xe dịch vụ mini",
        "seats": 4,
    },
    {
        "model_name": "EC Van",
        "slug": "ec-van",
        "url": f"{BASE_URL}/vn_vi/vinfast-ecvan",
        "segment": "Xe van chở hàng chạy điện",
        "seats": 2,
    },
]


def extract_specs_from_html(html: str) -> dict[str, str]:
    """Trích xuất bảng thông số kỹ thuật (specs) từ HTML trang chi tiết xe."""
    specs_dict: dict[str, str] = {}

    # Tìm tất cả khối spec
    spec_blocks = re.findall(
        r'<div[^>]*class="[^"]*spec[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.I
    )

    for b in spec_blocks:
        lines = [clean_html(x) for x in re.findall(r"<[^>]+>([^<]+)<", b)]
        clean_lines = [l.strip() for l in lines if l.strip()]

        # Bỏ qua các hàng tiêu đề nhóm tabs
        if "Kích thước" in clean_lines and "Pin & Sạc" in clean_lines:
            continue

        if len(clean_lines) >= 2:
            key = clean_lines[0]
            val = " ".join(clean_lines[1:])
            # Chuẩn hóa key
            key = re.sub(r"\s+", " ", key)
            if key not in specs_dict:
                specs_dict[key] = val

    # Nếu regex trên bắt ít, tìm thêm trong thẻ table hoặc dl/dt/dd
    tables = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.I)
    for row in tables:
        cells = [clean_html(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.I)]
        cells = [c for c in cells if c]
        if len(cells) == 2:
            k, v = cells[0], cells[1]
            if len(k) < 60 and k not in specs_dict:
                specs_dict[k] = v

    return specs_dict


def crawl_car_model_specs(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Crawl thông số kỹ thuật của một dòng xe ô tô VinFast."""
    url = cfg["url"]
    html = fetch_html(url)
    if not html:
        print(f"⚠️  Không tải được: {url}")
        return None

    title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    title = clean_html(title_m.group(1)) if title_m else cfg["model_name"]
    if "|" in title:
        title = title.split("|")[0].strip()

    specs = extract_specs_from_html(html)

    # Trích xuất tổng quan giới thiệu
    meta_desc = re.search(
        r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.I
    )
    description = clean_html(meta_desc.group(1)) if meta_desc else ""

    # Trích xuất các tính năng nổi bật (h3/h4/li trong section features)
    features = []
    feature_matches = re.findall(
        r'<div[^>]*class="[^"]*feature[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.I
    )
    for feat in feature_matches[:10]:
        t = clean_html(feat)
        if 20 < len(t) < 300 and t not in features:
            features.append(t)

    spec_lines = [f"- {k}: {v}" for k, v in specs.items()]
    feat_lines = [f"- {f}" for f in features]
    raw_content = (
        f"Dòng xe: {cfg['model_name']} ({cfg['segment']})\n"
        f"Mô tả: {description}\n\n"
        f"Thông số kỹ thuật:\n" + ("\n".join(spec_lines) if spec_lines else "Đang cập nhật") + "\n\n"
        f"Tính năng nổi bật:\n" + ("\n".join(feat_lines) if feat_lines else "Đang cập nhật")
    ).strip()

    metadata = build_rag_metadata(
        doc_id=f"doc_specs_{cfg['slug']}",
        doc_type="vehicle_spec",
        title=f"Thông số kỹ thuật và tính năng xe VinFast {cfg['model_name']}",
        category="Thông số kỹ thuật",
        subcategory=cfg["segment"],
        source_url=url,
        applies_to=f"Dòng xe {cfg['model_name']}",
        related_models=[cfg["model_name"]],
        raw_content=raw_content,
        extra_fields={
            "segment": cfg["segment"],
            "seats": cfg["seats"],
            "specifications_count": len(specs),
        },
    )

    return {
        "metadata": metadata,
        "model_name": cfg["model_name"],
        "slug": cfg["slug"],
        "segment": cfg["segment"],
        "seats": cfg["seats"],
        "description": description,
        "specifications": specs,
        "key_features": features,
        "raw_content": raw_content,
    }


def run_specs_crawl() -> dict[str, Any]:
    """Điều phối crawl toàn bộ thông số kỹ thuật của các dòng xe đã có trong bảng giá."""
    print("=" * 65)
    print("🚗 BẮT ĐẦU CRAWL THÔNG SỐ KỸ THUẬT (SPECS) CÁC DÒNG XE VINFAST")
    print(f"   Số lượng dòng xe: {len(CAR_PRODUCT_PAGES)}")
    print(f"   Thư mục đích: {SPECS_DIR}")
    print("=" * 65)

    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    all_specs: list[dict[str, Any]] = []

    for idx, cfg in enumerate(CAR_PRODUCT_PAGES):
        if idx > 0:
            random_delay(1.0, 2.0)

        print(f"🌐 Đang crawl specs: {cfg['model_name']} ({cfg['slug']}) ...")
        res = crawl_car_model_specs(cfg)
        if not res:
            continue

        # Lưu file từng dòng xe riêng lẻ
        out_file = SPECS_DIR / f"{cfg['slug']}_specs.json"
        save_json(res, out_file)
        all_specs.append(res)
        print(f"   ✅ Đã lưu: {out_file.name} ({len(res['specifications'])} thông số)")


    # Lưu tập tin tổng hợp toàn bộ thông số các dòng xe
    combined_file = SPECS_DIR / "vinfast_car_specifications.json"
    save_json(all_specs, combined_file)
    print(f"\n📁 Đã xuất tập tin tổng hợp: {combined_file.name} ({len(all_specs)} dòng xe)")

    summary = {
        "total_models": len(all_specs),
        "crawled_at": get_current_iso_timestamp(),
        "models": [
            {
                "model_name": s["model_name"],
                "segment": s["segment"],
                "specs_count": len(s["specifications"]),
            }
            for s in all_specs

        ],
    }
    summary_file = SPECS_DIR / "specs_summary.json"
    save_json(summary, summary_file)
    print(f"📁 Đã xuất: {summary_file.name} (Báo cáo tổng kết specs)")

    return {
        "status": "success",
        "models_count": len(all_specs),
        "combined_file": combined_file.name,
    }


if __name__ == "__main__":
    run_specs_crawl()
