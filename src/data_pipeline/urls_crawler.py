"""src/data_pipeline/urls_crawler.py
Script quét và thu thập danh sách toàn diện các URLs phục vụ 8 nhóm chủ đề cốt lõi.

8 Nhóm Chủ Đề (Topic / Category) chuẩn hóa:
1. gia_ca_lan_banh       : Giá niêm yết, chi phí đăng ký, thuế trước bạ, phí biển số.
2. thong_so_ky_thuat     : Kích thước, động cơ, pin, công suất, an toàn, ADAS.
3. chinh_sach_uu_dai     : Khuyến mãi đại lý, voucher, miễn giảm thuế trước bạ, VinClub.
4. he_thong_tram_sac     : Vị trí trạm sạc, công suất sạc, chi phí sạc/phút (V-GREEN & VinFast).
5. tai_chinh_tra_gop     : Lãi suất ngân hàng, gói vay, thủ tục chứng minh tài chính.
6. thu_tuc_phap_ly       : Quy trình bấm biển, đăng kiểm, nộp thuế, bảo hiểm TNDS/thân vỏ.
7. trai_nghiem_danh_gia  : Ưu nhược điểm từ người dùng, lỗi vặt, độ ồn, cảm giác lái, review.
8. hau_mai_bao_duong     : Lịch bảo dưỡng, chi phí kiểm tra pin, chính sách bảo hành, cứu hộ 24/7.

Nguồn thu thập:
- Hệ sinh thái VinFast Auto (vinfastauto.com, shop.vinfastauto.com)
- Mạng lưới trạm sạc V-GREEN (vgreen.net)
- Ngân hàng & Tài chính (Techcombank, VPBank, TPBank, Vietcombank...)
- Bảo hiểm & Pháp lý (Bảo Việt, PVI, Cổng Dịch vụ công, Cục Đăng kiểm, LuatVietnam...)
- Chuyên trang đánh giá xe uy tín (XeHay, VnExpress, Otofun, Autodaily, Tipcar...)

ĐẦU RA: File CSV lưu tại `src/data_pipeline/urls.csv` (Mặc định không ghi đè sources.csv).
"""

from __future__ import annotations

import argparse
import csv
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

# 8 danh mục chuẩn hóa theo yêu cầu
VALID_CATEGORIES = {
    "gia_ca_lan_banh",
    "thong_so_ky_thuat",
    "chinh_sach_uu_dai",
    "he_thong_tram_sac",
    "tai_chinh_tra_gop",
    "thu_tuc_phap_ly",
    "trai_nghiem_danh_gia",
    "hau_mai_bao_duong",
}

# ==============================================================================
# DANH SÁCH HẠT GIỐNG (SEEDS) ĐƯỢC CHỌN LỌC THEO 8 NHÓM CHỦ ĐỀ
# ==============================================================================

SEED_ENTRIES: list[dict[str, str]] = [
    # --------------------------------------------------------------------------
    # 1. GIA_CA_LAN_BANH
    # --------------------------------------------------------------------------
    {
        "title": "Dự toán chi phí lăn bánh ô tô điện VinFast toàn quốc",
        "url": "https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Bảng giá niêm yết & Đặt cọc ô tô điện VinFast",
        "url": "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Bảng giá niêm yết & Đặt cọc xe máy điện VinFast",
        "url": "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-may-dien.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Bảng giá xe VinFast mới nhất 2026 kèm ưu đãi lăn bánh",
        "url": "https://xehay.vn/bang-gia-xe-vinfast.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Chi phí lăn bánh VinFast VF 3 tại Hà Nội, TP.HCM và các tỉnh",
        "url": "https://xehay.vn/chi-phi-lan-banh-vinfast-vf-3.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Chi phí lăn bánh VinFast VF 5 Plus chi tiết sau miễn thuế trước bạ",
        "url": "https://xehay.vn/chi-phi-lan-banh-vinfast-vf-5-plus.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Chi phí lăn bánh VinFast VF 6 các phiên bản Base và Plus",
        "url": "https://xehay.vn/chi-phi-lan-banh-vinfast-vf-6.html",
        "category": "gia_ca_lan_banh",
    },
    {
        "title": "Chi phí lăn bánh VinFast VF 7 chi tiết các phiên bản",
        "url": "https://xehay.vn/chi-phi-lan-banh-vinfast-vf-7.html",
        "category": "gia_ca_lan_banh",
    },

    # --------------------------------------------------------------------------
    # 2. THONG_SO_KY_THUAT
    # --------------------------------------------------------------------------
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
        "title": "Thông số kỹ thuật VinFast VF 8 The All New (Nâng cấp 2026)",
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
        "title": "Thông số kỹ thuật xe máy điện VinFast Evo200 & Evo200 Lite",
        "url": "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-evo-200",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe máy điện VinFast Feliz S",
        "url": "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-feliz-s",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe máy điện VinFast Klara S (2022)",
        "url": "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-klara-s-2022",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe máy điện VinFast Vento S",
        "url": "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-vento-s",
        "category": "thong_so_ky_thuat",
    },
    {
        "title": "Thông số kỹ thuật xe máy điện VinFast Theon S",
        "url": "https://vinfastauto.com/vn_vi/xe-may-dien-vinfast-theon-s",
        "category": "thong_so_ky_thuat",
    },

    # --------------------------------------------------------------------------
    # 3. CHINH_SACH_UU_DAI
    # --------------------------------------------------------------------------
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
        "title": "Tổng hợp chương trình khuyến mại, voucher và ưu đãi mua xe VinFast",
        "url": "https://vinfastauto.com/vn_vi/uu-dai-mua-xe",
        "category": "chinh_sach_uu_dai",
    },

    # --------------------------------------------------------------------------
    # 4. HE_THONG_TRAM_SAC
    # --------------------------------------------------------------------------
    {
        "title": "Mạng lưới trạm sạc xe điện toàn quốc VinFast & V-GREEN",
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
    {
        "title": "Dịch vụ thuê pin, mua pin và đổi pin xe máy điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/dich-vu-pin-xe-may-dien",
        "category": "he_thong_tram_sac",
    },

    # --------------------------------------------------------------------------
    # 5. TAI_CHINH_TRA_GOP
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
    # 6. THU_TUC_PHAP_LY
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
        "title": "Bảo hiểm trách nhiệm dân sự bắt buộc cho xe máy Bảo Việt",
        "url": "https://baoviet.com/bao-hiem-xe-may-bao-viet.htm",
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
    # 7. TRAI_NGHIEM_DANH_GIA
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
    # 8. HAU_MAI_BAO_DUONG
    # --------------------------------------------------------------------------
    {
        "title": "Chính sách bảo hành 10 năm hoặc 200.000 km cho ô tô điện VinFast",
        "url": "https://vinfastauto.com/vn_vi/chinh-sach-bao-hanh-o-to",
        "category": "hau_mai_bao_duong",
    },
    {
        "title": "Chính sách bảo hành xe máy điện VinFast chính hãng",
        "url": "https://vinfastauto.com/vn_vi/chinh-sach-bao-hanh-xe-may",
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

def fetch_html(url: str, timeout: int = 15) -> str:
    """Tải nội dung HTML (urllib + fallback curl.exe)."""
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


def clean_text(text: str) -> str:
    """Làm sạch ký tự HTML thừa."""
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", "", text)
    t = unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def classify_topic_from_text(title: str, url: str) -> str:
    """Tự động phân loại URL vào 1 trong 8 nhóm chủ đề chuẩn hóa."""
    t = f"{title} {url}".lower()

    if any(k in t for k in ["gia", "lan-banh", "lăn bánh", "chi-phi-lan-banh", "bang-gia", "bảng giá"]):
        return "gia_ca_lan_banh"
    if any(k in t for k in ["thong-so", "thông số", "dong-co", "pin-catl", "kich-thuoc", "specs", "ky-thuat"]):
        return "thong_so_ky_thuat"
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
    """Quét động các bài viết từ VinFast Auto và V-GREEN."""
    feeds = [
        {"url": "https://vinfastauto.com/vn_vi/tin-tuc/o-to-dien", "default_cat": "trai_nghiem_danh_gia"},
        {"url": "https://vinfastauto.com/vn_vi/tin-tuc/xe-may-dien", "default_cat": "thong_so_ky_thuat"},
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

            matches = re.findall(r'<a[^>]+href="(/v[ni]_[^"]+|/vi/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL | re.I)
            for href, anchor in matches:
                clean_href = href.split("?")[0].strip()
                if any(x in clean_href for x in ["/tin-tuc", "/cau-hoi-thuong-gap", "/tim-kiem"]) and clean_href.count("/") <= 2:
                    continue

                full_url = f"https://vinfastauto.com{clean_href}" if clean_href.startswith("/vn_vi/") else f"https://vgreen.net{clean_href}"
                if full_url in seen:
                    continue
                seen.add(full_url)

                title = clean_text(anchor)
                if not title or len(title) < 12 or "Xem thêm" in title:
                    slug = clean_href.split("/")[-1].replace(".html", "").replace("-", " ")
                    title = slug.capitalize()

                cat = classify_topic_from_text(title, full_url)
                discovered.append({
                    "title": title,
                    "url": full_url,
                    "category": cat,
                })
            time.sleep(0.4)

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
        description="Crawl toàn diện danh sách URLs phục vụ 8 nhóm chủ đề cốt lõi"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(DEFAULT_OUTPUT_CSV),
        help="Đường dẫn file CSV xuất ra (mặc định: src/data_pipeline/urls.csv)",
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
    print("🚀 URLS CRAWLER THEO 8 NHÓM CHỦ ĐỀ CỐT LÕI")
    print(f"   Vị trí xuất file: {out_path}")
    print(f"   Số trang quét động: {args.max_pages}")
    print("   Lưu ý: Không ghi đè sources.csv (sources.csv là tập URL kiểm chứng)")
    print("=" * 70)

    all_records: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # 1. Nạp danh mục hạt giống từ tất cả 8 chủ đề (VinFast, V-Green, Techcombank, Bảo Việt, XeHay...)
    print("\n[1/2] Nạp danh sách URLs hạt giống theo 8 nhóm chủ đề...")
    for s in SEED_ENTRIES:
        u = s["url"].strip()
        if u not in seen_urls:
            seen_urls.add(u)
            all_records.append(s)
    print(f"   -> Đã nạp {len(all_records)} URLs hạt giống chất lượng cao.")

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

    # 4. Báo cáo thống kê theo 8 nhóm chủ đề
    cat_counts: dict[str, int] = {k: 0 for k in sorted(VALID_CATEGORIES)}
    for r in all_records:
        c = r["category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1

    duration = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT THU THẬP {len(all_records)} URLS TRONG {duration:.2f} GIÂY!")
    print("\n📊 PHÂN BỐ DỮ LIỆU THEO 8 NHÓM CHỦ ĐỀ (TOPIC / CATEGORY):")
    for cat, cnt in cat_counts.items():
        print(f"   - {cat:<24}: {cnt:>3} URLs")
    print("=" * 70)


if __name__ == "__main__":
    main()
