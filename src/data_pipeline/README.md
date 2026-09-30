# 🚗 Data Pipeline - Task 1 & URLs Discovery

Hệ thống thu thập và quản lý danh mục nguồn dữ liệu phục vụ AI Chatbot & RAG, được thiết kế theo kiến trúc **Medallion Architecture (Bronze Layer)** và phân bổ tài liệu có tổ chức.

---

## 🎯 1. Cấu trúc thư mục

```text
src/data_pipeline/
├── urls_crawler.py       # Script quét & tự động tìm kiếm danh sách URLs mở rộng -> xuất ra data/urls.csv
├── task1_crawl_data.py   # Script crawl dữ liệu thô (Raw Data) từ data/sources.csv vào data/bronze/ & data/pdf/
└── README.md             # Tài liệu kiến trúc và hướng dẫn vận hành

data/
├── urls.csv              # Danh sách URLs được crawler tổng hợp và phân loại
├── sources.csv           # Danh sách các URLs ĐÃ KIỂM CHỨNG (schema: title, url, category)
├── bronze/               # Dữ liệu thô cào được (vinfast/ & web_scraping/)
│   ├── vinfast/
│   │   ├── relational/   # Snapshot JSON API giá niêm yết & dự toán chi phí lăn bánh chính xác
│   │   ├── faq/          # HTML thô trang FAQ chính thức
│   │   ├── articles/     # HTML thô các bài viết từ vinfastauto.com
│   │   └── vinfast_sources_manifest.json
│   └── web_scraping/
│       ├── raw_html/     # HTML thô các bài viết ngoài (Techcombank, Bảo Việt, XeHay...)
│       └── web_scraping_manifest.json
└── pdf/                  # Thư mục lưu trữ tài liệu PDF được tổ chức theo chuyên mục
    ├── thu_tuc_phap_ly/   # Các văn bản luật, nghị định, thông tư
    ├── thong_so_ky_thuat/ # Brochure PDF thông số chi tiết các dòng xe từ VinFast
    ├── chinh_sach_uu_dai/ # Tài liệu PDF chính sách & chương trình ưu đãi
    └── pdf_manifest.json # Quản lý danh mục toàn bộ file PDF
```

---

## 🏷️ 2. Quy định Nhóm Chủ Đề Cốt Lõi & Nguyên Tắc Nguồn Dữ Liệu

| Mã định danh (`category`) | Phạm vi chủ đề                                          | Nguyên tắc nguồn dữ liệu                                                                                                         |
| :----------------------------- | :---------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------ |
| `gia_ca_lan_banh`            | Bảng giá niêm yết & chi phí lăn bánh                 | **CHỈ LẤY TỪ API VINFAST** (`data/bronze/vinfast/relational/`), không crawl web ngoài để tránh xung đột thông tin. |
| `thong_so_ky_thuat`          | Kích thước, động cơ, pin, an toàn, ADAS              | **CHỈ LẤY TỪ VINFAST** (`vinfastauto.com`) & tải Brochure PDF chính hãng về `data/pdf/thong_so_ky_thuat/`.           |
| `chinh_sach_uu_dai`          | Khuyến mại, ưu đãi, voucher, VinClub                   | Lấy từ trang`vinfastauto.com/vn_vi/uu-dai` & các file PDF chính sách về `data/pdf/chinh_sach_uu_dai/`.                      |
| `he_thong_tram_sac`          | Vị trí trạm sạc, công suất, chi phí, đổi pin       | Hệ sinh thái V-GREEN & VinFast (`vgreen.net`, `vinfastauto.com`).                                                               |
| `tai_chinh_tra_gop`          | Lãi suất ngân hàng, gói vay, thủ tục trả góp       | Ngân hàng đối tác Techcombank, VinFast.                                                                                          |
| `thu_tuc_phap_ly`            | Quy trình bấm biển định danh, đăng kiểm, bảo hiểm | Văn bản PDF trong`data/pdf/thu_tuc_phap_ly/` và bảo hiểm Bảo Việt.                                                           |
| `trai_nghiem_danh_gia`       | Trải nghiệm người dùng, ưu nhược điểm, review     | Chuyên trang xe uy tín (`xehay.vn`, `vnexpress.net`).                                                                           |
| `hau_mai_bao_duong`          | Lịch bảo dưỡng, chi phí pin, cứu hộ 24/7             | Chính hãng VinFast (`vinfastauto.com`).                                                                                           |

---

## 🚀 3. Hướng dẫn sử dụng

### 3.1 Khám phá danh sách URLs mới (`urls_crawler.py`)

Script quét các seed URL chất lượng cao và quét động qua các feed tin tức VinFast/V-Green, tự động loại trừ giá lăn bánh trùng lặp và chỉ chấp nhận thông số kỹ thuật từ VinFast:

```bash
python src/data_pipeline/urls_crawler.py
```

### 3.2 Thu thập dữ liệu thô vào tầng Bronze & PDF (`task1_crawl_data.py`)

Script thực hiện đầy đủ quy trình thu thập dữ liệu thô:

- Dữ liệu quan hệ (bảng giá & lăn bánh) từ API VinFast vào `data/bronze/vinfast/relational/`
- HTML FAQ chính thức vào `data/bronze/vinfast/faq/`
- Tài liệu Brochure & Chính sách PDF vào `data/pdf/thong_so_ky_thuat/` và `data/pdf/chinh_sach_uu_dai/`
- Bài viết từ `data/sources.csv` phân loại vào `vinfast/articles/` hoặc `web_scraping/raw_html/`

```bash
# Chạy toàn bộ (Relational API + FAQ + PDFs + Sources.csv):
python src/data_pipeline/task1_crawl_data.py --all

# Hoặc chỉ cập nhật tài liệu PDF:
python src/data_pipeline/task1_crawl_data.py --pdf

# Hoặc chỉ cào các bài viết trong sources.csv:
python src/data_pipeline/task1_crawl_data.py --sources
```
