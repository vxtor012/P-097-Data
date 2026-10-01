# 🥉 Bronze Layer: Raw Automotive Data Ingestion

> **Thời gian cập nhật:** `2026-10-01 05:15:23 UTC`  
> **Trạng thái:** Hoàn tất thu thập dữ liệu thô (Raw Data Layer).

---

## 📌 1. Giới thiệu tầng Bronze
Tầng **Bronze** chứa toàn bộ dữ liệu thô (raw snapshot) được thu thập từ các nguồn chính thống và kiểm chứng, bao gồm:
- **Rolling Pricing API**: Dữ liệu giá niêm yết, các phiên bản xe và ma trận dự toán chi phí lăn bánh từ VinFast API.
- **FAQ Accordion HTML**: Toàn văn trang câu hỏi thường gặp chính thức từ VinFast.
- **Chương trình ưu đãi**: Các bài viết thông báo khuyến mại, lãi suất, VinClub dạng raw HTML.
- **Web Scraping đã kiểm duyệt**: Đánh giá trải nghiệm thực tế từ XeHay và gói vay mua xe ngân hàng từ Techcombank.

Dữ liệu tại tầng này được bảo toàn nguyên vẹn bản quyền và cấu trúc gốc trước khi đưa vào chuẩn hóa tại tầng Silver.

---

## 📊 2. Thống kê tệp dữ liệu thô

| Phân loại | Đường dẫn tệp / thư mục | Số lượng / Dung lượng | Mô tả nội dung |
| :--- | :--- | :---: | :--- |
| **Relational Pricing** | `vinfast/relational/vinfast_rolling_raw_snapshot.json` | 501.6 KB | Snapshot API danh mục xe, màu sắc, pin và giá lăn bánh 63 tỉnh |
| **FAQ Accordion** | `vinfast/faq/vinfast_faq_raw.html` | 1.3 MB | 400 câu hỏi - đáp dạng accordion HTML |
| **EV Promos Articles** | `vinfast/articles/` | 18 tệp HTML (4.5 MB) | Tin tức chương trình kích cầu, bảo hiểm, sạc pin |
| **Web Scraping HTML** | `web_scraping/raw_html/` | 28 tệp HTML (4.8 MB) | Bài viết trải nghiệm xe & tư vấn vay ngân hàng |
| **Web Manifest** | `web_scraping/web_scraping_manifest.json` | Index JSON | Bảng kê nguồn web đã cào |

### 📑 Tài liệu PDF đính kèm (`dataset/pdf/`)
- **Brochure thông số kỹ thuật (`thong_so_ky_thuat/`)**: 10 tệp PDF (VF 3, VF 5, VF 6, VF 7, VF 8, VF 9,...)
- **Chính sách bán hàng & VinClub (`chinh_sach_uu_dai/`)**: 14 tệp PDF thông báo ưu đãi
- **Văn bản quy phạm pháp lý (`thu_tuc_phap_ly/`)**: 11 tệp PDF Nghị định & Thông tư

---

## 🔄 3. Cách thức tái tạo dữ liệu (Re-crawl)
Chạy lệnh CLI để cào mới dữ liệu Bronze:
```bash
# Cào toàn bộ nguồn
python -m src.pipeline crawl --mode all

# Hoặc chỉ cào API giá xe
python -m src.pipeline crawl --mode api

# Hoặc chỉ cào FAQ
python -m src.pipeline crawl --mode faq
```
