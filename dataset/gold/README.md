# 🥇 Gold Layer: Curated Car Purchasing Consultation Knowledge

> **Thời gian cập nhật:** `2026-10-01 05:15:36 UTC`  
> **Thời gian thực thi:** `2.91s`  
> **Miền tri thức:** Tư vấn mua bán xe & pháp lý sở hữu ô tô điện (Car Purchasing Consultation)

---

## 📌 1. Giới thiệu tầng Gold
Tầng **Gold** là kho tri thức tinh hoa đã trải qua quy trình 2 bước kiểm định khắt khe:
1. **Lọc nội dung không liên quan (Domain Filter)**: Loại bỏ triệt để **797 chunks** về luật giao thông đường bộ chung, xử phạt vi phạm (Nghị định 100/2019, 123/2021), thủ tục hoán cải khung sườn cơ khí và các quy định hành chính không phục vụ người mua xe.
2. **Khử trùng lặp nâng cao (Chunk Deduplication)**: Loại bỏ **133 chunks dư thừa** (gồm **100 chunks** trùng lặp 100% nội dung và **33 chunks** cận trùng lặp $\ge 90\%$), ưu tiên giữ lại các chunk có cấu trúc breadcrumb heading context sâu nhất và gộp nguồn gốc tài liệu (`duplicate_doc_sources`).
3. **Giữ lại trọn vẹn (1,871 chunks - 66.80%)**: Toàn bộ tri thức độc bản, chất lượng cao phục vụ khách hàng ra quyết định mua xe: Giá bán, lăn bánh 63 tỉnh, thông số kỹ thuật, gói vay trả góp, chính sách pin, trạm sạc và bảo hành 10 năm.

---

## 📊 2. Thống kê tệp dữ liệu tầng Gold

| Tệp dữ liệu | Số lượng bản ghi | Dung lượng | Mục đích & Vai trò kiến trúc trong RAG |
| :--- | :---: | :---: | :--- |
| **`gold_chunks.jsonl`** | **1,871 chunks** | 3.5 MB | **Kho tri thức phục vụ Semantic Vector Search (Dense Retrieval)**.<br/>Mỗi chunk chèn sẵn breadcrumbs ngữ cảnh (`[VF 8 > Chính sách pin]`) và nhãn chủ đề tư vấn. |
| **`gold_faq.jsonl`** | **400 Q&A** | 483.1 KB | **Bộ câu hỏi - đáp chuẩn phục vụ Semantic Routing & Cache**.<br/>So khớp trực tiếp câu hỏi người dùng, trả về đáp án chuẩn mà không tốn chi phí gọi LLM. |
| **`gold_vehicles.jsonl`** | **27 xe** | 32.8 KB | **Danh mục ô tô điện VinFast hoàn chỉnh** kèm giá niêm yết và thông số kỹ thuật. |
| **`gold_documents.jsonl`** | **112 docs** | 2.9 MB | Toàn văn 112 tài liệu sạch đã được chứng nhận phục vụ tư vấn mua xe. |
| **`gold_report.json`** | 1 báo cáo | 1.2 KB | Báo cáo kiểm định chất lượng và phân bổ chủ đề. |

### 🗄️ Bảng dữ liệu quan hệ thuần xe điện (`rdb_schema/`)
Đã loại bỏ dữ liệu xe máy/xe đạp điện, giữ lại bảng số liệu chuẩn xác cho Text-to-SQL:

| Tên bảng CSV | Số dòng dữ liệu | Dung lượng |
| :--- | :---: | :---: |
| `cars_catalog.csv` | 14 dòng | 1.6 KB |
| `fee_rules.csv` | 6 dòng | 1.1 KB |
| `provinces.csv` | 63 dòng | 2.5 KB |
| `rolling_cost_matrix.csv` | 162 dòng | 23.9 KB |
| `trims_pricing.csv` | 27 dòng | 4.8 KB |

---

## 🏷️ 3. Phân bổ theo 7 Chủ đề Tư vấn Mua Xe

| Chủ đề tư vấn | Số lượng chunks giữ lại |
| :--- | :---: |
| **Báo giá & Dự toán chi phí lăn bánh** (`bao_gia_chi_phi`) | 581 chunks |
| **Thông số kỹ thuật & Kinh nghiệm chọn xe** (`thong_so_va_chon_xe`) | 456 chunks |
| **Thủ tục pháp lý: Đăng ký, Biển số, Trước bạ** (`thu_tuc_phap_ly_so_huu`) | 308 chunks |
| **Chương trình ưu đãi, Khuyến mại & VinClub** (`chinh_sach_uu_dai`) | 239 chunks |
| **Chính sách Pin, Thuê pin & Trạm sạc V-GREEN** (`pin_va_tram_sac`) | 161 chunks |
| **Tài chính, Gói vay ngân hàng & Trả góp** (`tai_chinh_tra_gop`) | 73 chunks |
| **Bảo hành 10 năm & Dịch vụ hậu mãi 24/7** (`bao_hanh_hau_mai`) | 53 chunks |

---

## 🗑️ 4. Thống kê nội dung đã lọc bỏ (Filtered Out)

| Lý do loại bỏ | Số lượng chunks |
| :--- | :---: |
| No car purchasing or consultation relevance | 396 chunks |
| Insurance enterprise bureaucracy (non-vehicle buyer relevance) | 258 chunks |
| Excluded legal document: Nghi Dinh 90 2023 Nd Cp Phi Su Dung Duong Bo | 143 chunks |

---

## 💻 5. Ví dụ nạp dữ liệu bằng Python
```python
import json

# Đọc danh sách chunks tầng Gold để tính embedding
with open("dataset/gold/gold_chunks.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        chunk = json.loads(line)
        topic = chunk.get("metadata", {}).get("gold_topic")
        content = chunk["content"]
        # print(f"Topic: {topic} | Length: {len(content)} chars")
        break
```
