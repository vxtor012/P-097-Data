# Bronze → Silver Data Normalization Pipeline (IBM Docling)

> **🕒 Lần cập nhật gần nhất (Last Updated):** `2026-09-29 17:40 (GMT+7)`
> **📦 Phiên bản (Version):** `v2.0.0 (Docling Integration)`

---

## 📌 Tổng quan

Pipeline tự động hóa quá trình chuẩn hóa dữ liệu từ tầng **Bronze (Landing Raw)** sang tầng **Silver (Standardized)** trong kiến trúc Data Lakehouse sử dụng thư viện tiên tiến **IBM Docling** (`docling`). Hệ thống quét các danh mục văn bản trong `data/landing/`, áp dụng mô hình phân tích cấu trúc văn bản / OCR / layout / HTML / PDF của Docling để chuẩn hóa định dạng Markdown chất lượng cao kèm khối YAML Frontmatter metadata phong phú.

### Mục đích chính

- **Phạm vi xử lý:** Chuẩn hóa các tệp trong `faqs/`, `legal/`, `news/`, `policies/`, `specs/`.
- **Tuyệt đối KHÔNG can thiệp:** Thư mục `relational/` (dữ liệu bảng quan hệ CSV được bảo toàn tại Bronze).
- **Đầu vào (Input):**
  - Các tệp PDF trong `data/landing/legal/` (Nghị định, Thông tư quy phạm pháp luật).
  - Các tệp JSON trong `data/landing/` (faqs, news, policies, specs) gồm `metadata` và `raw_content` cào từ website.
- **Đầu ra (Output):** Các tệp Markdown (`.md`) chuẩn hóa tại `data/standardized/` với YAML Frontmatter chứa đầy đủ metadata truy vết (data provenance) phục vụ RAG / LLMOps.

---

## 🏗️ Kiến trúc Module

```text
src/data_pipeline/normalize/
├── __init__.py                 # Package init & re-exports
├── docling_converter.py        # Wrapper DoclingService (PDF, HTML, Text, JSON raw_content sang Markdown)
├── metadata_utils.py           # Trích xuất metadata & sinh YAML Frontmatter
├── processor.py                # Điều phối chuẩn hóa Bronze → Silver cho toàn bộ danh mục
└── README.md                   # Tài liệu hướng dẫn sử dụng

src/data_pipeline/
├── task2_normalize_data.py     # CLI Entrypoint chính thực thi Task 2
```

---

## 📋 YAML Frontmatter Metadata Schema

Mỗi file `.md` chuẩn hóa sinh ra có cấu trúc YAML Frontmatter ở đầu:

```yaml
---
doc_id: doc_specs_vf-3
title: Thông số kỹ thuật và tính năng xe VinFast VF 3
doc_type: vehicle_spec
category: Thông số kỹ thuật
subcategory: Mini SUV
domain: vinfastauto.com
source_url: https://vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3
applies_to: Dòng xe VF 3
related_models:
- VF 3
is_general_info: false
language: vi
pipeline_stage: silver_standardized
crawled_at: '2026-09-28T16:29:50.507830+00:00'
normalized_at: '2026-09-29T10:40:21.261890+00:00'
content_hash: a4aecaf09840002bd472ee2e95fc1ea7
char_count: 843
word_count: 135
token_estimate: 175
segment: Mini SUV
seats: 4
specifications_count: 12
---
```

---

## 🚀 Hướng dẫn Sử dụng

### Cài đặt Dependencies

```powershell
pip install docling pyyaml
```

### Chạy Pipeline Chuẩn hóa

```powershell
# Chạy với môi trường .venv đã cài docling
.\.venv\Scripts\python.exe src/data_pipeline/task2_normalize_data.py

# Chỉ định đường dẫn thư mục nguồn và đích
.\.venv\Scripts\python.exe src/data_pipeline/task2_normalize_data.py --input-dir data/landing --output-dir data/standardized

# Bật OCR cho tài liệu scan
.\.venv\Scripts\python.exe src/data_pipeline/task2_normalize_data.py --use-ocr
```

---

## 📊 Kết quả Thống kê

| Danh mục | File nguồn (Landing) | File Markdown tạo mới (Standardized) |
|----------|:-------------------:|:------------------------------------:|
| **FAQs** | 4 JSON | **415** |
| **Legal** | 14 PDF + 4 JSON | **18** |
| **News** | 51 JSON | **94** |
| **Policies** | 33 JSON | **56** |
| **Specs** | 16 JSON | **28** |
| **Relational** | 6 CSV | *Giữ nguyên tại Bronze* |
| **TỔNG CỘNG** | **116 files** | **612 Markdown files** |
