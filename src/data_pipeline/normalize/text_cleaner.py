"""src/data_pipeline/normalize/text_cleaner.py
Bộ công cụ làm sạch và chuẩn hóa văn bản Bronze → Silver.

Chức năng chính:
- Chuẩn hóa Unicode NFC cho tiếng Việt
- Khử dấu ngoặc kép thông minh, gạch ngang dài, ký tự ẩn
- Xóa header/footer/watermark/số trang lặp lại
- Loại bỏ rác web (navigation menu, sidebar tin liên quan, bản quyền giấy phép, nút CTA)
- Khử tiêu đề bị lặp ngay sau heading #
- Nối dòng bị ngắt vô lý (mid-sentence line breaks)
- Loại bỏ đoạn văn trùng lặp (content dedup)
- Chuẩn hóa khoảng trắng & khoảng cách dòng
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1. Bản đồ thay thế ký tự đặc biệt
# ---------------------------------------------------------------------------

_SMART_QUOTES_MAP: dict[str, str] = {
    "\u201c": '"',   # “
    "\u201d": '"',   # ”
    "\u201e": '"',   # „
    "\u2018": "'",   # ‘
    "\u2019": "'",   # ’
    "\u201a": "'",   # ‚
    "\u00ab": '"',   # «
    "\u00bb": '"',   # »
}

_DASH_MAP: dict[str, str] = {
    "\u2013": "-",   # en-dash –
    "\u2014": "-",   # em-dash —
    "\u2015": "-",   # horizontal bar ―
    "\u2012": "-",   # figure dash ‒
}

# Ký tự ẩn / zero-width cần loại bỏ hoàn toàn
_INVISIBLE_CHARS: re.Pattern[str] = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f"
    r"\u2028\u2029\u202a\u202b\u202c\u202d\u202e"
    r"\ufeff\ufff9\ufffa\ufffb\u00ad\u034f\u180e"
    r"\u061c\u2060\u2061\u2062\u2063\u2064]"
)

# ---------------------------------------------------------------------------
# 2. Pattern loại bỏ nhiễu kỹ thuật PDF & Web
# ---------------------------------------------------------------------------

# Số trang dạng "1/30", "Page 2 of 168", "Trang 5", "--- Page 3 ---"
_PAGE_NUMBER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^-{2,}\s*Page\s+\d+\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^Page\s+\d+\s*(?:of\s+\d+)?$", re.IGNORECASE),
    re.compile(r"^Trang\s+\d+(?:\s*/\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$"),
    re.compile(r"^-\s*\d{1,4}\s*-$"),
]

# Watermark / URL footer / boilerplate thường gặp
_NOISE_LINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"https?://\S+\s+\d{1,2}/\d{1,4}$", re.IGNORECASE),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}\s*(?:AM|PM)?\s+.+$", re.IGNORECASE),
    re.compile(r"^about:blank(?:\s*\d*/\d*)?$", re.IGNORECASE),
    re.compile(r"^Hiệu lực:\s*Đã biết$", re.IGNORECASE),
    re.compile(r"^Tình trạng hiệu lực:\s*Đã biết$", re.IGNORECASE),
    re.compile(r"^Phân tích$", re.IGNORECASE),
    # Web crawler HTML artifacts
    re.compile(r"^\s*<!--.*?-->\s*$", re.DOTALL),
    re.compile(r"^\s*-->\s*$"),
    re.compile(r"^\s*<!--\s*$"),
    re.compile(r".*for older IEs to work.*-->", re.IGNORECASE),
    re.compile(r"^TRANG THÔNG TIN Ô TÔ - XE MÁY-->?$", re.IGNORECASE),
    re.compile(r"^Xe Hay \| Chuyên trang thông tin.*-->?$", re.IGNORECASE),
    # Brand titles / HTML title trailers
    re.compile(r"^[^|\n]+\|\s*(?:VinFast|Techcombank|Xe Hay|V-Green)\s*$", re.IGNORECASE),
    # Web UI icons & status tags
    re.compile(r".*arrow_forward.*", re.IGNORECASE),
    re.compile(r"^\s*chevron_(?:left|right)\s*$", re.IGNORECASE),
    re.compile(r"^\s*đã hết hạn\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*$", re.IGNORECASE),
    # Giấy phép & Thông tin liên hệ cơ quan chủ quản (nhiễu báo chí)
    re.compile(r"^Giấy phép số:\s*.*$", re.IGNORECASE),
    re.compile(r"^Cấp ngày\s*\d{1,2}/\d{1,2}/\d{4}.*$", re.IGNORECASE),
    re.compile(r"^Chịu trách nhiệm nội dung:\s*.*$", re.IGNORECASE),
    re.compile(r"^Cơ quan chủ quản:\s*.*$", re.IGNORECASE),
    re.compile(r"^Địa chỉ:\s*.*(?:phường|quận|Hà Nội|TP\.?\s*HCM).*$", re.IGNORECASE),
    re.compile(r"^(?:Điện thoại|Email|Hotline):\s*[\d\s\w@\.\-]+$", re.IGNORECASE),
    re.compile(r"^Trang Thông tin Điện tử Tổng hợp$", re.IGNORECASE),
    # Nút bấm UI / Điều hướng trang web
    re.compile(r"^(?:Tài khoản|Đăng nhập / Đăng ký|Đăng nhập\s*/\s*Đăng ký|Đăng ký lái thử|Dự toán chi phí lăn bánh|Dự toán vay trả góp|So sánh xe|Tải Brochure|Xem tất cả|Đóng|Về đầu trang|Quay lại)$", re.IGNORECASE),
    re.compile(r"^(?:Speak-up hotline|VF eStore|Tìm Showroom & Trạm sạc|Cộng đồng VinFast toàn cầu|Lựa chọn quốc gia Việt Nam|Ưu đãi chỉ tới 31/12!|Đã có lỗi xảy ra\. Vui lòng thử lại\.|Thử lại)$", re.IGNORECASE),
    re.compile(r"^(?:Bắc Mỹ|United States|Canada|Francais|Châu Âu|Deutschland|Deutsch|Nederland|Nederlands|Châu Á|Việt Nam|Tiếng Việt|Others)$", re.IGNORECASE),
    # Tags & Phụ chú ảnh / Bút danh cuối bài báo
    re.compile(r"^Tags?:?$", re.IGNORECASE),
    re.compile(r"^TH\s*\([A-Za-z0-9]+\)$", re.IGNORECASE),
    re.compile(r"^Ảnh:\s*.*$", re.IGNORECASE),
    re.compile(r"^XE HAY$", re.IGNORECASE),
    # Website navigation bars, breadcrumbs & menu links (Xe Hay / Báo chí)
    re.compile(r"^\s*Trang chủ\s*$", re.IGNORECASE),
    re.compile(r"^\s*Tin Tức.*$", re.IGNORECASE),
    re.compile(r"^\s*Xe Hay TV.*$", re.IGNORECASE),
    re.compile(r"^\s*Emagazine.*$", re.IGNORECASE),
    re.compile(r"^\s*Kinh nghiệm(?:Ô tô.*)?$", re.IGNORECASE),
    re.compile(r"^\s*Xe và Thợ(?:Thợ Ô tô.*)?$", re.IGNORECASE),
    re.compile(r"^\s*Thể thao Xe xanh.*$", re.IGNORECASE),
    re.compile(r"^\s*Triển lãm Ô tô.*$", re.IGNORECASE),
    re.compile(r"^\s*Bảng giá(?:Ô tô.*)?$", re.IGNORECASE),
    re.compile(r"^\s*Thứ\s+[a-z0-9à-ỹ]+,\s*\d{1,2}/\d{1,2}/\d{4}.*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,2}:\d{2}\s*\|\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}\s*$", re.IGNORECASE),
    re.compile(r"^\s*Quốc tế Giao thông Giải trí\s*$", re.IGNORECASE),
    re.compile(r"^\s*Hùng Lâm\s*$", re.IGNORECASE),
    re.compile(r".*Toyota 2021\s*-\s*Look Back.*", re.IGNORECASE),
    re.compile(r"^\s*(?:Xe máy|Xe máy mới|Ô tô mới|Luật giao thông|Cafe Racer.*|Thợ Xe máy|Tokyo)\s*$", re.IGNORECASE),
    re.compile(r".*Đánh giá xe\s*Đánh giá.*", re.IGNORECASE),
    re.compile(r".*Bangkok\s+Detroit\s+Frankfurt.*", re.IGNORECASE),
    re.compile(r"^\s*SUV cỡ [A-E](?:\s*điện)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*VinFast\s+Xe điện\s+Vinfast.*$", re.IGNORECASE),
    # VinFast universal menu links
    re.compile(r"^\s*(?:Giới thiệu|Ô tô|Xe cá nhân|Xe dịch vụ|Động cơ xăng|Công cụ hỗ trợ khách hàng|Công cụ hỗ trợ)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Xe máy điện|Xe cao cấp|Xe trung cấp|Xe phổ thông|Tính chi phí sử dụng)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Phụ kiện xe|Dịch vụ hậu mãi|Dịch vụ bảo dưỡng|Dịch vụ sửa chữa|Thông tin cứu hộ|Đặt lịch dịch vụ|ĐẶT LỊCH DỊCH VỤ)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Tra cứu xưởng dịch vụ|Tra cứu tài liệu hướng dẫn|Ô tô điện|Xe bus)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Pin và trạm sạc|Pin và trạm sạc Ô tô điện|Pin và trạm sạc Xe máy điện|Lưu trữ năng lượng)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Sổ bảo hành ô tô|Hướng dẫn sử dụng ô tô|HƯỚNG DẪN SỬ DỤNG Ô TÔ)\s*$", re.IGNORECASE),
    re.compile(r"^\s*Sổ bảo hành\s+(?:VF\s*\w+|Lạc Hồng|Fadil|LUX|President).*", re.IGNORECASE),
    # Car catalog & seats lines when alone
    re.compile(r"^\s*(?:VinFast\s+)?(?:VF\s*(?:[2-9]|Wild|MPV\s*7|e34|8\s*Thế\s*hệ\s*mới|8\s*The\s*All\s*New)|EC\s*Van|Minio\s*Green|Herio\s*Green|Nerio\s*Green|Limo\s*Green|Fadil|Lux\s*A2\.0|Lux\s*SA2\.0|President|EBus)\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,2}\s+chỗ\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Xe đô thị(?: cỡ nhỏ| cỡ lớn| 7 chỗ)?|Xe gia đình(?: cỡ nhỏ| hạng sang)?|Xe doanh nhân|Bán tải điện|Xe dịch vụ(?: mini| cỡ lớn)?|Xe vận tải đô thị|Xe bus đô thị|Xe cá nhân thể thao)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Kinet|Viper|Vero\s*X|Kyo|Feliz(?:\s*2025|\s*II|\s*Lite|\s*S)?|Evo(?:\s*Grand|\s*Grand\s*Lite|\s*Lite|\s*Grand\s*Premia|\s*Grand\s*Limited|\s*Lite\s*Neo)?|Amio(?:\s*S|\s*S2)?|Flazz(?:\s*Max)?|ZGoo|VF\s*DrgnFly)\s*$", re.IGNORECASE),
    re.compile(r"^\s*Từ\s+[\d\.,]+\s*VNĐ\s*$", re.IGNORECASE),
    # V-Green specific navbar & CTA lines
    re.compile(r"^\s*(?:Sản phẩm dịch vụ|Cho đối tác, khách hàng|Về V-Green|Trạm [sS]ạc Ô [tT]ô [đĐ]iện|Trạm [sS]ạc Xe [mM]áy [đĐ]iện|Tủ Đổi Pin Xe Máy Điện|Góp ý về chất lượng dịch vụ|FAQs|EN)\s*$", re.IGNORECASE),
    re.compile(r"^\s*>>>\s*Khách hàng có thể tham khảo thêm về.*$", re.IGNORECASE),
    # VinFast Website Footer & Company boilerplate
    re.compile(r"^\s*(?:Hệ sinh thái|Vinhomes|Vinmec|Vinpearl|VinFast\. All rights reserved\.|© Copyright \d{4}|Về VinFast|Về Vingroup|Showroom & Đại lý|Điều khoản chính sách|Chính sách bảo vệ dữ liệu cá nhân|Chính sách vận chuyển|Chính sách đổi trả|Miễn trừ trách nhiệm|Điều khoản ký kết thỏa thuận đặt cọc mua Ô tô VinFast|Hợp đồng và chính sách|Dịch vụ khách hàng|Kết nối với VinFast|Tiện ích|Thẩm định vay|Tính chi phí sử dụng Xe máy điện|Mua sắm|Hỗ trợ|Thảo luận|Lựa chọn quốc gia|English|France)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:Công ty TNHH Kinh doanh Thương mại và Dịch vụ VinFast|MST/MSDN:?\s*\d+.*|Địa chỉ trụ sở chính:.*|Người đại diện theo pháp luật:.*|Chức vụ: Chủ tịch Hội đồng thành viên\.)\s*$", re.IGNORECASE),
    # Catalog download actions & filter dropdown lines
    re.compile(r"^\s*(?:Xem trước|Tải về|In|tìm kiếm|Chọn danh mục|Cho xe ô tô|Cho xe máy điện|Báo cáo tài chính|Hợp đồng mẫu|Thông tin trái phiếu|Khuyến mãi|Tài liệu xem nhiều)\s*$", re.IGNORECASE),
    re.compile(r"^\s*Năm 20[12]\d\s*$", re.IGNORECASE),
    # Additional Web noise & CTAs
    re.compile(r"^\s*Tìm hiểu thêm\s*$", re.IGNORECASE),
    re.compile(r"^\s*Nội dung đang được cập nhật\s*$", re.IGNORECASE),
    re.compile(r"^\s*Công ty\s*$", re.IGNORECASE),
    re.compile(r"^\s*https?://vinfast\.ethicspoint\.com/?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\[email\s*protected\]\s*$", re.IGNORECASE),
    re.compile(r"^\s*1900\s*23\s*23\s*89(?:\s*-\s*Nhánh\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^TH\s*-\s*.*$", re.IGNORECASE),
]

# Header hành chính lặp lại (quốc hiệu, tiêu ngữ)
_REPEATED_HEADER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT\s*NAM$", re.IGNORECASE),
    re.compile(r"^Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc$", re.IGNORECASE),
    re.compile(r"^_{3,}$"),
    re.compile(r"^-{3,}$"),
]


def normalize_unicode(text: str) -> str:
    """Chuẩn hóa Unicode NFC (dựng sẵn) cho tiếng Việt."""
    return unicodedata.normalize("NFC", text)


def replace_smart_quotes(text: str) -> str:
    """Thay thế dấu ngoặc kép / nháy đơn thông minh về dạng ASCII tiêu chuẩn."""
    for src, dst in _SMART_QUOTES_MAP.items():
        text = text.replace(src, dst)
    return text


def replace_dashes(text: str) -> str:
    """Chuẩn hóa gạch ngang dài (en/em dash) về dấu gạch ngang tiêu chuẩn."""
    for src, dst in _DASH_MAP.items():
        text = text.replace(src, dst)
    return text


def strip_invisible_chars(text: str) -> str:
    """Loại bỏ ký tự ẩn, zero-width space và ký tự không in được."""
    text = _INVISIBLE_CHARS.sub("", text)
    # Loại bỏ control chars (trừ \n, \r, \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def _is_noise_line(line: str) -> bool:
    """Kiểm tra xem dòng có phải nhiễu kỹ thuật (số trang, watermark, web UI boilerplate)."""
    stripped = line.strip()
    if not stripped:
        return False

    for pat in _PAGE_NUMBER_PATTERNS:
        if pat.match(stripped):
            return True

    for pat in _NOISE_LINE_PATTERNS:
        if pat.match(stripped):
            return True

    return False


def remove_noise_lines(text: str) -> str:
    """Loại bỏ các dòng nhiễu kỹ thuật: số trang, watermark, URL footer, web boilerplate."""
    lines = text.split("\n")
    cleaned = [line for line in lines if not _is_noise_line(line)]
    return "\n".join(cleaned)


def _is_repeated_header(line: str) -> bool:
    """Kiểm tra dòng có phải header hành chính lặp lại."""
    stripped = line.strip()
    for pat in _REPEATED_HEADER_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def remove_repeated_headers(text: str, *, keep_first: bool = True) -> str:
    """Loại bỏ header hành chính lặp lại, giữ lại lần xuất hiện đầu tiên nếu cần."""
    lines = text.split("\n")
    seen_headers: set[str] = set()
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _is_repeated_header(stripped):
            norm_key = re.sub(r"\s+", " ", stripped).upper()
            if keep_first and norm_key not in seen_headers:
                seen_headers.add(norm_key)
                result.append(line)
            # Bỏ qua các lần lặp tiếp theo
            continue
        result.append(line)

    return "\n".join(result)


def remove_duplicate_headings(text: str) -> str:
    """Loại bỏ dòng tiêu đề bị lặp ngay bên dưới heading # Markdown.

    Ví dụ:
        # ĐẶT CỌC VF WILD 15 TRIỆU ĐỒNG
        ĐẶT CỌC VF WILD 15 TRIỆU ĐỒNG
    -> Giữ lại duy nhất dòng `# ĐẶT CỌC VF WILD 15 TRIỆU ĐỒNG`
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 2:
        return text

    cleaned_paras: list[str] = []
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i]
        cleaned_paras.append(p)

        # Kiểm tra nếu p là Markdown heading (# Tiêu đề)
        if p.startswith("#"):
            heading_title = re.sub(r"^#+\s*", "", p).strip().lower()
            # Kiểm tra các đoạn văn ngay sau heading (tối đa 2 đoạn tiếp theo)
            j = i + 1
            while j < len(paragraphs) and j <= i + 2:
                next_p = paragraphs[j].strip()
                next_clean = re.sub(r"^[#>*\-\s]+", "", next_p).strip().lower()
                if heading_title and (next_clean == heading_title or (len(heading_title) > 25 and next_clean.startswith(heading_title))):
                    # Bỏ qua đoạn lặp này bằng cách xóa khỏi paragraphs
                    paragraphs.pop(j)
                    continue
                j += 1
        i += 1

    return "\n\n".join(cleaned_paras)


def strip_related_news_tail(text: str) -> str:
    """Cắt bỏ phần tin tức liên quan / sidebar rác ở cuối bài viết từ các trang tin (Xe Hay, báo chí).

    Dấu hiệu: Bắt đầu bằng 'Tin khác', 'Xem tiếp ...' và chứa danh sách các bài viết khác.
    """
    delimiters = [
        "\nTin khác\n",
        "\nXem tiếp ...\n",
        "\nXe và Thợ\n",
        "\nKinh nghiệm\n",
    ]
    for delim in delimiters:
        pos = text.find(delim)
        # Chỉ cắt nếu delimiter xuất hiện ở nửa sau của bài viết (> 40% chiều dài)
        if pos != -1 and pos > len(text) * 0.4:
            text = text[:pos].strip()

    return text


def strip_web_article_noise(text: str) -> str:
    """Loại bỏ khối header và banner cào từ các trang tin tức/báo chí (Xe Hay)."""
    # Xe Hay banner: Cắt bỏ từ đầu trang đến hết khối bản quyền/email liên hệ của Xe Hay
    if "xehay" in text.lower():
        pos_email = re.search(r"Email:\s*mailinh@xehay\.vn", text, re.IGNORECASE)
        if pos_email and pos_email.start() < len(text) * 0.4:
            text = text[pos_email.end():].strip()
            # Cắt bỏ tiếp các dòng ngày tháng, tiêu đề lặp ngay dưới email
            text = re.sub(
                r"^(?:-->|\s*Tin tức|\s*Thứ\s+[a-z0-9à-ỹ]+,\s*\d{1,2}/\d{1,2}/\d{4}.*|\s*\d{1,2}:\d{2}\s*\||\s*\d{1,2}/\d{1,2}/\d{4})*\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )

    return text


def heal_broken_lines(text: str) -> str:
    """Nối các dòng bị ngắt giữa chừng trong câu, giữ nguyên đoạn văn \\n\\n và heading #."""
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        current = lines[i]
        stripped = current.rstrip()

        # Nếu dòng trống → giữ nguyên (paragraph break)
        if not stripped:
            result.append("")
            i += 1
            continue

        # Nếu là dòng cuối → append và thoát
        if i + 1 >= len(lines):
            result.append(current)
            i += 1
            continue

        next_line = lines[i + 1].strip()

        # Không nối nếu dòng tiếp là trống (paragraph break)
        if not next_line:
            result.append(current)
            i += 1
            continue

        # Không nối nếu dòng tiếp bắt đầu bằng Markdown heading, list, table
        if re.match(r"^(#{1,6}\s|[-*+]\s|\d+\.\s|\|)", next_line):
            result.append(current)
            i += 1
            continue

        # Không nối nếu dòng hiện tại kết thúc bằng dấu chấm câu kết thúc
        if stripped and stripped[-1] in ".!?:;。）)》」】":
            result.append(current)
            i += 1
            continue

        # Nối dòng bị ngắt giữa chừng
        # Dòng hiện tại kết thúc bằng chữ thường, dấu phẩy hoặc liên từ
        if stripped and (
            stripped[-1].islower()
            or stripped[-1] in ",/và"
            or stripped.endswith(("của", "cho", "với", "để", "theo", "tại", "về"))
        ):
            merged = stripped + " " + next_line
            lines[i + 1] = merged  # Thay dòng tiếp theo bằng dòng đã nối
            i += 1
            continue

        result.append(current)
        i += 1

    return "\n".join(result)


def deduplicate_paragraphs(text: str) -> str:
    """Loại bỏ đoạn văn trùng lặp liên tiếp (content deduplication)."""
    paragraphs = re.split(r"\n{2,}", text)
    seen: set[str] = set()
    unique: list[str] = []

    for para in paragraphs:
        norm = re.sub(r"\s+", " ", para).strip()
        if not norm:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(para)

    return "\n\n".join(unique)


def normalize_whitespace(text: str) -> str:
    """Chuẩn hóa khoảng trắng: loại bỏ space thừa, tối đa 2 dòng trắng liên tiếp."""
    # Chuẩn hóa space ngang (không ảnh hưởng newline)
    text = re.sub(r"[ \t]+", " ", text)
    # Tối đa 2 newline liên tiếp
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim mỗi dòng
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)


def clean_text_pipeline(raw_text: str) -> str:
    """Pipeline đầy đủ làm sạch văn bản Bronze → Silver.

    Thứ tự xử lý:
    1. Unicode NFC
    2. Strip invisible chars
    3. Smart quotes → ASCII
    4. Dashes → standard hyphen
    5. Remove noise lines (page numbers, watermarks, web boilerplate)
    6. Strip related news tail (sidebar junk)
    7. Remove repeated headers
    8. Remove duplicate headings
    9. Heal broken lines
    10. Deduplicate paragraphs
    11. Normalize whitespace
    """
    if not raw_text:
        return ""

    text = normalize_unicode(raw_text)
    text = strip_invisible_chars(text)
    text = replace_smart_quotes(text)
    text = replace_dashes(text)
    text = strip_web_article_noise(text)
    text = remove_noise_lines(text)
    text = strip_related_news_tail(text)
    text = remove_repeated_headers(text, keep_first=True)
    text = remove_duplicate_headings(text)
    text = heal_broken_lines(text)
    text = deduplicate_paragraphs(text)
    text = normalize_whitespace(text)

    return text.strip()
