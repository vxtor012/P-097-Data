# 🚗 Data Pipeline - Task 1 & URLs Discovery

Hệ thống thu thập và quản lý danh mục nguồn dữ liệu phục vụ AI Chatbot & RAG, được thiết kế theo kiến trúc **Medallion Architecture (Bronze Layer)**.

---

## 🎯 1. Cấu trúc thư mục

```text
src/data_pipeline/
├── urls_crawler.py       # Script quét & tự động tìm kiếm danh sách URLs mở rộng -> xuất ra data/urls.csv
├── task1_crawl_data.py   # Script crawl dữ liệu thô (Raw Data) từ data/sources.csv vào data/bronze/
└── README.md             # Tài liệu kiến trúc và hướng dẫn vận hành

data/
├── urls.csv              # Danh sách tổng hợp toàn bộ URLs tìm kiếm được phân theo 8 category
├── sources.csv           # Danh sách các URLs ĐÃ KIỂM CHỨNG (schema: title, url, category)
└── bronze/               # Dữ liệu thô cào được (vinfast/ & web_scraping/)
```

---

## 🏷️ 2. Quy định 8 Nhóm Chủ Đề Cốt Lõi (`category`)

Tất cả các URL trong `data/sources.csv` và `data/urls.csv` đều sử dụng chung 8 nhãn định danh chuẩn hóa:

| Mã định danh (`category`) | Mô tả phạm vi chủ đề | Nguồn dữ liệu tiêu biểu |
| :--- | :--- | :--- |
| `gia_ca_lan_banh` | Giá niêm yết, chi phí đăng ký, thuế, biển số, dự toán | `shop.vinfastauto.com`, `xehay.vn` |
| `thong_so_ky_thuat` | Kích thước, động cơ, pin, công suất, an toàn, ADAS | `vinfastauto.com` |
| `chinh_sach_uu_dai` | Khuyến mãi đại lý, voucher, miễn giảm thuế trước bạ | `vinfastauto.com`, `luatvietnam.vn` |
| `he_thong_tram_sac` | Vị trí trạm sạc, công suất sạc, chi phí sạc/phút, đổi pin | `vgreen.net`, `vinfastauto.com` |
| `tai_chinh_tra_gop` | Lãi suất ngân hàng, gói vay, thủ tục chứng minh tài chính | `techcombank.com`, `vinfastauto.com` |
| `thu_tuc_phap_ly` | Quy trình bấm biển, đăng kiểm, nộp thuế, bảo hiểm TNDS | `baoviet.com`, `luatvietnam.vn` |
| `trai_nghiem_danh_gia` | Ưu nhược điểm từ người dùng, lỗi vặt, độ ồn, cảm giác lái | `xehay.vn`, `vnexpress.net` |
| `hau_mai_bao_duong` | Lịch bảo dưỡng, chi phí thay dầu/pin, cứu hộ 24/7 | `vinfastauto.com` |

---

## 🚀 3. Hướng dẫn sử dụng

### 3.1 Khám phá danh sách URLs mới (`urls_crawler.py`)
Script quét cả các seed URL chất lượng cao và quét động qua các feed tin tức/bài viết, tự động phân loại vào 8 category và xuất ra file `data/urls.csv` (không ghi đè `data/sources.csv`):
```bash
python src/data_pipeline/urls_crawler.py
```
*(Tùy chọn số trang quét: `python src/data_pipeline/urls_crawler.py --max-pages 5`)*

### 3.2 Thu thập dữ liệu thô vào tầng Bronze (`task1_crawl_data.py`)
Script đọc **`data/sources.csv`** (chứa danh sách URL đã kiểm chứng) cùng API/FAQ VinFast để lưu trữ dữ liệu thô vào `data/bronze/`:
- Nếu domain là `vinfastauto` -> lưu vào `data/bronze/vinfast/`
- Nếu domain ngoài -> lưu vào `data/bronze/web_scraping/raw_html/`

```bash
# Chạy toàn bộ (Relational API + FAQ HTML + Sources.csv)
python src/data_pipeline/task1_crawl_data.py --all

# Hoặc chỉ cào các bài viết trong sources.csv:
python src/data_pipeline/task1_crawl_data.py --sources
```
