# VinFast Auto Data Pipeline

> **🕒 Lần cập nhật script gần nhất (Last Updated):** `2026-09-28 23:30 (GMT+7)`
> **📦 Phiên bản (Version):** `v1.3.0`
> **⏱️ Chu kỳ kiểm tra khuyến nghị:** 7 – 14 ngày (hoặc kích hoạt chạy lại khi VinFast công bố bảng giá/chính sách/dòng xe mới để tránh outdate dữ liệu)

---

## 📌 Tổng quan mục đích & Phạm vi thu thập

Hệ thống pipeline được xây dựng để thu thập toàn diện từ hệ sinh thái [VinFast Auto Việt Nam](https://vinfastauto.com/vn_vi) và [VinFast Shop](https://shop.vinfastauto.com/vn_vi/chi-phi-lan-banh), phục vụ xây dựng kho tri thức cho hệ thống AI RAG Pipeline:

1. **Bảng giá & Dự toán lăn bánh (Relational Tabular CSV)**:

   - Bảng giá niêm yết, giá kèm pin / thuê pin cho toàn bộ các dòng ô tô và xe máy điện.
   - Toàn bộ danh mục tùy chọn màu sắc xe & biểu phí màu cơ bản / nâng cao.
   - Biểu phí đăng ký biển số và thuế trước bạ cho 63 tỉnh/thành phố (KV1, KV2, KV3).
   - 8 chương trình ưu đãi giảm giá (VinClub, O2O, Chuyển đổi xanh...).
   - Ma trận dự toán chi phí lăn bánh hoàn chỉnh cho tất cả các dòng xe và tỉnh thành.
2. **Câu hỏi thường gặp (FAQs JSON)**:

   - 400 câu hỏi & giải đáp chi tiết từ VinFast phân cấp theo danh mục: Bán hàng, Hậu mãi, Sạc pin, Trạm sạc, Trợ lý ảo...
   - Đã được làm sạch, gắn thẻ phân loại và liên kết với các dòng xe cụ thể.
3. **Chính sách sản phẩm, hậu mãi & Pháp lý (Policies & Legal JSON)**:

   - Chính sách bảo hành chính hãng ô tô (10 năm / 200.000 km) và xe máy điện.
   - Dịch vụ cứu hộ 24/7 toàn quốc & cứu hộ sạc pin khẩn cấp.
   - Chính sách thuê pin, đổi trả và thiết bị sạc tại nhà.
   - Quy trình và lịch bảo dưỡng định kỳ, dịch vụ sửa chữa chính hãng.
   - Hợp đồng mua bán xe, điều khoản pháp lý và chính sách bảo mật quyền riêng tư.
4. **Tin tức & Thông cáo sản phẩm mới (News JSON)**:

   - 24 bài viết tin tức, thông cáo ra mắt xe (VF Wild, VF MPV 7, VF 8 thế hệ mới, Evo Grand...).
   - Chương trình nâng cấp phần cứng/phần mềm (Apple CarPlay/Android Auto cho VF 3...).
   - Báo cáo tăng trưởng, hợp tác mạng lưới đại lý và chiến dịch chuyển đổi xanh.
5. **Thông số kỹ thuật chi tiết (Vehicle Specs JSON)**:

   - Bảng thông số kỹ thuật chi tiết (Kích thước, Động cơ, Pin, Quãng đường NEDC, Sạc nhanh, Chỗ ngồi, Túi khí, ADAS) của 14 dòng ô tô: **VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 8 The All New, VF 9, VF MPV 7, VF Wild, Limo Green, Herio Green, Minio Green, EC Van**.

---

## 🛡️ Cơ chế chống chặn Bot & Rate Limiting

Để bảo đảm quá trình crawl an toàn, ổn định và không làm quá tải máy chủ nguồn:

1. **Randomized Polite Delay (`random_delay`)**:
   - Tự động tạm dừng ngẫu nhiên từ `1.0s` đến `2.2s` giữa các lượt gửi HTTP request liên tiếp.
   - Giúp mô phỏng hành vi duyệt web tự nhiên của người dùng thật, ngăn ngừa triệt để các mã lỗi HTTP `429 Too Many Requests` hoặc bị tạm khóa IP.
2. **Cơ chế Fallback Cloudflare hai tầng**:
   - `urllib.request` kèm headers trình duyệt chuẩn (`User-Agent`, `Accept-Language`, `Referer`).
   - Tự động fallback sang `curl.exe` tích hợp sẵn trên hệ điều hành khi phát hiện máy chủ kích hoạt kiểm tra chữ ký TLS (Cloudflare JA3 Fingerprint).

---

## 🧩 Chuẩn bị Metadata cho RAG Chunking (Landing Raw Stage)

Mọi tập tin JSON đầu ra trong `data/landing/` đều được trang bị đối tượng chuẩn hóa `metadata` nhằm chuẩn bị tốt nhất cho giai đoạn tiếp theo (Phase 2: RAG Chunking, Embeddings & Vector Indexing), trong khi vẫn giữ nguyên tính toàn vẹn của văn bản gốc thô (`raw_content`):

```json
{
  "metadata": {
    "doc_id": "doc_news_vinfast-chinh-thuc-nhan-dat-coc-vf-mpv-7-tai-an-do",
    "doc_type": "news",
    "title": "VINFAST CHÍNH THỨC NHẬN ĐẶT CỌC VF MPV 7 TẠI ẤN ĐỘ",
    "domain": "vinfastauto.com",
    "source_url": "https://vinfastauto.com/vn_vi/vinfast-chinh-thuc-nhan-dat-coc-vf-mpv-7-tai-an-do",
    "language": "vi",
    "category": "Tin tức",
    "subcategory": "Ô tô điện",
    "applies_to": "Khách hàng quan tâm ô tô điện & hệ sinh thái VinFast",
    "related_models": ["VF 6", "VF 7", "VF MPV 7"],
    "is_general_info": false,
    "pipeline_stage": "landing_raw",
    "crawled_at": "2026-09-28T16:29:05.431743+00:00",
    "content_hash": "917b0ebf4fdb57480cf1fb58fc98de28",
    "char_count": 3908,
    "word_count": 852,
    "published_date": "02/04/2026"
  },
  "summary": "...",
  "published_date": "02/04/2026",
  "raw_content": "..."
}
```

### Ý nghĩa các trường Metadata:

- `doc_id`: Mã định danh duy nhất của tài liệu gốc, dùng để tham chiếu ngược từ các chunk văn bản sau này.
- `doc_type`: Phân loại tài liệu (`faq`, `policy`, `legal`, `news`, `vehicle_spec`), hỗ trợ metadata filtering trong RAG.
- `related_models`: Danh sách các dòng xe được đề cập (ví dụ: `["VF 3"]`), cho phép LLM lọc đúng ngữ cảnh xe mà người dùng đang hỏi.
- `content_hash`: Mã băm MD5 của nội dung, phục vụ việc kiểm tra trùng lặp (deduplication) và phát hiện khi nào dữ liệu nguồn bị thay đổi.
- `char_count` & `word_count`: Hỗ trợ thuật toán chunker tự động tính toán kích thước cửa sổ chia đoạn (chunk window size) tối ưu.
- `pipeline_stage`: Đánh dấu rõ ràng đây là dữ liệu thô tầng Landing (`landing_raw`), chưa qua xử lý làm sạch hay chia đoạn.

---

## 📂 Cấu trúc mã nguồn & Giới hạn số dòng file

Mã nguồn tuân thủ nghiêm ngặt nguyên tắc Clean Architecture và **mỗi file Python không vượt quá 600 dòng**:

```text
src/data_pipeline/
├── task1_vinfast_auto_crawl_data.py   # Task 1 Entrypoint chính (Crawl Landing Data) (~250 dòng)
├── task2_normalize_data.py            # Task 2 Entrypoint chính (Normalize Bronze → Silver) (~165 dòng)
├── README.md                          # Tài liệu kỹ thuật chi tiết (file này)
├── sources.csv                        # Danh sách nguồn tham chiếu bổ sung (Techcombank, Bảo Việt, XeHay...)
├── crawlers/                          # Task 1: Gói các module crawler chuyên biệt
│   ├── __init__.py                    # Package init & re-export (22 dòng)
│   ├── crawler_utils.py               # Tiện ích HTTP, delay, hash & RAG metadata (242 dòng)
│   ├── relational_crawler.py          # Bóc tách bảng giá & dự toán lăn bánh CSV (VinFast duy nhất) (502 dòng)
│   ├── faq_crawler.py                 # Bóc tách 400 FAQ & phân cấp danh mục (185 dòng)
│   ├── policy_crawler.py              # Bóc tách chính sách dịch vụ & pháp lý VinFast (282 dòng)
│   ├── news_crawler.py                # Bóc tách tin tức & thông cáo sản phẩm VinFast (241 dòng)
│   ├── specs_crawler.py               # Bóc tách thông số kỹ thuật 14 dòng xe VinFast (293 dòng)
│   ├── vgreen_crawler.py              # Crawl đa cấp V-GREEN (trạm sạc, đổi pin, chính sách, tin tức) (~340 dòng)
│   └── external_sources_crawler.py    # Crawl các bài viết từ source.csv / sources.csv (~260 dòng)
└── normalize/                         # Task 2: Module chi tiết Bronze → Silver Data Normalization
    ├── __init__.py                    # Package init & re-export (~50 dòng)
    ├── normalize_to_silver.py         # Pipeline Orchestrator logic (~450 dòng)
    ├── text_cleaner.py                # Bộ làm sạch văn bản 9 bước (Unicode NFC, noise, dedup) (~250 dòng)
    ├── metadata_extractor.py          # Trích xuất metadata phong phú (regex VN, dates, lineage) (~300 dòng)
    ├── file_extractors.py             # Trích xuất đa định dạng: PDF (PyMuPDF), JSON, CSV (~280 dòng)
    └── README.md                      # Tài liệu kỹ thuật chi tiết pipeline normalize
```

---

## 📂 Thư mục dữ liệu đầu ra (`data/landing/`)

> [!IMPORTANT]
> **Quy tắc phân vùng dữ liệu nghiêm ngặt:**
>
> - `data/landing/relational/` **CHỈ** được phép lưu trữ dữ liệu bảng giá & chi phí lăn bánh chính thức từ **VinFast Auto**.
> - Toàn bộ dữ liệu mở rộng từ **V-GREEN** và các nguồn ngoài lề (**source.csv / sources.csv**) **CHỈ** được phép phân bổ vào `data/landing/policies/` hoặc `data/landing/news/`.

```text
data/landing/
├── relational/                        # 6 CSV: bảng giá, màu xe, biểu phí, khuyến mãi, lăn bánh (CHỈ VINFAST AUTO)
├── faqs/                              # 3 JSON: vinfast_faqs.json (400 câu), phân cấp & tổng quan
├── policies/                          # Chính sách bảo hành, pin, trạm sạc, hợp đồng, tài chính & bảo hiểm:
│   ├── vgreen/                        # 36 JSON chi tiết chính sách, quy chế, đối tác, tài liệu trạm sạc V-GREEN
│   ├── external/                      # 7 JSON chính sách lãi suất vay (Techcombank) & bảo hiểm (Bảo Việt)
│   ├── vgreen_policies_all.json       # Tổng hợp toàn bộ chính sách V-GREEN
│   ├── external_sources_policies.json # Tổng hợp toàn bộ chính sách từ source.csv
│   └── vinfast_policies_all.json      # Tổng hợp toàn bộ chính sách VinFast
├── legal/                             # 3 JSON: điều khoản pháp lý & chính sách quyền riêng tư VinFast
├── news/                              # Tin tức, thông cáo báo chí, bài viết đánh giá thị trường:
│   ├── articles/                      # Hơn 58 bài viết chi tiết (VinFast + V-GREEN + XeHay)
│   ├── vgreen_news_articles.json      # Tổng hợp bài viết tin tức & hợp tác V-GREEN
│   ├── external_sources_news.json     # Tổng hợp bài viết tin tức từ source.csv
│   └── vinfast_news_articles.json     # Tổng hợp tin tức VinFast Auto
└── specs/                             # 16 JSON: 14 dòng xe (VF 2 -> VF Wild, Limo Green...) + tổng hợp
```

---

## 🚀 Hướng dẫn thực thi

Từ thư mục gốc dự án:

```powershell
# Chạy toàn bộ pipeline (Relational CSVs + FAQs + Policies + News + Specs + V-Green + Sources CSV):
python src/data_pipeline/task1_vinfast_auto_crawl_data.py

# Hoặc kích hoạt từng tác vụ độc lập:
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --relational
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --faqs
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --policies
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --news
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --specs
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --vgreen
python src/data_pipeline/task1_vinfast_auto_crawl_data.py --sources
```

---

## 📝 Lịch sử cập nhật (Changelog)

|   Phiên bản   |        Thời gian cập nhật        | Nội dung cải tiến chính                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| :--------------: | :---------------------------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **v1.3.0** | **2026-09-29 11:55 (GMT+7)** | - Tích hợp**V-GREEN Multi-level Crawler** (`vgreen_crawler.py`): bóc tách đa cấp toàn diện dữ liệu trạm sạc, tủ đổi pin, quy chế, đối tác, tài liệu vận hành và tin tức từ https://vgreen.net/vi.- Tích hợp **External Sources Crawler** (`external_sources_crawler.py`): thu thập các liên kết độc lập từ `source.csv` / `sources.csv` (lãi suất vay ngân hàng Techcombank, bảo hiểm xe Bảo Việt, đánh giá XeHay).- Thiết lập cơ chế cách ly dữ liệu: bảng `relational` chỉ chứa dữ liệu VinFast Auto; toàn bộ dữ liệu V-GREEN và bên ngoài được phân loại độc quyền vào `policies` hoặc `news`. |
| **v1.2.0** |      2026-09-28 23:30 (GMT+7)      | - Bổ sung cơ chế**random polite delay (1.0s – 2.2s)** giữa các HTTP request để chống bot detection.- Chuẩn hóa **RAG Metadata Schema** cho 100% file JSON tầng landing (doc_id, doc_type, hash, char/word count, related_models).- Thêm trường theo dõi ngày giờ cập nhật trong README để kiểm soát độ mới (data freshness).                                                                                                                                                                                                                                                                                                                                     |
| **v1.1.0** |      2026-09-28 23:05 (GMT+7)      | - Mở rộng thu thập phi cấu trúc: FAQs (400 câu), Chính sách, Pháp lý, Tin tức & Specs 14 dòng ô tô.- Tái cấu trúc module hóa dưới thư mục`crawlers/` (mỗi file < 600 dòng).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **v1.0.0** |      2026-09-28 15:40 (GMT+7)      | - Khởi tạo pipeline Task 1: Crawl dữ liệu bảng giá quan hệ và dự toán lăn bánh ra 6 file CSV.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
