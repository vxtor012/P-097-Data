"""src/data_pipeline/task1_vinfast_auto_crawl_data.py
Pipeline thu thập toàn diện dữ liệu VinFast Auto (Task 1):
1. Dữ liệu quan hệ dạng bảng (Relational Tabular Data):
   - Bảng giá các phiên bản xe ô tô & xe máy điện
   - Tùy chọn màu sắc & phụ phí màu
   - 63 tỉnh/thành & biểu phí ra biển, thuế trước bạ
   - Chính sách ưu đãi, khuyến mãi
   - Dự toán chi phí lăn bánh hoàn chỉnh
   -> Lưu trữ: CSV tại data/landing/relational/

2. Dữ liệu phi cấu trúc & bán cấu trúc (Unstructured & Semi-structured Data):
   - Câu hỏi thường gặp (FAQ) phân cấp danh mục: data/landing/faqs/
   - Chính sách bảo hành, pin, bảo dưỡng, cứu hộ: data/landing/policies/
   - Điều khoản pháp lý & quyền riêng tư: data/landing/legal/
   - Tin tức & thông cáo sản phẩm mới: data/landing/news/
   - Thông số kỹ thuật (Specs) chi tiết các dòng xe: data/landing/specs/
   -> Lưu trữ: JSON có cấu trúc

Kiến trúc module hóa:
Mỗi tác vụ được chia thành các module crawler chuyên biệt (< 600 dòng):
- crawlers/crawler_utils.py
- crawlers/relational_crawler.py
- crawlers/faq_crawler.py
- crawlers/policy_crawler.py
- crawlers/news_crawler.py
- crawlers/specs_crawler.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Cấu hình đường dẫn root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tự động cấu hình mã hóa UTF-8 cho stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import các crawler chuyên biệt
from src.data_pipeline.crawlers.external_sources_crawler import run_external_sources_crawl
from src.data_pipeline.crawlers.faq_crawler import run_faq_crawl
from src.data_pipeline.crawlers.news_crawler import run_news_crawl
from src.data_pipeline.crawlers.policy_crawler import run_policy_crawl
from src.data_pipeline.crawlers.relational_crawler import (
    export_bike_pricing,
    export_car_color_options,
    export_car_editions_pricing,
    export_car_rolling_cost_summary,
    export_promotions,
    export_provinces_fees,
    fetch_rolling_data,
    run_relational_crawl,
)
from src.data_pipeline.crawlers.specs_crawler import run_specs_crawl
from src.data_pipeline.crawlers.vgreen_crawler import run_vgreen_crawl

# Re-export các hàm và biến để tương thích ngược 100% với mã nguồn cũ
__all__ = [
    "fetch_rolling_data",
    "export_car_editions_pricing",
    "export_car_color_options",
    "export_provinces_fees",
    "export_promotions",
    "export_bike_pricing",
    "export_car_rolling_cost_summary",
    "run_relational_crawl",
    "run_faq_crawl",
    "run_policy_crawl",
    "run_news_crawl",
    "run_specs_crawl",
    "run_vgreen_crawl",
    "run_external_sources_crawl",
    "main",
]


def parse_arguments() -> argparse.Namespace:
    """Xử lý tham số dòng lệnh tùy chọn."""
    parser = argparse.ArgumentParser(
        description="Pipeline thu thập toàn diện dữ liệu VinFast Auto, V-GREEN & Nguồn tham chiếu (Task 1)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Chạy toàn bộ pipeline (Relational CSVs + FAQs + Policies + Legal + News + Specs + V-Green + Sources CSV)",
    )
    parser.add_argument(
        "--relational",
        action="store_true",
        help="Chỉ crawl dữ liệu bảng giá quan hệ và dự toán lăn bánh (CSV - chỉ dành cho VinFast Auto)",
    )
    parser.add_argument(
        "--faqs",
        action="store_true",
        help="Chỉ crawl Câu hỏi thường gặp FAQ (JSON)",
    )
    parser.add_argument(
        "--policies",
        action="store_true",
        help="Chỉ crawl Chính sách bảo hành, pin, hậu mãi & Pháp lý (JSON)",
    )
    parser.add_argument(
        "--news",
        action="store_true",
        help="Chỉ crawl Tin tức & Thông cáo sản phẩm (JSON)",
    )
    parser.add_argument(
        "--specs",
        action="store_true",
        help="Chỉ crawl Thông số kỹ thuật chi tiết các dòng xe (JSON)",
    )
    parser.add_argument(
        "--vgreen",
        action="store_true",
        help="Chỉ crawl dữ liệu đa cấp V-GREEN (vgreen.net - chỉ lưu vào policies và news)",
    )
    parser.add_argument(
        "--sources",
        action="store_true",
        help="Chỉ crawl dữ liệu từ file source.csv / sources.csv (chỉ lưu vào policies và news)",
    )
    return parser.parse_args()


def main() -> None:
    """Điểm khởi chạy chính của Pipeline."""
    args = parse_arguments()

    # Mặc định nếu không chỉ định cờ nào thì chạy toàn bộ
    run_all = args.all or not any([
        args.relational,
        args.faqs,
        args.policies,
        args.news,
        args.specs,
        args.vgreen,
        args.sources,
    ])

    start_time = time.time()
    print("=" * 70)
    print("🌟 VINFAST AUTO & ECOSYSTEM COMPREHENSIVE DATA PIPELINE (TASK 1)")
    print("   Trang chủ VinFast: https://vinfastauto.com/vn_vi")
    print("   Trang dự toán:     https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh")
    print("   Trang V-Green:     https://vgreen.net/vi")
    print("   Nguồn tham chiếu:  source.csv / sources.csv")
    print("   Lưu ý kiến trúc:   Bảng relational CHỈ lưu trữ dữ liệu VinFast Auto.")
    print("                      Dữ liệu V-Green & ngoài lề chỉ lưu vào policies/news.")
    print("=" * 70)

    results_summary: dict[str, str] = {}

    # 1. Relational Data (CSV) - DUY NHẤT DÀNH CHO VINFAST AUTO
    if run_all or args.relational:
        print("\n[1/7] 📊 CRAWL DỮ LIỆU GIÁ BÁN & DỰ TOÁN LĂN BÁNH VINFAST AUTO (RELATIONAL CSV)...")
        try:
            rel_res = run_relational_crawl()
            total_rows = sum(rel_res.values())
            results_summary["Relational CSVs (VinFast)"] = f"✅ {total_rows} bản ghi (6 files CSV)"
        except Exception as e:
            results_summary["Relational CSVs (VinFast)"] = f"❌ Lỗi: {e}"
            print(f"❌ Lỗi crawl relational: {e}")

    # 2. FAQs (JSON)
    if run_all or args.faqs:
        print("\n[2/7] ❓ CRAWL CÂU HỎI THƯỜNG GẶP (FAQS JSON)...")
        try:
            faq_res = run_faq_crawl()
            results_summary["FAQs JSON"] = f"✅ {faq_res.get('count', 0)} câu hỏi"
        except Exception as e:
            results_summary["FAQs JSON"] = f"❌ Lỗi: {e}"
            print(f"❌ Lỗi crawl FAQs: {e}")

    # 3. Policies & Legal (JSON)
    if run_all or args.policies:
        print("\n[3/7] 📜 CRAWL CHÍNH SÁCH BẢO HÀNH, PIN, HẬU MÃI & PHÁP LÝ VINFAST (JSON)...")
        try:
            pol_res = run_policy_crawl()
            total_pols = pol_res.get("policies_count", 0) + pol_res.get("legal_count", 0)
            results_summary["Policies & Legal JSON"] = f"✅ {total_pols} tài liệu chính sách/pháp lý"
        except Exception as e:
            results_summary["Policies & Legal JSON"] = f"❌ Lỗi: {e}"
            print(f"❌ Lỗi crawl Policies: {e}")

    # 4. News (JSON)
    if run_all or args.news:
        print("\n[4/7] 📰 CRAWL TIN TỨC & THÔNG CÁO SẢN PHẨM MỚI VINFAST (JSON)...")
        try:
            news_res = run_news_crawl()
            results_summary["News JSON"] = f"✅ {news_res.get('count', 0)} bài viết"
        except Exception as e:
            results_summary["News JSON"] = f"❌ Lỗi: {e}"
            print(f"❌ Lỗi crawl News: {e}")

    # 5. Vehicle Specifications (JSON)
    if run_all or args.specs:
        print("\n[5/7] 🚗 CRAWL THÔNG SỐ KỸ THUẬT CHI TIẾT CÁC DÒNG XE VINFAST (SPECS JSON)...")
        try:
            specs_res = run_specs_crawl()
            results_summary["Specs JSON"] = f"✅ {specs_res.get('models_count', 0)} dòng xe"
        except Exception as e:
            results_summary["Specs JSON"] = f"❌ Lỗi: {e}"
            print(f"❌ Lỗi crawl Specs: {e}")

    # 6. V-Green Multi-level Crawler (JSON -> policies / news)
    if run_all or args.vgreen or args.policies or args.news:
        if run_all or args.vgreen:
            print("\n[6/7] ⚡ CRAWL ĐA CẤP HỆ SINH THÁI TRẠM SẠC & ĐỔI PIN V-GREEN (vgreen.net)...")
            try:
                vg_res = run_vgreen_crawl()
                p_cnt = vg_res.get("total_policies_collected", 0)
                n_cnt = vg_res.get("total_news_collected", 0)
                results_summary["V-GREEN (Policies & News)"] = f"✅ {p_cnt} chính sách, {n_cnt} tin tức"
            except Exception as e:
                results_summary["V-GREEN (Policies & News)"] = f"❌ Lỗi: {e}"
                print(f"❌ Lỗi crawl V-GREEN: {e}")

    # 7. External Sources Crawler (JSON -> policies / news)
    if run_all or args.sources or args.policies or args.news:
        if run_all or args.sources:
            print("\n[7/7] 🌐 CRAWL BÀI VIẾT THAM CHIẾU TỪ FILE NGUỒN (source.csv / sources.csv)...")
            try:
                ext_res = run_external_sources_crawl()
                p_cnt = ext_res.get("total_policies_collected", 0)
                n_cnt = ext_res.get("total_news_collected", 0)
                results_summary["External Sources (CSV)"] = f"✅ {p_cnt} chính sách, {n_cnt} tin tức"
            except Exception as e:
                results_summary["External Sources (CSV)"] = f"❌ Lỗi: {e}"
                print(f"❌ Lỗi crawl External Sources: {e}")

    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT PIPELINE THU THẬP DỮ LIỆU TRONG {duration:.2f} GIÂY!")
    print("📊 BÁO CÁO KẾT QUẢ:")
    for component, status in results_summary.items():
        print(f"   - {component:<28}: {status}")
    print("=" * 70)


if __name__ == "__main__":
    main()
