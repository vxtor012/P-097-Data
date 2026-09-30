"""src/data_pipeline/urls_crawler.py
Script quét và thu thập danh sách toàn diện các URLs phục vụ các nhóm chủ đề cốt lõi.

QUY TẮC PHẠM VI NGUỒN DỮ LIỆU:
1. `gia_ca_lan_banh`: ĐÃ CRAWL TRỰC TIẾP TỪ API VINFAST thành dữ liệu quan hệ (relational snapshot).
   -> Bỏ qua thu thập URL bên ngoài về giá/lăn bánh để tránh xung đột thông tin.
2. `thong_so_ky_thuat`: CHỈ ĐƯỢC PHÉP CRAWL TỪ TRANG CHỦ CHÍNH HÃNG VINFAST (vinfastauto.com).
   -> Bao gồm cả các link tải Brochure PDF thông số chi tiết của từng dòng xe.
3. `chinh_sach_uu_dai`: Thu thập từ trang Ưu đãi VinFast (vinfastauto.com/vn_vi/uu-dai) và văn bản chính sách.
4. `he_thong_tram_sac`: Hệ sinh thái V-GREEN và VinFast (vgreen.net, vinfastauto.com).
5. `tai_chinh_tra_gop`: Các ngân hàng đối tác liên kết và cổng tài chính VinFast.
6. `thu_tuc_phap_ly`: Bảo hiểm (Bảo Việt, PVI), Đăng kiểm, Cổng DVC, Luật Việt Nam.
7. `trai_nghiem_danh_gia`: Báo chí & chuyên trang đánh giá xe uy tín (XeHay, VnExpress...).
8. `hau_mai_bao_duong`: Chính sách bảo hành, bảo dưỡng, cứu hộ 24/7 chính hãng VinFast.

ĐẦU RA: File CSV lưu tại `data/urls.csv` (Mặc định không ghi đè sources.csv).
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any

# Cấu hình UTF-8 cho console Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
DEFAULT_OUTPUT_CSV = DATA_DIR / "urls.csv"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Danh mục chuẩn hóa cho Web & Tài liệu (Loại bỏ gia_ca_lan_banh khỏi web crawler vì đã dùng Relational API)
VALID_CATEGORIES = {
    "thong_so_ky_thuat",
    "chinh_sach_uu_dai",
    "he_thong_tram_sac",
    "tai_chinh_tra_gop",
    "thu_tuc_phap_ly",
    "trai_nghiem_danh_gia",
    "hau_mai_bao_duong",
}

# ==============================================================================
# DANH SÁCH HẠT GIỐNG (SEEDS) ĐƯỢC CHỌN LỌC CHUẨN XÁC
# ==============================================================================

SEED_ENTRIES: list[dict[str, str]] = [
    # --------------------------------------------------------------------------
    # 1. THONG_SO_KY_THUAT (CHỈ TỪ TRANG CHỦ VINFAST & TÀI LIỆU BROCHURE CHÍNH HÃNG)
    # --------------------------------------------------------------------------
    {
        "title": "Thông số kỹ thuật & Thiết kế VinFast VF 3",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Brochure PDF Thông số kỹ thuật chi tiết VinFast VF 3",
        "url": "https://static-cms-prod.vinfastauto.com/statics/shared/16062026-Brochure-VF-3.pdf",
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
        "title": "Thông số kỹ thuật xe bán tải điện VinFast VF Wild",
        "url": "https://vinfastauto.com/vn_vi/dat-coc-xe-vf-wild",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe tải điện VinFast EC Van",
        "url": "https://vinfastauto.com/vn_vi/vinfast-ecvan",
        "category": "thong_so_ky_thuat",
    },

    # --------------------------------------------------------------------------
    # 2. CHINH_SACH_UU_DAI (TRANG CHỦ ƯU ĐÃI Ô TÔ ĐIỆN VINFAST)
    # --------------------------------------------------------------------------
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
        "title": "Chính sách miễn 100% lệ phí trước bạ cho ô tô điện chạy pin",
        "url": "https://luatvietnam.vn/thue-phi/chinh-sach-le-phi-truoc-ba-o-to-dien-561-90123-article.html",
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

    # --------------------------------------------------------------------------
    # 3. HE_THONG_TRAM_SAC (Ô TÔ ĐIỆN)
    # --------------------------------------------------------------------------
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

    # --------------------------------------------------------------------------
    # 4. TAI_CHINH_TRA_GOP
    # --------------------------------------------------------------------------
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
        "title": "Điều kiện, hồ sơ, thủ tục mua xe máy và ô tô trả góp 2026",
        "url": "https://techcombank.com/thong-tin/blog/thu-tuc-mua-xe-tra-gop",
        "category": "tai_chinh_tra_gop",
    },
    {
        "title": "Gói vay ưu đãi lãi suất cố định mua ô tô điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/chinh-sach-vay-mua-xe-tra-gop",
        "category": "tai_chinh_tra_gop",
    },

    # --------------------------------------------------------------------------
    # 5. THU_TUC_PHAP_LY
    # --------------------------------------------------------------------------
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
        "title": "Hướng dẫn thủ tục bấm biển số xe định danh online cổng Dịch vụ công",
        "url": "https://luatvietnam.vn/thu-tuc-dang-ky-bien-so-dinh-danh-561-92341-article.html",
        "category": "thu_tuc_phap_ly",
    },
    {
        "title": "Quy định đăng kiểm ô tô mới & chu kỳ kiểm định ô tô điện",
        "url": "https://luatvietnam.vn/quy-dinh-dang-kiem-o-to-dien-561-94521-article.html",
        "category": "thu_tuc_phap_ly",
    },
    {
        "title": "Hợp đồng và điều khoản pháp lý bán hàng VinFast Auto",
        "url": "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach",
        "category": "thu_tuc_phap_ly",
    },
    {
        "title": "Điều khoản pháp lý và quyền riêng tư VinFast Auto",
        "url": "https://vinfastauto.com/vn_vi/dieu-khoan-phap-ly",
        "category": "thu_tuc_phap_ly",
    },

    # --------------------------------------------------------------------------
    # 6. TRAI_NGHIEM_DANH_GIA (Ô TÔ ĐIỆN VINFAST)
    # --------------------------------------------------------------------------
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
        "title": "VinFast VF 8 thế hệ mới lộ nội thất nâu - đen, thêm nhiều nâng cấp đáng chú ý",
        "url": "https://xehay.vn/vinfast-vf-8-the-he-moi-lo-noi-that-nau-den-them-nhieu-nang-cap-dang-chu-y.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Những cải tiến kỹ thuật ấn tượng của VinFast VF 8 thế hệ mới",
        "url": "https://xehay.vn/nhung-cai-tien-ky-thuat-an-tuong-cua-vinfast-vf-8-the-he-moi.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Người Sài Gòn lái thử VinFast VF 8: “Đáng mua nhất trong tầm giá 1 tỷ đồng”",
        "url": "https://xehay.vn/nguoi-sai-gon-lai-thu-vinfast-vf-8-dang-mua-nhat-trong-tam-gia-1-ty-dong.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Người trẻ hào hứng sau tay lái VinFast VF 7 và VF 8: “Trải nghiệm thú vị, mang lại sự an tâm”",
        "url": "https://xehay.vn/nguoi-tre-hao-hung-sau-tay-lai-vinfast-vf-7-va-vf-8-trai-nghiem-thu-vi-mang-lai-su-an-tam.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "[ĐÁNH GIÁ XE] Người dùng đánh giá VinFast VF 9: Đẹp, cao cấp, lái hay và rất phù hợp cho gia đình",
        "url": "https://xehay.vn/danh-gia-xe-nguoi-dung-danh-gia-vinfast-vf-9-dep-cao-cap-lai-hay-va-rat-phu-hop-cho-gia-dinh.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chủ xe VinFast VF 9: “Người lái thấy sướng, người ngồi sau ngủ ngon”",
        "url": "https://xehay.vn/chu-xe-vinfast-vf-9-nguoi-lai-thay-suong-nguoi-ngoi-sau-ngu-ngon.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Người dùng VinFast VF 9 thừa nhận bị “chiều hư” vì ghế ngồi quá thoải mái, không gian rộng rãi",
        "url": "https://xehay.vn/nguoi-dung-vinfast-vf-9-thua-nhan-bi-chieu-hu-vi-ghe-ngoi-qua-thoai-mai-khong-gian-rong-rai-tien-nghi-thuong-gia.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 9 nâng tầm trải nghiệm thượng lưu trên mọi hành trình",
        "url": "https://xehay.vn/vinfast-vf-9-nang-tam-trai-nghiem-thuong-luu-tren-moi-hanh-trinh.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chinh phục Tà Xùa, chủ xe ví trải nghiệm VinFast VF 7 như xe vài tỷ",
        "url": "https://xehay.vn/chinh-phuc-ta-xua-chu-xe-vi-trai-nghiem-vinfast-vf-7-nhu-xe-vai-ty.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chủ xe Gen Z chọn VinFast VF 7: Cảm giác lái và dịch vụ hậu mãi là yếu tố tiên quyết",
        "url": "https://xehay.vn/chu-xe-gen-z-chon-vinfast-vf-7-cam-giac-lai-va-dich-vu-hau-mai-la-yeu-to-tien-quyet.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Đi xa càng “sướng”: VinFast VF 7 giúp cả nhà nhẹ đầu trên hành trình dài",
        "url": "https://xehay.vn/di-xa-cang-suong-vinfast-vf-7-giup-ca-nha-nhe-dau-tren-hanh-trinh-dai.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Cận cảnh VinFast VF 7 phiên bản thương mại ngoài đời thực",
        "url": "https://xehay.vn/can-canh-vinfast-vf-7-phien-ban-ban-thuong-mai-ngoai-doi-thuc.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 7 ghi điểm với gia đình Việt: Không gian rộng thoáng, tiết kiệm chi phí",
        "url": "https://xehay.vn/vinfast-vf-7-ghi-diem-voi-gia-dinh-viet-khong-gian-rong-thoang-tiet-kiem-chi-phi-tu-tien-sac-toi-bao-duong.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast bàn giao những chiếc VF 7 Hỏa Long Độc Bản đầu tiên cho khách hàng Việt",
        "url": "https://xehay.vn/vinfast-vf-7-hoa-long-doc-ban-dau-tien-duoc-ban-giao-cho-khach-hang-viet.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "[ĐÁNH GIÁ NHANH] VinFast VF 6: Sắc bén, tiện nghi, giá tốt",
        "url": "https://xehay.vn/danh-gia-nhanh-vinfast-vf-6-sac-ben-tien-nghi-gia-tot.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Khách hàng lái thử VF 6 trên toàn quốc: Chốt vì lái hay, an toàn, chi phí quá tiết kiệm",
        "url": "https://xehay.vn/khach-hang-lai-thu-vf-6-tren-toan-quoc-chot-vi-lai-hay-an-toan-chi-phi-qua-tiet-kiem.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 6 - mẫu SUV điện hạng B của hãng xe Việt lộ diện",
        "url": "https://xehay.vn/vinfast-vf-6-mau-suv-dien-hang-b-cua-hang-xe-viet-lo-dien.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Chi tiết VinFast VF 3 Plus tại đại lý: Thêm camera lùi, gương chỉnh điện",
        "url": "https://xehay.vn/chi-tiet-vinfast-vf-3-plus-tai-dai-ly-them-camera-lui-guong-chinh-dien-gia-315-trieu-dong.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 5 Plus bản thương mại lộ diện, chuẩn bị bàn giao tới khách hàng",
        "url": "https://xehay.vn/vinfast-vf-5-plus-ban-thuong-mai-lo-dien-chuan-bi-ban-giao-toi-khach-hang.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "VinFast VF 5 chứng minh vị thế SUV “đáng tiền nhất” cho người mua xe lần đầu",
        "url": "https://xehay.vn/vinfast-vf-5-chung-minh-vi-the-suv-dang-tien-nhat-cho-nguoi-mua-xe-lan-dau.html",
        "category": "trai_nghiem_danh_gia",
    },
    {
        "title": "Đánh giá chi tiết ưu nhược điểm xe điện sau 20.000km sử dụng thực tế",
        "url": "https://vnexpress.net/danh-gia-o-to-dien-vinfast-sau-20000km-4712391.html",
        "category": "trai_nghiem_danh_gia",
    },

    # --------------------------------------------------------------------------
    # 7. HAU_MAI_BAO_DUONG (Ô TÔ ĐIỆN VINFAST)
    # --------------------------------------------------------------------------
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
    {
        "title": "Câu hỏi thường gặp về quy trình bảo dưỡng và cứu hộ xe VinFast",
        "url": "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap",
        "category": "hau_mai_bao_duong",
    },
]


# ==============================================================================
# HÀM CÀO ĐỘNG BỔ SUNG TỪ TIN TỨC & CHUYÊN MỤC
# ==============================================================================

def fetch_html(url: str, timeout: int = 6) -> str:
    """Tải nội dung HTML nhanh chóng và ổn định bằng curl -4 / urllib."""
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

    # Fallback sang urllib nếu curl không phản hồi
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


def clean_text(text: str) -> str:
    """Làm sạch ký tự HTML thừa."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", text)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def classify_topic_from_text(title: str, url: str) -> str | None:
    """Tự động phân loại URL vào các nhóm chủ đề được phép (loại trừ xe máy và giá lăn bánh)."""
    t = f"{title} {url}".lower()

    # BỎ TOÀN BỘ DATA XE MÁY, XE ĐẠP ĐIỆN
    motorbike_keywords = [
        "xe-may", "xe máy", "xmd", "xe dap", "xe-dap", "xedap", "feliz",
        "evo", "klara", "vento", "theon", "viper", "drgnfly", "ebike",
        "e-scooter", "xe hai banh", "xe 2 banh", "scooter"
    ]
    if any(k in t for k in motorbike_keywords):
        return None

    # Nếu là giá lăn bánh bên ngoài -> bỏ qua không thu thập (tránh xung đột với relational API)
    if any(k in t for k in ["lan-banh", "lăn bánh", "chi-phi-lan-banh"]):
        return None

    # Thông số kỹ thuật CHỈ chấp nhận từ domain vinfastauto.com
    is_vinfast = "vinfast" in url.lower() or "vinfastauto" in url.lower()
    if any(k in t for k in ["thong-so", "thông số", "dong-co", "pin-catl", "kich-thuoc", "specs", "ky-thuat", "brochure"]):
        return "thong_so_ky_thuat" if is_vinfast else "trai_nghiem_danh_gia"

    if any(k in t for k in ["uu-dai", "ưu đãi", "khuyen-mai", "khuyến mại", "voucher", "giam-gia", "vinclub", "manh-liet"]):
        return "chinh_sach_uu_dai"
    if any(k in t for k in ["tram-sac", "trạm sạc", "vgreen", "tru-sac", "phi-sac", "sac-nhanh", "doi-pin", "pin-va-tram-sac"]):
        return "he_thong_tram_sac"
    if any(k in t for k in ["lai-suat", "lãi suất", "vay", "tra-gop", "trả góp", "ngan-hang", "ngân hàng", "tin-dung", "tai-chinh"]):
        return "tai_chinh_tra_gop"
    if any(k in t for k in ["bao-hiem", "bảo hiểm", "phap-ly", "pháp lý", "bien-so", "biển số", "dinh-danh", "dang-kiem", "đăng kiểm", "hop-dong"]):
        return "thu_tuc_phap_ly"
    if any(k in t for k in ["bao-duong", "bảo dưỡng", "cuu-ho", "cứu hộ", "hau-mai", "hậu mãi", "sua-chua", "sửa chữa", "bao-hanh", "bảo hành"]):
        return "hau_mai_bao_duong"

    # Mặc định cho tin tức, review xe
    return "trai_nghiem_danh_gia"


def discover_dynamic_news_urls(max_pages: int = 3) -> list[dict[str, str]]:
    """Quét động các bài viết từ VinFast Auto và V-GREEN (CHỈ Ô TÔ ĐIỆN)."""
    feeds = [
        {"url": "https://vinfastauto.com/vn_vi/uu-dai", "default_cat": "chinh_sach_uu_dai"},
        {"url": "https://vinfastauto.com/vn_vi/tin-tuc/o-to-dien", "default_cat": "trai_nghiem_danh_gia"},
        {"url": "https://vinfastauto.com/vn_vi/tin-tuc/cong-ty", "default_cat": "chinh_sach_uu_dai"},
        {"url": "https://vgreen.net/vi/tin-tuc", "default_cat": "he_thong_tram_sac"},
    ]

    discovered: list[dict[str, str]] = []
    seen: set[str] = set()

    for feed in feeds:
        base_url = feed["url"]
        print(f"🌐 Đang quét nguồn: {base_url}...")
        for p in range(0, max_pages):
            p_url = f"{base_url}?page={p}" if p > 0 else base_url
            html = fetch_html(p_url)
            if not html or len(html) < 400:
                break

            matches = re.findall(r'<a[^>]+href="(/v[ni]_[^"]+|/vi/[^"]+|https://[^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.DOTALL | re.I)
            for href, anchor in matches:
                clean_href = href.split("?")[0].strip()
                if any(x in clean_href for x in ["/tin-tuc", "/cau-hoi-thuong-gap", "/tim-kiem"]) and clean_href.count("/") <= 2:
                    continue

                if clean_href.startswith("https://"):
                    full_url = clean_href
                elif clean_href.startswith("/vn_vi/"):
                    full_url = f"https://vinfastauto.com{clean_href}"
                else:
                    full_url = f"https://vgreen.net{clean_href}"

                if full_url in seen:
                    continue
                seen.add(full_url)

                title = clean_text(anchor)
                if not title or len(title) < 8 or "Xem thêm" in title:
                    slug = clean_href.split("/")[-1].replace(".html", "").replace(".pdf", "").replace("-", " ")
                    title = slug.capitalize()

                cat = classify_topic_from_text(title, full_url)
                if cat is None:
                    # Bỏ qua nhóm gia_ca_lan_banh để tránh xung đột
                    continue

                # Kiểm tra nghiêm ngặt: thong_so_ky_thuat chỉ từ vinfastauto.com
                if cat == "thong_so_ky_thuat" and "vinfast" not in full_url.lower():
                    cat = "trai_nghiem_danh_gia"

                discovered.append({
                    "title": title,
                    "url": full_url,
                    "category": cat,
                })
            time.sleep(0.3)

    return discovered


# ==============================================================================
# XUẤT FILE CSV
# ==============================================================================

def export_urls_to_csv(records: list[dict[str, str]], output_path: Path) -> None:
    """Xuất danh sách URLs thành file CSV chuẩn UTF-8-BOM."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["title", "url", "category"]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "title": r["title"].strip(),
                "url": r["url"].strip(),
                "category": r["category"].strip(),
            })

    print(f"\n💾 ĐÃ LƯU THÀNH CÔNG: {output_path} ({len(records)} URLs)")


def main() -> None:
    """Hàm chính điều phối quy trình crawl URLs."""
    parser = argparse.ArgumentParser(
        description="Crawl toàn diện danh sách URLs (Loại bỏ giá lăn bánh xung đột, thông số kỹ thuật chuẩn VinFast)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(DEFAULT_OUTPUT_CSV),
        help="Đường dẫn file CSV xuất ra (mặc định: data/urls.csv)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Số trang tin tức tối đa cần quét cho mỗi chuyên mục (mặc định: 3)",
    )
    args = parser.parse_args()

    start_time = time.time()
    out_path = Path(args.output)

    print("=" * 70)
    print("🚀 URLS CRAWLER ĐƯỢC ĐIỀU CHỈNH THEO QUY TẮC NGUỒN CHUẨN:")
    print("   1. 'gia_ca_lan_banh': Bỏ qua (Đã có Relational API VinFast).")
    print("   2. 'thong_so_ky_thuat': CHỈ lấy từ vinfastauto.com & brochure PDF.")
    print("   3. 'chinh_sach_uu_dai': Lấy từ vinfastauto.com/vn_vi/uu-dai & văn bản.")
    print(f"   Vị trí xuất file: {out_path}")
    print("=" * 70)

    all_records: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # 1. Nạp danh mục hạt giống
    print("\n[1/2] Nạp danh sách URLs hạt giống chất lượng cao...")
    for s in SEED_ENTRIES:
        u = s["url"].strip()
        c = s["category"].strip()

        # Kiểm tra tính hợp lệ
        if c == "gia_ca_lan_banh":
            continue
        if c == "thong_so_ky_thuat" and "vinfast" not in u.lower():
            continue

        if u not in seen_urls:
            seen_urls.add(u)
            all_records.append(s)
    print(f"   -> Đã nạp {len(all_records)} URLs hạt giống.")

    # 2. Quét động thêm các bài viết mới từ VinFast & V-GREEN
    print("\n[2/2] Quét động bài viết từ các feed tin tức VinFast & V-GREEN...")
    dynamic_items = discover_dynamic_news_urls(max_pages=args.max_pages)
    new_count = 0
    for item in dynamic_items:
        u = item["url"].strip()
        if u not in seen_urls:
            seen_urls.add(u)
            all_records.append(item)
            new_count += 1
    print(f"   -> Đã bổ sung thêm {new_count} URLs từ quét động.")

    # 3. Xuất file CSV (urls.csv)
    export_urls_to_csv(all_records, out_path)

    # 4. Báo cáo thống kê
    cat_counts: dict[str, int] = {k: 0 for k in sorted(VALID_CATEGORIES)}
    for r in all_records:
        c = r["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1

    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT THU THẬP {len(all_records)} URLS TRONG {duration:.2f} GIÂY!")
    print("\n📊 PHÂN BỐ DỮ LIỆU THEO CÁC NHÓM CHỦ ĐỀ:")
    for cat, cnt in cat_counts.items():
        print(f"   - {cat:<24}: {cnt:>3} URLs")
    print("=" * 70)


if __name__ == "__main__":
    main()
