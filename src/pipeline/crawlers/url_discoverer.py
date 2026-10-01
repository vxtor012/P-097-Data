"""
URL Discovery and Source Cataloging for Vietnamese Automotive Pre-RAG Pipeline.
Discovers, validates, and categorizes seed URLs and dynamic news/policy feeds.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MOTORBIKE_KEYWORDS = [
    "xe-may", "xe máy", "xmd", "xe dap", "xe-dap", "xedap", "feliz",
    "evo", "klara", "vento", "theon", "viper", "drgnfly", "ebike",
    "e-scooter", "xe hai banh", "xe 2 banh", "scooter"
]

VALID_CATEGORIES = {
    "thong_so_ky_thuat",
    "chinh_sach_uu_dai",
    "he_thong_tram_sac",
    "tai_chinh_tra_gop",
    "thu_tuc_phap_ly",
    "trai_nghiem_danh_gia",
    "hau_mai_bao_duong",
}

SEED_ENTRIES: List[Dict[str, str]] = [
    # 1. THONG_SO_KY_THUAT (Official VinFast EV only)
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 3",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 5 Plus",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf5-plus",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 6",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf6",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 7",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf7",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 8",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-vf8",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật VinFast VF 8 The All New",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-vf8-the-all-new-2026",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 9",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-vf9",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe tải điện VinFast EC Van",
        "url": "https://vinfastauto.com/vn_vi/vinfast-ecvan",
        "category": "thong_so_ky_thuat",
    },
    # 2. CHINH_SACH_UU_DAI
    {
        "title": "Tổng hợp chương trình ưu đãi và khuyến mại VinFast",
        "url": "https://vinfastauto.com/vn_vi/uu-dai",
        "category": "chinh_sach_uu_dai",
    },
    {
        "title": "Chính sách ưu đãi chương trình Mãnh liệt Tinh thần Việt Nam",
        "url": "https://vinfastauto.com/vn_vi/manh-liet-tinh-than-viet-nam",
        "category": "chinh_sach_uu_dai",
    },
    {
        "title": "Đặc quyền hội viên VinClub khi mua và sử dụng xe VinFast",
        "url": "https://vinfastauto.com/vn_vi/dac-quyen-vinclub-vinfast",
        "category": "chinh_sach_uu_dai",
    },
    {
        "title": "Chương trình ưu đãi Mua 1 tặng 1 xe ô tô điện VinFast VF 8 và VF 9",
        "url": "https://vinfastauto.com/vn_vi/chuong-trinh-uu-dai-mua-1-tang-1-danh-cho-khach-hang-mua-xe-o-to-dien-vinfast-vf-8-va-vf-9",
        "category": "chinh_sach_uu_dai",
    },
    {
        "title": "Chương trình ưu đãi tặng bảo hiểm 2 năm khi mua xe VinFast VF 3, VF 5",
        "url": "https://vinfastauto.com/vn_vi/chuong-trinh-uu-dai-tang-bao-hiem-2-nam-khi-mua-xe-o-to-vinfast-vf-3-vf-5-va-herio-green",
        "category": "chinh_sach_uu_dai",
    },
    # 3. HE_THONG_TRAM_SAC
    {
        "title": "Mạng lưới trạm sạc ô tô điện toàn quốc VinFast & V-GREEN",
        "url": "https://vinfastauto.com/vn_vi/pin-va-tram-sac",
        "category": "he_thong_tram_sac",
    },
    {
        "title": "Bảng giá sạc pin và dịch vụ tại trạm sạc V-GREEN",
        "url": "https://vgreen.net/vi/san-pham-dich-vu",
        "category": "he_thong_tram_sac",
    },
    {
        "title": "Câu hỏi thường gặp về trạm sạc & quy chuẩn sạc xe điện V-GREEN",
        "url": "https://vgreen.net/vi/cau-hoi-thuong-gap",
        "category": "he_thong_tram_sac",
    },
    {
        "title": "Hướng dẫn sử dụng các trụ sạc siêu nhanh DC 150kW - 250kW",
        "url": "https://vgreen.net/vi/huong-dan-sac-xe-nhanh",
        "category": "he_thong_tram_sac",
    },
    {
        "title": "Chính sách và giải pháp lắp đặt bộ sạc tại nhà cho ô tô điện",
        "url": "https://vinfastauto.com/vn_vi/giai-phap-sac-tai-nha",
        "category": "he_thong_tram_sac",
    },
    # 4. TAI_CHINH_TRA_GOP
    {
        "title": "Lãi suất vay mua ô tô các ngân hàng cập nhật mới nhất",
        "url": "https://techcombank.com/thong-tin/blog/lai-suat-vay-mua-o-to",
        "category": "tai_chinh_tra_gop",
    },
    {
        "title": "Lời khuyên lựa chọn ngân hàng khi vay mua xe trả góp tối ưu",
        "url": "https://techcombank.com/thong-tin/blog/vay-mua-xe-tra-gop-ngan-hang-nao-tot-nhat",
        "category": "tai_chinh_tra_gop",
    },
    {
        "title": "Nên vay ngân hàng mua xe trả góp hay thanh toán một lần",
        "url": "https://techcombank.com/thong-tin/blog/nen-mua-xe-tra-gop-hay-tra-thang",
        "category": "tai_chinh_tra_gop",
    },
    {
        "title": "Điều kiện, hồ sơ, thủ tục mua ô tô trả góp 2026",
        "url": "https://techcombank.com/thong-tin/blog/thu-tuc-mua-xe-tra-gop",
        "category": "tai_chinh_tra_gop",
    },
    {
        "title": "Gói vay ưu đãi lãi suất cố định mua ô tô điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/chinh-sach-vay-mua-xe-tra-gop",
        "category": "tai_chinh_tra_gop",
    },
    # 5. THU_TUC_PHAP_LY (Bảo hiểm & Hợp đồng chính hãng - Văn bản luật đã có PDF chuẩn riêng)
    {
        "title": "Bảo hiểm xe ô tô Bảo Việt: Quyền lợi & Biểu phí thân vỏ",
        "url": "https://baoviet.com/bao-hiem-xe-bao-viet.htm",
        "category": "thu_tuc_phap_ly",
    },
    {
        "title": "Bảo hiểm trách nhiệm dân sự bắt buộc cho xe ô tô Bảo Việt",
        "url": "https://baoviet.com/bao-hiem-trach-nhiem-dan-su-xe-o-to-bao-viet.htm",
        "category": "thu_tuc_phap_ly",
    },
    {
        "title": "Hợp đồng và điều khoản pháp lý bán hàng VinFast Auto",
        "url": "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach",
        "category": "thu_tuc_phap_ly",
    },
    # 6. TRAI_NGHIEM_DANH_GIA
    {
        "title": "[ĐÁNH GIÁ XE] VinFast VF 8 thế hệ mới: Nhẹ hơn, êm hơn và thực dụng sau vô-lăng",
        "url": "https://xehay.vn/danh-gia-xe-vinfast-vf-8-the-he-moi-nhe-hon-em-hon-va-thuc-dung-hon-sau-vo-lang.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Những thay đổi mang tính thực tế và kinh tế trên VinFast VF 8 thế hệ mới",
        "url": "https://xehay.vn/nhung-thay-doi-mang-tinh-thuc-te-va-kinh-te-tren-vinfast-vf-8-the-he-moi.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "[ĐÁNH GIÁ XE] Người dùng đánh giá VinFast VF 9: Đẹp, cao cấp, lái hay và rất phù hợp cho gia đình",
        "url": "https://xehay.vn/danh-gia-xe-nguoi-dung-danh-gia-vinfast-vf-9-dep-cao-cap-lai-hay-va-rat-phu-hop-cho-gia-dinh.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chinh phục Tà Xùa, chủ xe ví trải nghiệm VinFast VF 7 như xe vài tỷ",
        "url": "https://xehay.vn/chinh-phuc-ta-xua-chu-xe-vi-trai-nghiem-vinfast-vf-7-nhu-xe-vai-ty.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "[ĐÁNH GIÁ NHANH] VinFast VF 6: Sắc bén, tiện nghi, giá tốt",
        "url": "https://xehay.vn/danh-gia-nhanh-vinfast-vf-6-sac-ben-tien-nghi-gia-tot.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chi tiết VinFast VF 3 Plus tại đại lý: Thêm camera lùi, gương chỉnh điện",
        "url": "https://xehay.vn/chi-tiet-vinfast-vf-3-plus-tai-dai-ly-them-camera-lui-guong-chinh-dien-gia-315-trieu-dong.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 5 chứng minh vị thế SUV “đáng tiền nhất” cho người mua xe lần đầu",
        "url": "https://xehay.vn/vinfast-vf-5-chung-minh-vi-the-suv-dang-tien-nhat-cho-nguoi-mua-xe-lan-dau.html",
        "category": "trai_nghiem_danh_gia",
    },
    # 7. HAU_MAI_BAO_DUONG
    {
        "title": "Chính sách bảo hành 10 năm hoặc 200.000 km cho ô tô điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/chinh-sach-bao-hanh-o-to",
        "category": "hau_mai_bao_duong",
    },
    {
        "title": "Dịch vụ cứu hộ 24/7 và cứu hộ pin lưu động (Mobile Charging)",
        "url": "https://vinfastauto.com/vn_vi/thong-tin-cuu-ho-oto",
        "category": "hau_mai_bao_duong",
    },
    {
        "title": "Lịch bảo dưỡng định kỳ và bảng giá phụ tùng ô tô điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/dich-vu-bao-duong-oto",
        "category": "hau_mai_bao_duong",
    },
    {
        "title": "Dịch vụ sửa chữa chính hãng và xưởng dịch vụ lưu động (Mobile Service)",
        "url": "https://vinfastauto.com/vn_vi/dich-vu-sua-chua-oto",
        "category": "hau_mai_bao_duong",
    },
    {
        "title": "Chính sách bảo hành pin và cam kết dung lượng pin trên 70%",
        "url": "https://vinfastauto.com/vn_vi/dich-vu-pin-oto-dien",
        "category": "hau_mai_bao_duong",
    },
]


class UrlDiscoverer:
    """Discovers and validates URLs for Vietnamese electric vehicle purchasing knowledge."""

    def __init__(self, seeds: Optional[List[Dict[str, str]]] = None):
        self.seeds = seeds or SEED_ENTRIES

    @staticmethod
    def is_valid_entry(title: str, url: str, category: str) -> bool:
        """Enforces quality gates on discovered URLs."""
        if not url or not title:
            return False

        t_lower = title.lower()
        u_lower = url.lower()

        # Reject all motorbikes, scooters, and ebikes
        if any(k in t_lower or k in u_lower for k in MOTORBIKE_KEYWORDS):
            return False

        # Pricing must only be queried from VinFast API snapshot, reject web price crawling
        if category == "gia_ca_lan_banh":
            return False

        # Specifications must strictly come from official VinFast domain
        if category == "thong_so_ky_thuat" and "vinfast" not in u_lower:
            return False

        # Reject external legal portals & statutory crawlers (authentic PDFs are manually managed in dataset/pdf/thu_tuc_phap_ly)
        if "luatvietnam.vn" in u_lower or "thuvienphapluat.vn" in u_lower:
            return False
        if any(k in u_lower for k in ["/luat-", "nghi-dinh", "thong-tu", "van-ban-luat"]):
            return False

        return True

    def discover_urls(self, include_dynamic: bool = False, max_pages: int = 2) -> List[Dict[str, str]]:
        """Compiles validated URLs from seeds and optional dynamic feeds."""
        seen_urls: Set[str] = set()
        results: List[Dict[str, str]] = []

        # 1. Ingest seed entries
        for seed in self.seeds:
            url = seed.get("url", "").strip()
            title = seed.get("title", "").strip()
            category = seed.get("category", "trai_nghiem_danh_gia").strip()

            if url not in seen_urls and self.is_valid_entry(title, url, category):
                seen_urls.add(url)
                results.append({"title": title, "url": url, "category": category})

        # 2. Dynamic discovery from feeds if enabled
        if include_dynamic:
            dynamic_entries = self._crawl_dynamic_promos(max_pages=max_pages)
            for entry in dynamic_entries:
                url = entry.get("url", "").strip()
                title = entry.get("title", "").strip()
                category = entry.get("category", "chinh_sach_uu_dai").strip()
                if url not in seen_urls and self.is_valid_entry(title, url, category):
                    seen_urls.add(url)
                    results.append({"title": title, "url": url, "category": category})

        logger.info("Discovered %d valid consultation URLs", len(results))
        return results

    def _crawl_dynamic_promos(self, max_pages: int = 2) -> List[Dict[str, str]]:
        """Scans VinFast promotion listing pages dynamically."""
        entries: List[Dict[str, str]] = []
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return entries

        for page in range(0, max_pages):
            page_url = f"https://vinfastauto.com/vn_vi/uu-dai?page={page}" if page > 0 else "https://vinfastauto.com/vn_vi/uu-dai"
            try:
                cmd = ["curl.exe", "-4", "-sL", "-m", "10", page_url, "-H", f"User-Agent: {DEFAULT_USER_AGENT}"]
                res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=12)
                html = res.stdout if res.returncode == 0 else ""
                if not html or len(html) < 200:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    title = a.get_text(strip=True)
                    if any(k in href.lower() or k in title.lower() for k in MOTORBIKE_KEYWORDS):
                        continue
                    if any(k in href for k in ["uu-dai", "khuyen-mai", "chuong-trinh", "vi-tuong-lai-xanh"]):
                        full_url = f"https://vinfastauto.com{href}" if href.startswith("/") else href
                        entries.append({
                            "title": title or href.split("/")[-1].replace("-", " ").title(),
                            "url": full_url,
                            "category": "chinh_sach_uu_dai",
                        })
            except Exception as e:
                logger.warning("Dynamic feed scan warning: %s", e)

        return entries

    def export_to_csv(self, filepath: Path, include_dynamic: bool = False) -> int:
        """Exports discovered valid URLs to CSV."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        urls = self.discover_urls(include_dynamic=include_dynamic)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "url", "category"])
            writer.writeheader()
            for r in urls:
                writer.writerow(r)

        logger.info("Saved %d URLs to %s", len(urls), filepath)
        return len(urls)
