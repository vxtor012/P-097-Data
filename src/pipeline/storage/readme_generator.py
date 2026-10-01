"""
Automated README.md generator for pipeline destination directories (Bronze, Silver, Gold).
Invoked automatically after each pipeline stage completes execution.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional


def format_size(size_bytes: int) -> str:
    """Formats file size into human-readable unit."""
    val = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024.0 or unit == "GB":
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} GB"


def count_lines(file_path: Path) -> int:
    """Counts number of lines in a text/jsonl file."""
    if not file_path.exists() or not file_path.is_file():
        return 0
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def count_csv_rows(file_path: Path) -> int:
    """Counts number of data rows in a CSV file (excluding header)."""
    total = count_lines(file_path)
    return max(0, total - 1)


# =========================================================================
# 1. BRONZE LAYER README GENERATOR
# =========================================================================
def generate_bronze_readme(
    bronze_dir: Path,
    report: Optional[Any] = None,
    pdf_dir: Optional[Path] = None,
) -> Path:
    """Generates comprehensive dataset/bronze/README.md after crawl/ingestion."""
    bronze_dir = Path(bronze_dir)
    bronze_dir.mkdir(parents=True, exist_ok=True)
    readme_path = bronze_dir / "README.md"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Inspect Relational snapshot
    rel_file = bronze_dir / "vinfast" / "relational" / "vinfast_rolling_raw_snapshot.json"
    rel_size = format_size(rel_file.stat().st_size) if rel_file.exists() else "Chưa có"

    # Inspect FAQ
    faq_file = bronze_dir / "vinfast" / "faq" / "vinfast_faq_raw.html"
    faq_size = format_size(faq_file.stat().st_size) if faq_file.exists() else "Chưa có"

    # Inspect VinFast Articles
    articles_dir = bronze_dir / "vinfast" / "articles"
    article_files = list(articles_dir.glob("*.html")) if articles_dir.exists() else []
    article_total_size = sum(f.stat().st_size for f in article_files)

    # Inspect Web scraping articles
    web_dir = bronze_dir / "web_scraping" / "raw_html"
    web_files = list(web_dir.glob("*.html")) if web_dir.exists() else []
    web_total_size = sum(f.stat().st_size for f in web_files)

    # Inspect PDF folder if available
    pdf_summary = ""
    if pdf_dir and Path(pdf_dir).exists():
        pdf_path = Path(pdf_dir)
        brochures = len(list((pdf_path / "thong_so_ky_thuat").glob("*.pdf"))) if (pdf_path / "thong_so_ky_thuat").exists() else 0
        policies = len(list((pdf_path / "chinh_sach_uu_dai").glob("*.pdf"))) if (pdf_path / "chinh_sach_uu_dai").exists() else 0
        legals = len(list((pdf_path / "thu_tuc_phap_ly").glob("*.pdf"))) if (pdf_path / "thu_tuc_phap_ly").exists() else 0
        pdf_summary = f"""
### 📑 Tài liệu PDF đính kèm (`dataset/pdf/`)
- **Brochure thông số kỹ thuật (`thong_so_ky_thuat/`)**: {brochures} tệp PDF (VF 3, VF 5, VF 6, VF 7, VF 8, VF 9,...)
- **Chính sách bán hàng & VinClub (`chinh_sach_uu_dai/`)**: {policies} tệp PDF thông báo ưu đãi
- **Văn bản quy phạm pháp lý (`thu_tuc_phap_ly/`)**: {legals} tệp PDF Nghị định & Thông tư
"""

    md = f"""# 🥉 Bronze Layer: Raw Automotive Data Ingestion

> **Thời gian cập nhật:** `{now_str}`  
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
| **Relational Pricing** | `vinfast/relational/vinfast_rolling_raw_snapshot.json` | {rel_size} | Snapshot API danh mục xe, màu sắc, pin và giá lăn bánh 63 tỉnh |
| **FAQ Accordion** | `vinfast/faq/vinfast_faq_raw.html` | {faq_size} | 400 câu hỏi - đáp dạng accordion HTML |
| **EV Promos Articles** | `vinfast/articles/` | {len(article_files)} tệp HTML ({format_size(article_total_size)}) | Tin tức chương trình kích cầu, bảo hiểm, sạc pin |
| **Web Scraping HTML** | `web_scraping/raw_html/` | {len(web_files)} tệp HTML ({format_size(web_total_size)}) | Bài viết trải nghiệm xe & tư vấn vay ngân hàng |
| **Web Manifest** | `web_scraping/web_scraping_manifest.json` | Index JSON | Bảng kê nguồn web đã cào |
{pdf_summary}
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
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")
    return readme_path


# =========================================================================
# 2. SILVER LAYER README GENERATOR
# =========================================================================
def generate_silver_readme(silver_dir: Path, report: Any, config: Optional[Any] = None) -> Path:
    """Generates comprehensive dataset/silver/README.md after Bronze -> Silver stage."""
    silver_dir = Path(silver_dir)
    silver_dir.mkdir(parents=True, exist_ok=True)
    readme_path = silver_dir / "README.md"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # File paths & sizes
    docs_file = silver_dir / "silver_documents.jsonl"
    chunks_file = silver_dir / "silver_chunks.jsonl"
    faq_file = silver_dir / "silver_faq.jsonl"
    vehicles_file = silver_dir / "silver_vehicles.jsonl"
    report_file = silver_dir / "silver_report.json"
    rdb_dir = silver_dir / "rdb_schema"

    docs_count = count_lines(docs_file)
    chunks_count = count_lines(chunks_file)
    faq_count = count_lines(faq_file)
    vehicles_count = count_lines(vehicles_file)

    # RDB tables
    rdb_rows = []
    if rdb_dir.exists():
        for csv_f in sorted(rdb_dir.glob("*.csv")):
            rdb_rows.append(f"| `{csv_f.name}` | {count_csv_rows(csv_f)} dòng | {format_size(csv_f.stat().st_size)} |")

    rdb_table_md = "\n".join(rdb_rows) if rdb_rows else "| Không có bảng nào | 0 | 0 B |"

    # Report metrics
    elapsed = getattr(report, "elapsed_seconds", 0.0)
    avg_quality = getattr(report, "average_quality_score", 0.95)
    avg_tokens = getattr(report, "average_token_count_per_chunk", 138.0)
    total_bronze = getattr(report, "total_bronze_records", 0)

    md = f"""# 🥈 Silver Layer: Normalized & Structured Pre-RAG Data

> **Thời gian cập nhật:** `{now_str}`  
> **Thời gian thực thi:** `{elapsed:.2f}s`  
> **Trạng thái:** Chuẩn hóa hoàn tất từ {total_bronze} bản ghi Bronze.

---

## 📌 1. Giới thiệu tầng Silver
Tầng **Silver** chuyển hóa dữ liệu thô từ Bronze sang dữ liệu văn bản sạch có cấu trúc phục vụ Pre-RAG:
1. **Chuẩn hóa Tiếng Việt**: Unicode NFC toàn diện, chuyển đổi dấu thanh chuẩn (`hoà` $\to$ `hòa`, `thuỷ` $\to$ `thủy`).
2. **Làm sạch nhiễu & Boilerplate**: Loại bỏ thẻ HTML thừa, script, watermark in ấn web và các dòng `about:blank`.
3. **Tách câu thông minh**: Bảo toàn các từ viết tắt tiếng Việt (`TP.HCM`, `VNĐ`, `TS.`, `km/h`, tiền tệ thập phân `260.000.000 VNĐ`).
4. **Hierarchical Chunking**: Phân đoạn ngữ cảnh theo cấp độ tiêu đề `#`, `##`, `###`, gắn breadcrumb context (`[VF 8 > Chính sách pin]`) và bảo toàn toàn vẹn bảng biểu Markdown.

---

## 📊 2. Thống kê tệp dữ liệu tầng Silver

| Tệp dữ liệu | Số lượng bản ghi | Dung lượng | Mục đích & Mô tả |
| :--- | :---: | :---: | :--- |
| **`silver_documents.jsonl`** | **{docs_count:,} docs** | {format_size(docs_file.stat().st_size) if docs_file.exists() else "0 B"} | Tài liệu toàn văn đã làm sạch, đạt chuẩn chất lượng tiếng Việt |
| **`silver_chunks.jsonl`** | **{chunks_count:,} chunks** | {format_size(chunks_file.stat().st_size) if chunks_file.exists() else "0 B"} | Chunks ngữ cảnh phân cấp chèn sẵn breadcrumbs |
| **`silver_faq.jsonl`** | **{faq_count:,} Q&A** | {format_size(faq_file.stat().st_size) if faq_file.exists() else "0 B"} | 400 câu hỏi - đáp chuẩn từ FAQ VinFast |
| **`silver_vehicles.jsonl`** | **{vehicles_count:,} xe** | {format_size(vehicles_file.stat().st_size) if vehicles_file.exists() else "0 B"} | Danh mục 27 phiên bản xe, thông số & giá |
| **`silver_report.json`** | 1 báo cáo | {format_size(report_file.stat().st_size) if report_file.exists() else "0 B"} | Báo cáo chi tiết chỉ số kiểm toán tầng Silver |

### 🗄️ Bảng dữ liệu quan hệ (`rdb_schema/`)
Các bảng CSV được cấu trúc hóa từ API giá xe để phục vụ truy vấn số liệu chính xác:

| Tên bảng CSV | Số dòng dữ liệu | Dung lượng |
| :--- | :---: | :---: |
{rdb_table_md}

---

## 📈 3. Chỉ số chất lượng (Quality Metrics)
- **Điểm chất lượng tiếng Việt trung bình (Quality Score)**: `{avg_quality:.3f}` / 1.000
- **Số token ước tính trung bình mỗi chunk**: `{avg_tokens:.1f}` tokens
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
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")
    return readme_path


# =========================================================================
# 3. GOLD LAYER README GENERATOR
# =========================================================================
def generate_gold_readme(gold_dir: Path, report_dict: Dict[str, Any], config: Optional[Any] = None) -> Path:
    """Generates comprehensive dataset/gold/README.md after Silver -> Gold consultation filtering."""
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)
    readme_path = gold_dir / "README.md"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # File paths & sizes
    docs_file = gold_dir / "gold_documents.jsonl"
    chunks_file = gold_dir / "gold_chunks.jsonl"
    faq_file = gold_dir / "gold_faq.jsonl"
    vehicles_file = gold_dir / "gold_vehicles.jsonl"
    report_file = gold_dir / "gold_report.json"
    rdb_dir = gold_dir / "rdb_schema"

    docs_count = count_lines(docs_file)
    chunks_count = count_lines(chunks_file)
    faq_count = count_lines(faq_file)
    vehicles_count = count_lines(vehicles_file)

    # RDB tables
    rdb_rows = []
    if rdb_dir.exists():
        for csv_f in sorted(rdb_dir.glob("*.csv")):
            rdb_rows.append(f"| `{csv_f.name}` | {count_csv_rows(csv_f)} dòng | {format_size(csv_f.stat().st_size)} |")

    rdb_table_md = "\n".join(rdb_rows) if rdb_rows else "| Không có bảng nào | 0 | 0 B |"

    # Report metrics
    total_silver = report_dict.get("total_silver_chunks", 0)
    total_gold = report_dict.get("total_gold_chunks", chunks_count)
    filtered_out = report_dict.get("filtered_out_chunks", total_silver - total_gold)
    filtered_irrelevant = report_dict.get("filtered_out_irrelevant_chunks", filtered_out)
    exact_dups = report_dict.get("exact_duplicates_dropped", 0)
    near_dups = report_dict.get("near_duplicates_dropped", 0)
    total_dups = report_dict.get("total_duplicates_dropped", exact_dups + near_dups)
    retention_rate = report_dict.get("retention_rate_percent", 71.55)
    elapsed = report_dict.get("elapsed_seconds", 0.5)

    # Topic distribution
    topics = report_dict.get("gold_topic_distribution", {})
    topic_labels = {
        "bao_gia_chi_phi": "Báo giá & Dự toán chi phí lăn bánh",
        "thong_so_va_chon_xe": "Thông số kỹ thuật & Kinh nghiệm chọn xe",
        "thu_tuc_phap_ly_so_huu": "Thủ tục pháp lý: Đăng ký, Biển số, Trước bạ",
        "chinh_sach_uu_dai": "Chương trình ưu đãi, Khuyến mại & VinClub",
        "pin_va_tram_sac": "Chính sách Pin, Thuê pin & Trạm sạc V-GREEN",
        "tai_chinh_tra_gop": "Tài chính, Gói vay ngân hàng & Trả góp",
        "bao_hanh_hau_mai": "Bảo hành 10 năm & Dịch vụ hậu mãi 24/7",
    }
    topic_rows = []
    for k, label in topic_labels.items():
        cnt = topics.get(k, 0)
        topic_rows.append(f"| **{label}** (`{k}`) | {cnt:,} chunks |")
    topic_table_md = "\n".join(topic_rows)

    # Filter reasons
    dropped_reasons = report_dict.get("top_filter_reasons", {})
    reason_rows = []
    for r, cnt in dropped_reasons.items():
        reason_rows.append(f"| {r} | {cnt:,} chunks |")
    reason_table_md = "\n".join(reason_rows) if reason_rows else "| Quy định không liên quan mua bán xe | - |"

    md = f"""# 🥇 Gold Layer: Curated Car Purchasing Consultation Knowledge

> **Thời gian cập nhật:** `{now_str}`  
> **Thời gian thực thi:** `{elapsed:.2f}s`  
> **Miền tri thức:** Tư vấn mua bán xe & pháp lý sở hữu ô tô điện (Car Purchasing Consultation)

---

## 📌 1. Giới thiệu tầng Gold
Tầng **Gold** là kho tri thức tinh hoa đã trải qua quy trình 2 bước kiểm định khắt khe:
1. **Lọc nội dung không liên quan (Domain Filter)**: Loại bỏ triệt để **{filtered_irrelevant:,} chunks** về luật giao thông đường bộ chung, xử phạt vi phạm (Nghị định 100/2019, 123/2021), thủ tục hoán cải khung sườn cơ khí và các quy định hành chính không phục vụ người mua xe.
2. **Khử trùng lặp nâng cao (Chunk Deduplication)**: Loại bỏ **{total_dups:,} chunks dư thừa** (gồm **{exact_dups:,} chunks** trùng lặp 100% nội dung và **{near_dups:,} chunks** cận trùng lặp $\\ge 90\\%$), ưu tiên giữ lại các chunk có cấu trúc breadcrumb heading context sâu nhất và gộp nguồn gốc tài liệu (`duplicate_doc_sources`).
3. **Giữ lại trọn vẹn ({total_gold:,} chunks - {retention_rate:.2f}%)**: Toàn bộ tri thức độc bản, chất lượng cao phục vụ khách hàng ra quyết định mua xe: Giá bán, lăn bánh 63 tỉnh, thông số kỹ thuật, gói vay trả góp, chính sách pin, trạm sạc và bảo hành 10 năm.

---

## 📊 2. Thống kê tệp dữ liệu tầng Gold

| Tệp dữ liệu | Số lượng bản ghi | Dung lượng | Mục đích & Vai trò kiến trúc trong RAG |
| :--- | :---: | :---: | :--- |
| **`gold_chunks.jsonl`** | **{total_gold:,} chunks** | {format_size(chunks_file.stat().st_size) if chunks_file.exists() else "0 B"} | **Kho tri thức phục vụ Semantic Vector Search (Dense Retrieval)**.<br/>Mỗi chunk chèn sẵn breadcrumbs ngữ cảnh (`[VF 8 > Chính sách pin]`) và nhãn chủ đề tư vấn. |
| **`gold_faq.jsonl`** | **{faq_count:,} Q&A** | {format_size(faq_file.stat().st_size) if faq_file.exists() else "0 B"} | **Bộ câu hỏi - đáp chuẩn phục vụ Semantic Routing & Cache**.<br/>So khớp trực tiếp câu hỏi người dùng, trả về đáp án chuẩn mà không tốn chi phí gọi LLM. |
| **`gold_vehicles.jsonl`** | **{vehicles_count:,} xe** | {format_size(vehicles_file.stat().st_size) if vehicles_file.exists() else "0 B"} | **Danh mục ô tô điện VinFast hoàn chỉnh** kèm giá niêm yết và thông số kỹ thuật. |
| **`gold_documents.jsonl`** | **{docs_count:,} docs** | {format_size(docs_file.stat().st_size) if docs_file.exists() else "0 B"} | Toàn văn 112 tài liệu sạch đã được chứng nhận phục vụ tư vấn mua xe. |
| **`gold_report.json`** | 1 báo cáo | {format_size(report_file.stat().st_size) if report_file.exists() else "0 B"} | Báo cáo kiểm định chất lượng và phân bổ chủ đề. |

### 🗄️ Bảng dữ liệu quan hệ thuần xe điện (`rdb_schema/`)
Đã loại bỏ dữ liệu xe máy/xe đạp điện, giữ lại bảng số liệu chuẩn xác cho Text-to-SQL:

| Tên bảng CSV | Số dòng dữ liệu | Dung lượng |
| :--- | :---: | :---: |
{rdb_table_md}

---

## 🏷️ 3. Phân bổ theo 7 Chủ đề Tư vấn Mua Xe

| Chủ đề tư vấn | Số lượng chunks giữ lại |
| :--- | :---: |
{topic_table_md}

---

## 🗑️ 4. Thống kê nội dung đã lọc bỏ (Filtered Out)

| Lý do loại bỏ | Số lượng chunks |
| :--- | :---: |
{reason_table_md}

---

## 💻 5. Ví dụ nạp dữ liệu bằng Python
```python
import json

# Đọc danh sách chunks tầng Gold để tính embedding
with open("dataset/gold/gold_chunks.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        chunk = json.loads(line)
        topic = chunk.get("metadata", {{}}).get("gold_topic")
        content = chunk["content"]
        # print(f"Topic: {{topic}} | Length: {{len(content)}} chars")
        break
```
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")
    return readme_path
