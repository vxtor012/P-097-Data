# Bronze → Silver Data Normalization Pipeline

> **🕒 Lần cập nhật gần nhất (Last Updated):** `2026-09-29 14:30 (GMT+7)`
> **📦 Phiên bản (Version):** `v1.0.0`

---

## 📌 Tổng quan

Pipeline tự động hóa quá trình chuẩn hóa dữ liệu từ tầng **Bronze (Landing Raw)** sang tầng **Silver (Standardized)** trong kiến trúc Data Lakehouse. Hệ thống quét toàn bộ thư mục `data/landing/`, trích xuất nội dung từ nhiều định dạng file (PDF, JSON, CSV), thực hiện làm sạch chuyên sâu và xuất ra các file Markdown (`.md`) kèm YAML Frontmatter metadata phong phú.

### Mục đích chính

- **Phạm vi xử lý:** CHỈ chuẩn hóa các tệp trong `faqs/`, `legal/`, `news/`, `policies/`, `specs/`.
- **Tuyệt đối KHÔNG động:** Thư mục `relational/` (giữ nguyên dữ liệu bảng quan hệ CSV tại Bronze).
- **Input:** Các file PDF, JSON trong `data/landing/` thuộc 5 danh mục trên.
- **Output:** File `.md` chuẩn hóa trong `data/standardized/` (giữ nguyên cấu trúc thư mục con).
- **Ứng dụng:** Phục vụ RAG Metadata Filtering, Chunking & Vector Indexing trong pipeline AI.

---

## 🏗️ Kiến trúc Module

```text
src/data_pipeline/normalize/
├── __init__.py                 # Package init
├── normalize_to_silver.py      # Entrypoint chính (CLI + Orchestrator)
├── text_cleaner.py             # Bộ công cụ làm sạch & chuẩn hóa văn bản
├── metadata_extractor.py       # Trích xuất metadata phong phú cho YAML Frontmatter
└── file_extractors.py          # Bộ trích xuất nội dung đa định dạng (PDF/JSON/CSV)

tests/test_data_pipeline/
└── test_normalize_pipeline.py  # Unit tests (27+ test classes, 50+ test cases)
```

---

## 📋 YAML Frontmatter Metadata Schema

Mỗi file `.md` sinh ra sẽ có khối YAML Frontmatter chứa các trường sau:

### 1. Thông tin Định danh & Truy vết (Data Lineage)

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `doc_id` | `string` | UUIDv4 prefix + slug tên file |
| `file_sha256` | `string` | SHA-256 hash file gốc (dedup & integrity check) |
| `source_filename` | `string` | Tên file gốc |
| `source_relative_path` | `string` | Đường dẫn tương đối từ `data/landing/` |
| `file_size_bytes` | `int` | Kích thước file gốc (bytes) |
| `file_created_time` | `ISO 8601` | Ngày giờ tạo file (hệ thống) |
| `file_modified_time` | `ISO 8601` | Ngày giờ sửa đổi gần nhất |
| `processed_at` | `ISO 8601` | Timestamp tại thời điểm normalize |

### 2. Thuộc tính Văn bản (Document Attributes)

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `document_code` | `string \| null` | Số hiệu văn bản (e.g. `109/2024/NĐ-CP`) |
| `document_title` | `string` | Tiêu đề chính xác (từ PDF metadata hoặc heuristic) |
| `issuing_authority` | `string \| null` | Cơ quan ban hành (e.g. `CHÍNH PHỦ`, `BỘ TÀI CHÍNH`) |
| `effective_or_published_date` | `YYYY-MM-DD \| null` | Ngày ban hành / ngày ký |
| `fallback_timestamp` | `ISO 8601 \| null` | Ngày từ PDF metadata hoặc file mtime (nếu không có ngày chính thức) |
| `document_type` | `string` | Loại tài liệu: `legal_document`, `policy`, `faq`, `news`, `technical_manual`, `relational_data` |

### 3. Thông số Kỹ thuật & RAG Context

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `total_pages` | `int \| null` | Tổng số trang (chỉ PDF) |
| `language` | `string` | Ngôn ngữ chính (`vi` hoặc `en`) |
| `char_count` | `int` | Tổng ký tự sau normalize |
| `word_count` | `int` | Tổng từ sau normalize |
| `estimated_tokens` | `int` | Token ước tính (~char/3.8 cho tiếng Việt) |
| `has_tables` | `bool` | Có chứa bảng biểu hay không |
| `pipeline_stage` | `string` | Luôn = `silver_normalized` |

---

## 🔧 Quy trình Làm sạch (Text Normalization Pipeline)

Pipeline làm sạch 9 bước tuần tự:

1. **Unicode NFC** — Chuẩn hóa dựng sẵn cho tiếng Việt
2. **Strip Invisible** — Loại bỏ zero-width space, BOM, control chars
3. **Smart Quotes → ASCII** — `""` → `""`, `''` → `''`
4. **Dashes → Hyphen** — `—`, `–` → `-`
5. **Remove Noise** — Số trang, URL footer, watermark, timestamp crawl
6. **Remove Repeated Headers** — Quốc hiệu, tiêu ngữ lặp lại
7. **Heal Broken Lines** — Nối dòng bị ngắt giữa câu do PDF
8. **Deduplicate** — Loại bỏ đoạn văn trùng lặp liên tiếp
9. **Normalize Whitespace** — Chuẩn hóa space, tối đa 2 newline liên tiếp

---

## 🚀 Hướng dẫn Sử dụng

### Cài đặt Dependencies

```bash
pip install pymupdf pyyaml tqdm
```

### Chạy Pipeline

```powershell
# Chạy toàn bộ pipeline với cấu hình mặc định
python src/data_pipeline/normalize/normalize_to_silver.py

# Chỉ định thư mục input/output
python src/data_pipeline/normalize/normalize_to_silver.py --input-dir data/landing --output-dir data/standardized

# Ghi đè tất cả file đã tồn tại
python src/data_pipeline/normalize/normalize_to_silver.py --overwrite

# Chỉ định file log lỗi
python src/data_pipeline/normalize/normalize_to_silver.py --log-file my_errors.log
```

### Cờ CLI

| Cờ | Mặc định | Mô tả |
|----|----------|-------|
| `--input-dir` | `data/landing` | Thư mục chứa dữ liệu Bronze |
| `--output-dir` | `data/standardized` | Thư mục xuất dữ liệu Silver |
| `--overwrite` | `False` | Ghi đè tất cả (mặc định: bỏ qua nếu hash không đổi) |
| `--log-file` | `normalize_errors.log` | File ghi log các file lỗi |

### Cơ chế Incremental Processing

Khi `--overwrite` **không** được bật (mặc định):
- Pipeline tính SHA-256 hash cho mỗi file input
- So sánh với cache (`.normalize_cache.json` trong thư mục output)
- **Bỏ qua** file nếu hash không đổi VÀ file output đã tồn tại
- Tiết kiệm tài nguyên khi chạy lại pipeline định kỳ

---

## 🧪 Kiểm thử

```bash
# Chạy toàn bộ test suite
python -m pytest tests/test_data_pipeline/test_normalize_pipeline.py -v

# Chạy ruff lint
ruff check src/data_pipeline/normalize/
```

---

## 📂 Cấu trúc Dữ liệu Đầu ra

```text
data/standardized/
├── legal/
│   ├── Nghị định 109_2024_NĐ-CP [...].md
│   ├── Nghị định 10_2022 [...].md
│   └── ...
├── faqs/
│   ├── vinfast_faqs.md
│   └── ...
├── policies/
│   ├── vgreen/
│   │   └── *.md
│   ├── external/
│   │   └── *.md
│   └── vinfast_*.md
├── news/
│   ├── articles/
│   │   └── *.md
│   └── vinfast_news_articles.md
├── specs/
│   ├── vf-3_specs.md
│   └── ...
├── relational/
│   ├── vinfast_car_editions_pricing.md
│   └── ...
├── .normalize_cache.json    # SHA-256 cache cho incremental processing
└── .normalize_stats.json    # Thống kê kết quả pipeline run gần nhất
```

---

## 📝 Dependencies

| Package | Version | Mục đích |
|---------|---------|----------|
| `pymupdf` | ≥ 1.24.0 | Trích xuất nội dung & bảng biểu từ PDF (tốc độ cao) |
| `pyyaml` | ≥ 6.0 | Sinh YAML Frontmatter |
| `tqdm` | ≥ 4.66.0 | Thanh tiến trình khi xử lý file |

---

## 📝 Changelog

| Phiên bản | Thời gian | Nội dung |
|:---------:|:---------:|:---------|
| **v1.0.0** | **2026-09-29 14:30 (GMT+7)** | Khởi tạo pipeline Bronze → Silver: trích xuất đa định dạng (PDF/JSON/CSV), làm sạch 9 bước, YAML Frontmatter metadata phong phú, incremental processing, error logging, CLI đầy đủ. |
