"""
Gold Layer filter and classifier for Car Purchasing Consultation knowledge.
Filters out general traffic laws, traffic violations/penalties, chassis modifications,
and non-automotive legal regulations, retaining only content directly assisting car buyers.
"""

import re
from typing import Dict, List, Optional, Tuple
from ..models.schemas import SilverChunk, SilverDocument

# Completely excluded legal/penalties documents (irrelevant to car purchasing)
EXCLUDED_DOCUMENT_PREFIXES = [
    "nghi dinh 100 2019",   # Traffic violation penalties (speeding, helmets, alcohol)
    "nghi dinh 123 2021",   # Amended traffic violation penalties
    "nghi dinh 13 2023",    # General personal data protection
    "thong tu 43 2023",     # Vehicle chassis remodeling & structural conversion
    "thong tu 85 2014",     # Vehicle conversion and structural modification
    "luat 36 2024 qh15",    # Road traffic order & driving conduct rules
    "nghi dinh 90 2023",    # General road maintenance toll collection mechanics
]

# Irrelevant traffic conduct and driving rules regex patterns
IRRELEVANT_TRAFFIC_RULES_REGEX = re.compile(
    r"(?i)điều\s+\d+\.\s*("
    r"sử\s+dụng\s+đèn|"
    r"sử\s+dụng\s+tín\s+hiệu\s+còi|"
    r"nhường\s+đường|"
    r"qua\s+phà|"
    r"giao\s+thông\s+tại\s+đường\s+ngang|"
    r"giao\s+thông\s+trên\s+đường\s+cao\s+tốc|"
    r"giao\s+thông\s+trong\s+hầm|"
    r"xe\s+ưu\s+tiên|"
    r"trường\s+hợp\s+chở\s+người\s+trên\s+thùng\s+xe|"
    r"xe\s+kéo\s+xe|"
    r"quy\s+tắc\s+chung|"
    r"tín\s+hiệu\s+giao\s+thông|"
    r"chấp\s+hành\s+hiệu\s+lệnh|"
    r"vượt\s+xe|"
    r"lùi\s+xe|"
    r"tránh\s+xe|"
    r"dừng\s+xe,\s+đỗ\s+xe|"
    r"người\s+đi\s+bộ|"
    r"người\s+khuyết\s+tật|"
    r"người\s+dẫn\s+dắt\s+súc\s+vật|"
    r"giao\s+thông\s+trên\s+cầu\s+phao|"
    r"cấp\s+cứu\s+người\s+bị\s+tai\s+nạn|"
    r"đào\s+tạo\s+lái\s+xe|"
    r"sát\s+hạch\s+lái\s+xe|"
    r"thanh\s+tra\s+giao\s+thông|"
    r"xử\s+phạt\s+vi\s+phạm\s+hành\s+chính|"
    r"tước\s+quyền\s+sử\s+dụng\s+giấy\s+phép\s+lái\s+xe|"
    r"tạm\s+giữ\s+phương\s+tiện|"
    r"nồng\s+độ\s+cồn"
    r")"
)

# Mandatory buying relevance keywords for Nghi Dinh 67 (Insurance)
INSURANCE_BUYING_KEYWORDS = [
    "mức phí", "biểu phí", "xe ô tô", "xe chở người", "dưới 6 chỗ",
    "từ 6 đến 11 chỗ", "xe máy", "bồi thường", "bảo hiểm bắt buộc",
    "thời hạn bảo hiểm", "chứng nhận bảo hiểm", "trách nhiệm dân sự",
]

# Domain taxonomy keywords for car purchasing and consultation
TOPIC_TAXONOMY: Dict[str, List[str]] = {
    "bao_gia_chi_phi": [
        "giá xe", "giá niêm yết", "giá bán", "lăn bánh", "chi phí lăn bánh",
        "lệ phí trước bạ", "trước bạ", "biển số", "phí cấp biển", "phí đăng ký",
        "bảng giá", "chi phí", "triệu đồng", "tỷ đồng", "dự toán chi phí",
        "phí bảo trì đường bộ", "đăng kiểm", "miễn trước bạ"
    ],
    "chinh_sach_uu_dai": [
        "ưu đãi", "khuyến mại", "chiết khấu", "giảm giá", "voucher",
        "thu cũ đổi mới", "chuyển đổi xanh", "mua 1 tặng 1", "quà tặng",
        "tri ân", "kích cầu", "hỗ trợ", "chương trình đặc biệt", "hạn chót"
    ],
    "tai_chinh_tra_gop": [
        "trả góp", "vay mua xe", "vay ngân hàng", "lãi suất", "thời hạn vay",
        "hạn mức vay", "tỷ lệ vay", "hồ sơ vay", "chứng minh thu nhập", "thế chấp",
        "đặt cọc", "hủy cọc", "rút cọc", "hợp đồng mua bán", "thanh toán", "hóa đơn"
    ],
    "pin_va_tram_sac": [
        "thuê pin", "mua pin", "kèm pin", "gói thuê pin", "cọc pin",
        "trạm sạc", "trụ sạc", "sạc pin", "chi phí sạc", "sạc tại nhà",
        "sạc nhanh", "dung lượng pin", "kwh", "quãng đường", "bảo hành pin"
    ],
    "thong_so_va_chon_xe": [
        "phiên bản", "bản eco", "bản plus", "bản base", "thông số kỹ thuật",
        "kích thước", "chiều dài", "chiều rộng", "công suất", "mã lực",
        "mô-men xoắn", "túi khí", "adas", "nội thất", "ngoại thất", "chọn xe",
        "so sánh xe", "đánh giá xe", "trải nghiệm lái", "cảm giác lái", "suv"
    ],
    "thu_tuc_phap_ly_so_huu": [
        "đăng ký xe", "cấp biển số", "biển số định danh", "thu hồi biển số",
        "sang tên", "thủ tục mua xe", "kiểm định an toàn", "chu kỳ kiểm định",
        "bảo hiểm bắt buộc", "bảo hiểm thân vỏ", "bảo hiểm tnds"
    ],
    "bao_hanh_hau_mai": [
        "bảo hành", "bảo dưỡng", "thời hạn bảo hành", "hậu mãi", "cứu hộ 24/7",
        "mobile service", "xưởng dịch vụ", "phụ tùng", "sửa chữa lưu động"
    ],
}


class GoldConsultationFilter:
    """Filter that screens and classifies silver content into car purchasing consultation Gold artifacts."""

    def __init__(self, min_score: float = 0.5):
        self.min_score = min_score

    def evaluate_chunk(self, chunk: SilverChunk) -> Tuple[bool, Optional[str], float, str]:
        """
        Evaluate if a SilverChunk is relevant to car purchasing / buyer consultation.
        Returns: (admitted, gold_topic, score, reason)
        """
        heading_path = chunk.heading_path or []
        top_doc = heading_path[0] if heading_path else ""
        content = chunk.content.lower()
        title_lower = top_doc.lower()

        # 1. Negative Document Check (penalties, general traffic rules, data privacy, conversion)
        for excl in EXCLUDED_DOCUMENT_PREFIXES:
            if excl in title_lower:
                return False, None, 0.0, f"Excluded legal document: {top_doc}"

        # 2. Negative Traffic Conduct Section Check
        if IRRELEVANT_TRAFFIC_RULES_REGEX.search(content):
            return False, None, 0.0, "Irrelevant traffic driving rule or penalty"

        # 3. Insurance Document (Nghi Dinh 67) Special Check
        if "nghi dinh 67 2023" in title_lower:
            has_buyer_relevance = any(kw in content for kw in INSURANCE_BUYING_KEYWORDS)
            if not has_buyer_relevance:
                return False, None, 0.0, "Insurance enterprise bureaucracy (non-vehicle buyer relevance)"

        # 4. Check for pure noise
        if "about: blank" in content and len(content.strip()) < 100:
            return False, None, 0.0, "Empty browser print noise"

        # 5. Check positive consultation relevance
        topic_scores = {}
        for topic, kws in TOPIC_TAXONOMY.items():
            matches = sum(1 for kw in kws if kw in content)
            if matches > 0:
                topic_scores[topic] = matches

        # Guaranteed passes for core categories
        category = chunk.category
        if category in ["chinh_sach_uu_dai", "gia_xe_va_chi_phi_lan_banh", "thong_so_ky_thuat", "faq", "trai_nghiem_danh_gia", "tai_chinh_tra_gop"]:
            best_topic = max(topic_scores.items(), key=lambda x: x[1])[0] if topic_scores else self._default_topic_for_cat(category)
            score = 0.95
            return True, best_topic, score, "Core consultation category"

        # For remaining legal documents (Lệ phí trước bạ, Thông tư cho vay, Đăng ký biển số xe, Đăng kiểm xe mới):
        if topic_scores:
            best_topic, match_count = max(topic_scores.items(), key=lambda x: x[1])
            score = min(1.0, 0.5 + (match_count * 0.1))
            if score >= self.min_score:
                return True, best_topic, round(score, 2), "Vehicle purchasing & ownership legality"

        return False, None, 0.0, "No car purchasing or consultation relevance"

    def evaluate_document(self, doc: SilverDocument) -> Tuple[bool, Optional[str], float, str]:
        """Evaluate if an entire SilverDocument should be preserved in Gold."""
        title_lower = doc.title.lower()
        source_id = doc.source_id.lower()

        for excl in EXCLUDED_DOCUMENT_PREFIXES:
            if excl in title_lower or excl.replace(" ", "_") in source_id:
                return False, None, 0.0, f"Excluded legal document: {doc.title}"

        # Core categories always admitted
        if doc.category in ["chinh_sach_uu_dai", "gia_xe_va_chi_phi_lan_banh", "thong_so_ky_thuat", "faq", "trai_nghiem_danh_gia", "tai_chinh_tra_gop"]:
            return True, self._default_topic_for_cat(doc.category), 1.0, "Core consultation category"

        # For legal docs, check if it's registration fee, banking loan, or license plate
        legal_kept_keywords = ["lệ phí trước bạ", "cho vay", "biển số", "kiểm định", "bảo hiểm bắt buộc"]
        if any(kw in title_lower for kw in legal_kept_keywords):
            return True, "thu_tuc_phap_ly_so_huu", 0.9, "Car purchasing & ownership legality document"

        return False, None, 0.0, "Non-automotive general regulation"

    def _default_topic_for_cat(self, cat: str) -> str:
        mapping = {
            "chinh_sach_uu_dai": "chinh_sach_uu_dai",
            "gia_xe_va_chi_phi_lan_banh": "bao_gia_chi_phi",
            "thong_so_ky_thuat": "thong_so_va_chon_xe",
            "trai_nghiem_danh_gia": "thong_so_va_chon_xe",
            "tai_chinh_tra_gop": "tai_chinh_tra_gop",
            "faq": "thong_so_va_chon_xe",
            "thu_tuc_phap_ly": "thu_tuc_phap_ly_so_huu",
        }
        return mapping.get(cat, "thong_so_va_chon_xe")
