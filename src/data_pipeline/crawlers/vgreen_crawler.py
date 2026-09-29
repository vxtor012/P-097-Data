"""src/data_pipeline/crawlers/vgreen_crawler.py
Thu thập dữ liệu toàn diện đa cấp từ hệ thống V-GREEN (https://vgreen.net/vi):
- Bóc tách có chọn lọc (filtered deep crawl):
    + CHỈ LẤY: trạm sạc, phí sạc, xe VinFast, chính sách liên quan đến xe và pin, tủ đổi pin, biểu phí.
    + LOẠI BỎ: thông tin tập đoàn, giới thiệu công ty, nhà đầu tư, đối tác, nhượng quyền, mặt bằng.
- Phân loại lưu trữ:
    + Câu hỏi thường gặp V-GREEN -> data/landing/faqs/vgreen_faqs.json
    + Chính sách dịch vụ, biểu phí sạc & pin -> data/landing/policies/vgreen/
    + Tin tức, thông cáo ra mắt xe & chính sách sạc -> data/landing/news/articles/
- BẢO MẬT DỮ LIỆU: Tuyệt đối KHÔNG ghi vào thư mục relational (dành riêng cho VinFast Auto).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any

from src.data_pipeline.crawlers.crawler_utils import (
    CRAWLED_BIKE_MODELS,
    CRAWLED_CAR_MODELS,
    FAQS_DIR,
    NEWS_DIR,
    POLICIES_DIR,
    build_rag_metadata,
    clean_html,
    fetch_html,
    get_current_iso_timestamp,
    random_delay,
    save_json,
)

BASE_URL = "https://vgreen.net"

# Danh mục seed URLs khởi động khám phá
SEED_URLS = [
    "https://vgreen.net/vi",
    "https://vgreen.net/vi/tin-tuc",
    "https://vgreen.net/vi/san-pham-dich-vu",
    "https://vgreen.net/vi/san-pham-dich-vu?tab=oto",
    "https://vgreen.net/vi/san-pham-dich-vu?tab=xemay",
    "https://vgreen.net/vi/san-pham-dich-vu?tab=pin",
    "https://vgreen.net/vi/tram-sac-xe-may-dien",
    "https://vgreen.net/vi/ban-do-tram-sac",
    "https://vgreen.net/vi/cau-hoi-thuong-gap",
    "https://vgreen.net/vi/cong-bo-thong-tin-va-dieu-khoan-dich-vu",
    "https://vgreen.net/vi/quy-trinh-tiep-nhan-phan-hoi-thong-tin-va-giai-quyet-phan-anh-yeu-cau-khieu-nai-cua-khach-hang",
    "https://vgreen.net/vi/vinfast-mien-phi-sac-pin-cho-tat-ca-o-to-dien-den-ngay-30062027",
    "https://vgreen.net/vi/huong-dan-doi-pin-tai-tu-doi-pin-v-green-trong-3-buoc",
    "https://vgreen.net/vi/canh-bao-hanh-vi-pha-hoai-xam-pham-he-thong-tram-sac-va-tu-doi-pin-v-green",
    "https://vgreen.net/vi/v-green-dat-muc-tieu-xay-dung-500000-cong-sac-oto-dien",
    "https://vgreen.net/vi/vinfast-ra-mat-4-mau-xe-may-dien-moi-hoan-thien-lap-dat-4500-tram-doi-pin-dau-tien",
]

# Các mẫu từ khóa BỊ LOẠI TRỪ (tập đoàn, công ty, nhà đầu tư, đối tác, nhượng quyền, mặt bằng)
EXCLUDE_TOPIC_PATTERNS = [
    # Công ty & Tập đoàn
    r"vgreen-about",
    r"ve-v-green",
    r"về v-green",
    r"cong-ty",
    r"công ty",
    r"tap-doan",
    r"tập đoàn",
    r"doanh-nghiep",
    r"doanh nghiệp",
    r"tin-tuc_cong-ty",
    r"tin-tuc-cong-ty",
    r"tin-tuc_chinh-sach",
    r"tin-tuc_bao-chi-noi-gi",
    r"tin-tuc\?page=",
    r"tin-tuc_page_",
    # Nhà đầu tư & Đầu tư kinh doanh
    r"nha-dau-tu",
    r"nhà đầu tư",
    r"dau-tu",
    r"đầu tư",
    r"co-hoi-dau-tu",
    r"cơ hội đầu tư",
    r"mo-hinh-dau-tu",
    r"mô hình đầu tư",
    r"hoan-von",
    r"hoàn vốn",
    r"sinh-loi",
    r"sinh lời",
    r"npp",
    r"nhà phân phối",
    r"nha-phan-phoi",
    r"tuyen-chon-npp",
    r"tuyển chọn npp",
    r"tuyen-chon",
    r"tuyển chọn",
    r"ty-phu",
    r"tỷ phú",
    r"dan-song",
    r"dẫn sóng",
    r"mo-vang",
    r"mỏ vàng",
    r"gom-slot",
    r"gom slot",
    r"chi-100-ty",
    # Đối tác & Hợp tác doanh nghiệp (B2B)
    r"doi-tac",
    r"đối tác",
    r"cho-doi-tac-khach-hang",
    r"dang-ky-doi-tac",
    r"đăng ký đối tác",
    r"hop-tac",
    r"hợp tác",
    r"thoa-thuan-hop-tac",
    r"thỏa thuận hợp tác",
    r"thoa-thuan",
    r"mou",
    r"ky-ket",
    r"ký kết",
    r"nhuong-quyen",
    r"nhượng quyền",
    r"gia-thue-mat-bang",
    r"thuê mặt bằng",
    r"mat-bang",
    r"mặt bằng",
    r"tim-kiem-mat-bang",
    r"cho-thue-mat-bang",
    r"fast-tiep-tuc",
    r"evn",
    r"(?<!vin)fast",
    r"kn-holdings",
    r"telkom",
    r"prime-group",
    r"chargepoint",
    r"idico",
    r"trung-son",
    r"mwg",
    r"roadgrid",
    r"tho-dien-may-xanh",
    r"vikki",
    r"phan-trong-tue",
    r"minh-dao",
    r"thinh-cuong",
    r"etreego",
    r"home-credit",
    # Cảnh báo mạo danh / phi liên quan
    r"gia-mao",
    r"giả mạo",
    r"lua-dao",
    r"lừa đảo",
    r"tin-chi-carbon",
    r"tuyen-dung",
    r"tuyển dụng",
    r"thu-4-ngay-xanh",
    r"register-charging-battery",
]

# Các mẫu từ khóa BẮT BUỘC THỎA MÃN (trạm sạc, phí sạc, xe vin, pin, chính sách pin/sạc)
INCLUDE_TOPIC_PATTERNS = [
    r"tram-sac",
    r"trạm sạc",
    r"tru-sac",
    r"trụ sạc",
    r"cong-sac",
    r"cổng sạc",
    r"tu-doi-pin",
    r"tủ đổi pin",
    r"doi-pin",
    r"đổi pin",
    r"phi-sac",
    r"phí sạc",
    r"mien-phi-sac",
    r"miễn phí sạc",
    r"san-pham-dich-vu",
    r"huong-dan-doi-pin",
    r"van-hanh-tram-sac",
    r"dieu-khoan-dich-vu",
    r"phan-hoi-thong-tin",
    r"4-mau-xe-may-dien",
    r"pha-hoai-xam-pham",
    r"ban-do-tram-sac",
    r"cau-hoi-thuong-gap",
]


def _extract_related_models(text: str) -> list[str]:
    """Phát hiện các dòng xe hoặc dòng pin được nhắc tới trong bài viết."""
    text_upper = text.upper()
    found: set[str] = set()

    for car in CRAWLED_CAR_MODELS:
        pattern = r"\b" + re.escape(car.upper()) + r"\b"
        compressed = r"\b" + re.escape(car.upper().replace(" ", "")) + r"\b"
        if re.search(pattern, text_upper) or re.search(compressed, text_upper):
            found.add(car)

    for bike in CRAWLED_BIKE_MODELS:
        base_name = bike.split()[0].upper()
        if base_name in text_upper:
            found.add(bike)

    return sorted(found)


def _normalize_url(url: str, base: str = BASE_URL) -> str:
    """Chuẩn hóa URL tuyệt đối và loại bỏ hash fragment."""
    full = urllib.parse.urljoin(base, url)
    parsed = urllib.parse.urlparse(full)
    clean_path = parsed.path.rstrip("/")
    if not clean_path:
        clean_path = "/"
    query = f"?{parsed.query}" if parsed.query and "page=" in parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{clean_path}{query}"


def _is_vgreen_content_link(url: str) -> bool:
    """Kiểm tra đường dẫn có thuộc phạm vi V-Green cần crawl hay không."""
    parsed = urllib.parse.urlparse(url)
    if "vgreen.net" not in parsed.netloc:
        return False

    path = parsed.path.lower()
    for ext in [".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".ico", ".pdf", ".docx", ".zip"]:
        if path.endswith(ext):
            return False

    for skip in ["/cdn-cgi/", "/en", "/themes/", "/core/", "/modules/", "/edit", "/user"]:
        if skip in path:
            return False

    return path.startswith("/vi") or path.startswith("/san-pham") or path.startswith("/tin-tuc")


def is_allowed_vgreen_content(url_or_slug: str, title: str) -> bool:
    """Kiểm tra nghiêm ngặt: chỉ giữ trạm sạc, phí sạc, xe VinFast, pin/sạc xe; loại bỏ công ty, đối tác, nhà đầu tư."""
    combined = f"{url_or_slug} {title}".lower()

    # 1. Kiểm tra loại trừ trên slug và title (tránh bị dính từ khóa menu/navbar trong body)
    for pat in EXCLUDE_TOPIC_PATTERNS:
        if re.search(pat, combined, re.I):
            return False

    # 2. Kiểm tra bao hàm
    for pat in INCLUDE_TOPIC_PATTERNS:
        if re.search(pat, combined, re.I):
            return True

    return False


def extract_internal_links(html: str, current_url: str) -> list[str]:
    """Trích xuất danh sách liên kết nội bộ hợp lệ từ HTML."""
    raw_hrefs = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
    valid_links: list[str] = []
    seen: set[str] = set()

    for href in raw_hrefs:
        if href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        full_url = _normalize_url(href, current_url)
        if _is_vgreen_content_link(full_url) and full_url not in seen:
            seen.add(full_url)
            valid_links.append(full_url)

    return valid_links


def parse_vgreen_faqs(raw_content: str, url: str) -> list[dict[str, Any]]:
    """Tách riêng toàn bộ các câu hỏi thường gặp FAQ của V-GREEN thành cấu trúc chuẩn."""
    lines = [line_item.strip() for line_item in raw_content.split("\n") if line_item.strip()]
    faqs: list[dict[str, Any]] = []
    current_section = "Ô tô điện"
    current_q = None
    current_a: list[str] = []

    for line in lines:
        if line in ["Ô tô điện", "Xe máy điện"]:
            if current_q and current_a:
                ans_text = "\n".join(current_a).strip()
                faqs.append({
                    "section": current_section,
                    "question": current_q,
                    "answer": ans_text,
                })
                current_q = None
                current_a = []
            current_section = line
            continue

        if line in ["Trang chủ", "Sản phẩm dịch vụ", "Cho đối tác, khách hàng", "Tin tức", "Về V-Green", "Trạm sạc Ô tô điện", "Trạm sạc Xe máy điện", "Góp ý về chất lượng dịch vụ", "FAQs", "EN", "-->"]:
            continue

        if line.startswith(("×", "ĐĂNG KÝ ĐỐI TÁC", "Góp ý về chất lượng dịch vụ trạm sạc", "Xin chào Quý khách")):
            break

        if line.endswith("?"):
            if current_q and current_a:
                ans_text = "\n".join(current_a).strip()
                faqs.append({
                    "section": current_section,
                    "question": current_q,
                    "answer": ans_text,
                })
                current_a = []
            current_q = line
        elif current_q is not None:
            current_a.append(line)

    if current_q and current_a:
        faqs.append({
            "section": current_section,
            "question": current_q,
            "answer": "\n".join(current_a).strip(),
        })

    structured_faqs: list[dict[str, Any]] = []
    for idx, f in enumerate(faqs, start=1):
        q = f["question"]
        a = f["answer"]
        models = _extract_related_models(f"{q} {a}")
        meta = build_rag_metadata(
            doc_id=f"doc_vgreen_faq_{idx:02d}",
            doc_type="faq",
            title=q,
            domain="vgreen.net",
            source_url=url,
            category="Câu hỏi thường gặp V-GREEN",
            subcategory=f"Trạm sạc & Phí sạc {f['section']}",
            applies_to=f"Khách hàng sử dụng {f['section']} VinFast tại hệ thống trạm sạc V-GREEN",
            related_models=models,
            raw_content=f"Câu hỏi: {q}\n\nTrả lời:\n{a}",
        )
        structured_faqs.append({
            "faq_id": meta["doc_id"],
            "section": f["section"],
            "question": q,
            "answer": a,
            "metadata": meta,
        })

    return structured_faqs


def parse_vgreen_page(url: str, html: str) -> dict[str, Any] | None:
    """Bóc tách nội dung chi tiết một trang V-Green."""
    if not html or len(html) < 200:
        return None

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
    title = clean_html(h1_m.group(1)) if h1_m else ""
    if not title:
        t_m = re.search(r"<title>(.*?)</title>", html, re.I)
        title = clean_html(t_m.group(1)) if t_m else ""
    if "|" in title:
        title = title.split("|")[0].strip()

    if not title or "Truy cập bị từ chối" in title or "Page not found" in title:
        return None

    date_m = re.search(r"(\d{2}/\d{2}/\d{4})", html)
    if not date_m:
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", html)
    pub_date = date_m.group(1) if date_m else ""

    body_m = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.I)
    raw_text = ""
    if body_m:
        raw_text = clean_html(body_m.group(1), strip_nav=True)
    if len(raw_text) < 200:
        main_m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL | re.I)
        if main_m:
            raw_text = clean_html(main_m.group(1), strip_nav=True)
    if len(raw_text) < 200:
        raw_text = clean_html(html, strip_nav=True)

    if len(raw_text) < 150:
        return None

    parsed_u = urllib.parse.urlparse(url)
    slug = parsed_u.path.strip("/").replace("/", "_")
    slug = re.sub(r"^vi_", "", slug)
    if parsed_u.query:
        clean_q = re.sub(r"[^a-zA-Z0-9_\-]+", "_", parsed_u.query).strip("_")
        if clean_q:
            slug = f"{slug}_{clean_q}"
    if not slug:
        slug = "trang_chu"

    # Kiểm tra bộ lọc nội dung chặt chẽ
    if not is_allowed_vgreen_content(slug, title):
        return None

    # Xác định loại tài liệu: policy vs news vs faq
    url_lower = url.lower()
    title_lower = title.lower()

    is_faq = "cau-hoi-thuong-gap" in slug or "cau-hoi-thuong-gap" in url_lower
    is_policy = any(kw in url_lower or kw in title_lower for kw in [
        "chinh-sach", "chính sách", "dieu-khoan", "điều khoản", "quy-trinh", "quy trình",
        "huong-dan", "hướng dẫn", "phi-sac", "phí sạc", "san-pham-dich-vu", "tram-sac", "trạm sạc", "doi-pin", "đổi pin"
    ])

    if "/tin-tuc" in url_lower and not any(kw in title_lower for kw in ["chính sách", "quy trình", "hướng dẫn", "miễn phí sạc"]):
        is_policy = False

    target_category = "Chính sách V-Green" if is_policy else "Tin tức V-Green"
    doc_type = "policy" if is_policy else "news"
    subcategory = "Trạm sạc & Tủ đổi pin" if is_policy else "Phát triển hạ tầng xe điện"

    related_models = _extract_related_models(f"{title} {raw_text}")

    metadata = build_rag_metadata(
        doc_id=f"doc_vgreen_{doc_type}_{slug}",
        doc_type=doc_type,
        title=title,
        domain="vgreen.net",
        source_url=url,
        category=target_category,
        subcategory=subcategory,
        applies_to="Khách hàng sử dụng ô tô điện/xe máy điện VinFast tại trạm sạc V-GREEN",
        related_models=related_models,
        raw_content=raw_text,
        extra_fields={
            "published_date": pub_date,
            "ecosystem": "V-GREEN Global Charging Network",
        },
    )

    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    summary = paragraphs[0] if paragraphs else raw_text[:250]
    if len(summary) > 300:
        summary = summary[:297] + "..."

    return {
        "metadata": metadata,
        "is_faq": is_faq,
        "is_policy": is_policy,
        "slug": slug,
        "summary": summary,
        "published_date": pub_date,
        "raw_content": raw_text,
    }


def clean_stale_vgreen_files(vgreen_policies_dir: Path, news_articles_dir: Path) -> None:
    """Xóa các file V-Green cũ không còn thỏa mãn tiêu chí lọc mới."""
    for folder in [vgreen_policies_dir, news_articles_dir]:
        if not folder.exists():
            continue
        for p in folder.glob("vgreen_*.json"):
            # FAQ phải ở thư mục data/landing/faqs/ chứ không lưu trùng ở policies hay news
            if "cau-hoi-thuong-gap" in p.name:
                try:
                    p.unlink()
                except Exception:
                    pass
                continue

            # Đọc nội dung file để kiểm tra chính xác tiêu chí lọc
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                title = data.get("metadata", {}).get("title", "")
                slug = data.get("slug", p.stem)
                if not is_allowed_vgreen_content(slug, title):
                    p.unlink()
            except Exception:
                if not is_allowed_vgreen_content(p.stem, p.stem):
                    try:
                        p.unlink()
                    except Exception:
                        pass


def run_vgreen_crawl(max_depth: int = 2, max_pages: int = 40) -> dict[str, Any]:
    """Crawl có chọn lọc dữ liệu từ trang web V-GREEN (vgreen.net).

    - Chỉ lấy trạm sạc, phí sạc, xe VinFast, chính sách xe & pin.
    - Đưa FAQ V-Green vào data/landing/faqs/vgreen_faqs.json.
    - Loại bỏ tin tức tập đoàn, công ty, nhà đầu tư, đối tác.
    """
    print("=" * 65)
    print("⚡ BẮT ĐẦU CRAWL CÓ CHỌN LỌC HỆ SINH THÁI TRẠM SẠC & PIN V-GREEN")
    print("   Tiêu chí: Trạm sạc, phí sạc, xe VinFast, chính sách pin/sạc.")
    print("   Loại bỏ:  Tập đoàn, công ty, nhà đầu tư, đối tác, nhượng quyền.")
    print(f"   Thư mục Chính sách: {POLICIES_DIR}")
    print(f"   Thư mục FAQ:        {FAQS_DIR}")
    print(f"   Thư mục Tin tức:    {NEWS_DIR}")
    print("=" * 65)

    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    FAQS_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    vgreen_policies_dir = POLICIES_DIR / "vgreen"
    vgreen_policies_dir.mkdir(parents=True, exist_ok=True)
    news_articles_dir = NEWS_DIR / "articles"
    news_articles_dir.mkdir(parents=True, exist_ok=True)

    # Dọn dẹp các file cũ không hợp lệ
    clean_stale_vgreen_files(vgreen_policies_dir, news_articles_dir)

    full_seeds = list(SEED_URLS)
    for p in range(1, 3):
        full_seeds.append(f"https://vgreen.net/vi/tin-tuc?page={p}")

    queue: deque[tuple[str, int]] = deque([(s, 0) for s in full_seeds])
    visited: set[str] = set()

    crawled_policies: list[dict[str, Any]] = []
    crawled_news: list[dict[str, Any]] = []
    extracted_faqs: list[dict[str, Any]] = []

    while queue and len(visited) < max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        random_delay(0.6, 1.2)
        html = fetch_html(current_url)
        if not html:
            continue

        parsed_doc = parse_vgreen_page(current_url, html)
        if parsed_doc:
            slug = parsed_doc["slug"]
            # Nếu là trang FAQ -> trích xuất vào faqs/vgreen_faqs.json và không lưu trùng vào policies/ hay news/
            if parsed_doc["is_faq"]:
                faq_items = parse_vgreen_faqs(parsed_doc["raw_content"], current_url)
                if faq_items:
                    extracted_faqs.extend(faq_items)
                    vgreen_faq_file = FAQS_DIR / "vgreen_faqs.json"
                    save_json(faq_items, vgreen_faq_file)
                    print(f"   ❓ [FAQ] Đã trích xuất {len(faq_items)} câu hỏi vào: {vgreen_faq_file.name}")
                continue

            # Lưu vào policies hoặc news
            if parsed_doc["is_policy"]:
                out_path = vgreen_policies_dir / f"vgreen_policy_{slug}.json"
                save_json(parsed_doc, out_path)
                crawled_policies.append(parsed_doc)
                print(f"   📜 [POLICY] {parsed_doc['metadata']['title'][:50]}... -> {out_path.name}")
            else:
                out_path = news_articles_dir / f"vgreen_news_{slug}.json"
                save_json(parsed_doc, out_path)
                crawled_news.append(parsed_doc)
                print(f"   📰 [NEWS]   {parsed_doc['metadata']['title'][:50]}... -> {out_path.name}")

        if depth < max_depth:
            child_links = extract_internal_links(html, current_url)
            for child in child_links:
                if child not in visited:
                    queue.append((child, depth + 1))

    # Lưu tập tin tổng hợp V-Green Policies hợp lệ
    vgreen_policies_file = POLICIES_DIR / "vgreen_policies_all.json"
    save_json(crawled_policies, vgreen_policies_file)
    print(f"\n📁 Đã xuất tổng hợp chính sách V-Green: {vgreen_policies_file.name} ({len(crawled_policies)} tài liệu)")

    # Lưu tập tin tổng hợp V-Green News hợp lệ
    vgreen_news_file = NEWS_DIR / "vgreen_news_articles.json"
    save_json(crawled_news, vgreen_news_file)
    print(f"📁 Đã xuất tổng hợp tin tức V-Green: {vgreen_news_file.name} ({len(crawled_news)} bài viết)")

    report = {
        "status": "success",
        "domain": "vgreen.net",
        "crawled_at": get_current_iso_timestamp(),
        "total_visited_urls": len(visited),
        "total_faqs_collected": len(extracted_faqs),
        "total_policies_collected": len(crawled_policies),
        "total_news_collected": len(crawled_news),
        "faqs_file": "vgreen_faqs.json" if extracted_faqs else None,
        "policies_file": vgreen_policies_file.name,
        "news_file": vgreen_news_file.name,
    }
    summary_file = POLICIES_DIR / "vgreen_summary.json"
    save_json(report, summary_file)
    print(f"📁 Đã lưu báo cáo tổng kết V-Green: {summary_file.name}")

    return report


if __name__ == "__main__":
    run_vgreen_crawl()
