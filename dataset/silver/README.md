# 🥈 Silver Layer: Normalized & Structured Pre-RAG Data

> **Thời gian cập nhật:** `2026-10-01 05:15:33 UTC`  
> **Thời gian thực thi:** `9.72s`  
> **Trạng thái:** Chuẩn hóa hoàn tất từ 113 bản ghi Bronze.

---

## 📌 1. Giới thiệu tầng Silver
Tầng **Silver** chuyển hóa dữ liệu thô từ Bronze sang dữ liệu văn bản sạch có cấu trúc phục vụ Pre-RAG:
1. **Chuẩn hóa Tiếng Việt**: Unicode NFC toàn diện, chuyển đổi dấu thanh chuẩn (`hoà` $	o$ `hòa`, `thuỷ` $	o$ `thủy`).
2. **Làm sạch nhiễu & Boilerplate**: Loại bỏ thẻ HTML thừa, script, watermark in ấn web và các dòng `about:blank`.
3. **Tách câu thông minh**: Bảo toàn các từ viết tắt tiếng Việt (`TP.HCM`, `VNĐ`, `TS.`, `km/h`, tiền tệ thập phân `260.000.000 VNĐ`).
4. **Hierarchical Chunking**: Phân đoạn ngữ cảnh theo cấp độ tiêu đề `#`, `##`, `###`, gắn breadcrumb context (`[VF 8 > Chính sách pin]`) và bảo toàn toàn vẹn bảng biểu Markdown.

---

## 📊 2. Thống kê tệp dữ liệu tầng Silver

| Tệp dữ liệu | Số lượng bản ghi | Dung lượng | Mục đích & Mô tả |
| :--- | :---: | :---: | :--- |
| **`silver_documents.jsonl`** | **113 docs** | 3.1 MB | Tài liệu toàn văn đã làm sạch, đạt chuẩn chất lượng tiếng Việt |
| **`silver_chunks.jsonl`** | **2,801 chunks** | 4.8 MB | Chunks ngữ cảnh phân cấp chèn sẵn breadcrumbs |
| **`silver_faq.jsonl`** | **400 Q&A** | 483.1 KB | 400 câu hỏi - đáp chuẩn từ FAQ VinFast |
| **`silver_vehicles.jsonl`** | **27 xe** | 32.8 KB | Danh mục 27 phiên bản xe, thông số & giá |
| **`silver_report.json`** | 1 báo cáo | 868 B | Báo cáo chi tiết chỉ số kiểm toán tầng Silver |

### 🗄️ Bảng dữ liệu quan hệ (`rdb_schema/`)
Các bảng CSV được cấu trúc hóa từ API giá xe để phục vụ truy vấn số liệu chính xác:

| Tên bảng CSV | Số dòng dữ liệu | Dung lượng |
| :--- | :---: | :---: |
| `cars_catalog.csv` | 27 dòng | 2.9 KB |
| `fee_rules.csv` | 6 dòng | 1.1 KB |
| `provinces.csv` | 63 dòng | 2.5 KB |
| `rolling_cost_matrix.csv` | 276 dòng | 42.0 KB |
| `trims_pricing.csv` | 46 dòng | 8.4 KB |

---

## 📈 3. Chỉ số chất lượng (Quality Metrics)
- **Điểm chất lượng tiếng Việt trung bình (Quality Score)**: `0.952` / 1.000
- **Số token ước tính trung bình mỗi chunk**: `118.9` tokens
- **Kích thước chunk cấu hình**: `512` ký tự (Overlap: `80` ký tự)

---

## 💻 4. Ví dụ đọc dữ liệu bằng Python
```python
import json

# Đọc mẫu chunk từ silver_chunks.jsonl
with open("dataset/silver/silver_chunks.jsonl", "r", encoding="utf-8") as f:
    first_chunk = json.loads(f.readline())
    print("Chunk ID:", first_chunk["chunk_id"])
    print("Breadcrumb:", first_chunk["heading_context"])
    print("Content preview:", first_chunk["content"][:200])
```
