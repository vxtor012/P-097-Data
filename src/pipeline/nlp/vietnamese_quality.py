"""
Vietnamese content quality scoring and boilerplate stripper.
Ensures silver records meet high standards for RAG and search.
"""

import re
from typing import Tuple

# All Vietnamese letters with diacritics (lower and upper)
VIETNAMESE_DIACRITICS = set(
    "áàảãạăắằẳẵặâấầẩẫậđ"
    "éèẻẽẹêếềểễệ"
    "íìỉĩị"
    "óòỏõọôốồổỗộơớờởỡợ"
    "úùủũụưứừửữự"
    "ýỳỷỹỵ"
    "ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐ"
    "ÉÈẺẼẸÊẾỀỂỄỆ"
    "ÍÌỈĨỊ"
    "ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ"
    "ÚÙỦŨỤƯỨỪỬỮỰ"
    "ÝỲỶỸỴ"
)

# Common crawled boilerplate patterns in Vietnamese web pages
BOILERPLATE_PATTERNS = [
    r"(?i)chia\s+sẻ\s+bài\s+viết\s*(qua)?\s*:?.*",
    r"(?i)chia\s+sẻ\s+lên\s+(facebook|zalo|twitter|linkedin).*",
    r"(?i)bình\s+luận\s*\(\d+\).*",
    r"(?i)gửi\s+ý\s+kiến\s+của\s+bạn.*",
    r"(?i)theo\s+dõi\s+chúng\s+tôi\s+trên.*",
    r"(?i)bản\s+quyền\s+(thuộc\s+về|\©|\(c\)).*",
    r"(?i)mọi\s+hành\s+vi\s+sao\s+chép\s+phải\s+có\s+sự\s+đồng\s+ý.*",
    r"(?i)hotline\s*(hỗ\s+trợ|tư\s+vấn)?\s*:\s*[\d\s.-]+",
    r"(?i)đăng\s+ký\s+nhận\s+tin\s*(mới\s+nhất)?.*",
    r"(?i)chính\s+sách\s+bảo\s+mật\s*\|\s*điều\s+khoản\s+sử\s+dụng.*",
    r"(?i)bài\s+viết\s+liên\s+quan\s*:?.*",
    r"(?i)tin\s+cùng\s+chuyên\s+mục\s*:?.*",
    r"(?i)xem\s+thêm\s*:.*",
    r"(?i)\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*about:\s*blank.*",
    r"(?i)about:\s*blank.*",
    r"(?i)\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*.*(?:https?://|Nghị định|Thông tư|Luật).*",
    r"(?i)https?://(?:www\.)?luatvietnam\.vn/\S*",
    r"(?i)https?://(?:www\.)?thuvienphapluat\.vn/\S*",
    r"(?i)\bPhân tích Hiệu lực:\s*Đã biết\b",
    r"(?i)\bTình trạng hiệu lực:\s*Đã biết\b",
    r"(?i)\bPhân tích\s*(?:Phân tích)+\b",
]
COMPILED_BOILERPLATE = [re.compile(p) for p in BOILERPLATE_PATTERNS]


def strip_vietnamese_boilerplate(text: str) -> str:
    """Strip common Vietnamese news and corporate website boilerplate lines."""
    if not text:
        return ""

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        # Clean inline print watermarks & analysis tags
        stripped = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*.*?(?:https?://\S+|Nghị định[^\n.]+)", "", stripped)
        stripped = re.sub(r"https?://(?:www\.)?luatvietnam\.vn/\S*", "", stripped)
        stripped = re.sub(r"https?://(?:www\.)?thuvienphapluat\.vn/\S*", "", stripped)
        stripped = re.sub(r"(?i)\bPhân tích(?:\s+Hiệu lực:\s*Đã biết|\s+Tình trạng hiệu lực:\s*Đã biết|\s+Phân tích)*\b", "", stripped)
        stripped = re.sub(r"\s{2,}", " ", stripped).strip()

        if not stripped:
            continue

        # Check if line matches known boilerplate
        is_boilerplate = False
        for pattern in COMPILED_BOILERPLATE:
            if pattern.search(stripped):
                is_boilerplate = True
                break

        if not is_boilerplate:
            cleaned_lines.append(stripped)

    # Rejoin and collapse blank lines
    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


class VietnameseQualityScorer:
    """Calculates Vietnamese linguistic fidelity, structural richness, and quality score."""

    def __init__(self, min_diacritic_ratio: float = 0.03, min_doc_len: int = 50):
        self.min_diacritic_ratio = min_diacritic_ratio
        self.min_doc_len = min_doc_len

    def compute_diacritic_ratio(self, text: str) -> float:
        """Calculate the proportion of alphabetic characters that have Vietnamese diacritics."""
        if not text:
            return 0.0

        alpha_chars = [c for c in text if c.isalpha()]
        if not alpha_chars:
            return 0.0

        diacritic_chars = [c for c in alpha_chars if c in VIETNAMESE_DIACRITICS]
        return len(diacritic_chars) / len(alpha_chars)

    def evaluate(self, text: str, title: str = "") -> Tuple[float, Dict[str, any]]:
        """
        Evaluate text quality for silver admission.
        Returns (quality_score [0.0 - 1.0], details_dict).
        """
        text_len = len(text.strip())
        diacritic_ratio = self.compute_diacritic_ratio(text)

        # Baseline checks
        if text_len < self.min_doc_len:
            return 0.0, {
                "passed": False,
                "reason": f"Text too short ({text_len} < {self.min_doc_len})",
                "diacritic_ratio": diacritic_ratio,
                "length": text_len,
            }

        # Diacritic check: English/foreign or corrupt unaccented Vietnamese
        has_sufficient_diacritics = diacritic_ratio >= self.min_diacritic_ratio

        # Calculate composite score components
        # 1. Length score (up to 0.3)
        length_score = min(0.3, (text_len / 1000) * 0.3)

        # 2. Vietnamese linguistic fidelity (up to 0.3)
        # Typical Vietnamese text has 10% - 25% diacritics
        if diacritic_ratio >= 0.08:
            vietnamese_score = 0.3
        elif diacritic_ratio >= self.min_diacritic_ratio:
            vietnamese_score = 0.2
        else:
            vietnamese_score = 0.05  # Mostly English/numbers or unaccented

        # 3. Structural richness: headers, lists, paragraphs (up to 0.4)
        structure_score = 0.1
        if "#" in text:
            structure_score += 0.1
        if any(marker in text for marker in ["\n- ", "\n* ", "\n1. ", "\n|"]):
            structure_score += 0.1
        if len(text.split("\n\n")) >= 3:
            structure_score += 0.1

        composite_score = round(length_score + vietnamese_score + structure_score, 3)

        passed = text_len >= self.min_doc_len and (has_sufficient_diacritics or text_len > 200)

        return composite_score, {
            "passed": passed,
            "quality_score": composite_score,
            "diacritic_ratio": round(diacritic_ratio, 4),
            "length": text_len,
            "word_count": len(text.split()),
        }
