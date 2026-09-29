"""src/data_pipeline/task2_normalize_data.py
Pipeline Chuẩn hóa Dữ liệu Đồng bộ Toàn diện (Task 2 — Bronze → Silver Data Normalization):

1. Mục tiêu & Nguyên lý thiết kế:
   - Đầu vào: Các tệp thuộc faqs, legal, news, policies, specs trong thư mục Bronze `data/landing/` (PDF, JSON, CSV).
   - Đầu ra: File Markdown (.md) chuẩn hóa tại Silver `data/standardized/` kèm YAML Frontmatter.
   - Nguyên tắc: Bảo toàn ngữ nghĩa, loại bỏ nhiễu kỹ thuật (watermark, page numbers, smart quotes).
   - Phạm vi nghiêm ngặt: TUYỆT ĐỐI KHÔNG can thiệp vào thư mục `relational` (dữ liệu quan hệ dạng bảng CSV).
   - Bọc toàn bộ metadata truy vết (data provenance & lineage) vào YAML Frontmatter phục vụ RAG/LLMOps.

2. Tính năng chính:
   - Đa định dạng: PDF (PyMuPDF với font heuristic, bounding box, table handling), JSON, CSV.
   - 9 bước làm sạch văn bản (Unicode NFC, normalize dấu tiếng Việt, line healing, de-hyphenation, dedup).
   - Trích xuất 21 trường metadata phong phú: doc_id (slug-hash), document_code, dates, authority, doc_type, hash, token estimate.
   - Cơ chế tăng dần (Incremental Processing): Skip file không đổi dựa trên SHA-256 hash cache.
   - Báo cáo thống kê chi tiết và logging lỗi độc lập.

Sử dụng:
    python src/data_pipeline/task2_normalize_data.py
    python src/data_pipeline/task2_normalize_data.py --input-dir data/landing --output-dir data/standardized
    python src/data_pipeline/task2_normalize_data.py --overwrite
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

# Cấu hình đường dẫn root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tự động cấu hình mã hóa UTF-8 cho stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import các thành phần từ module normalize
from src.data_pipeline.normalize.file_extractors import (  # noqa: E402
    ExtractionResult,
    extract_csv,
    extract_file,
    extract_json,
    extract_pdf,
    is_supported_file,
)
from src.data_pipeline.normalize.metadata_extractor import (  # noqa: E402
    build_frontmatter_metadata,
    compute_file_sha256,
    detect_document_type,
    detect_language,
    estimate_tokens,
    extract_document_code,
    extract_document_title,
    extract_effective_date,
    extract_issuing_authority,
    generate_doc_id,
)
from src.data_pipeline.normalize.normalize_to_silver import (  # noqa: E402
    ALLOWED_CATEGORIES,
    EXCLUDED_CATEGORIES,
    build_markdown_output,
    is_target_file,
    process_single_file,
    run_normalize_pipeline,
)
from src.data_pipeline.normalize.text_cleaner import (  # noqa: E402
    clean_text_pipeline,
    deduplicate_paragraphs,
    heal_broken_lines,
    normalize_unicode,
    normalize_whitespace,
    remove_noise_lines,
)

# Re-export các hàm và class để đồng bộ toàn dự án
__all__ = [
    # Pipeline Orchestration & Filtering
    "ALLOWED_CATEGORIES",
    "EXCLUDED_CATEGORIES",
    "is_target_file",
    "run_normalize_pipeline",
    "process_single_file",
    "build_markdown_output",
    # Text Cleaning
    "clean_text_pipeline",
    "normalize_unicode",
    "remove_noise_lines",
    "heal_broken_lines",
    "normalize_whitespace",
    "deduplicate_paragraphs",
    # Metadata Extraction
    "build_frontmatter_metadata",
    "compute_file_sha256",
    "generate_doc_id",
    "detect_document_type",
    "detect_language",
    "extract_document_code",
    "extract_effective_date",
    "extract_document_title",
    "extract_issuing_authority",
    "estimate_tokens",
    # File Extractors
    "extract_file",
    "extract_pdf",
    "extract_json",
    "extract_csv",
    "is_supported_file",
    "ExtractionResult",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments cho Task 2 Normalize Data."""
    parser = argparse.ArgumentParser(
        prog="task2_normalize_data",
        description="[Task 2] Bronze → Silver Data Normalization Pipeline. "
                    "Quét các thư mục faqs, legal, news, policies, specs trong data/landing/, "
                    "chuẩn hóa văn bản và xuất Markdown kèm YAML Frontmatter vào data/standardized/. "
                    "Tuyệt đối không can thiệp thư mục relational.",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/landing",
        help="Thư mục Bronze chứa dữ liệu thô (mặc định: data/landing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/standardized",
        help="Thư mục Silver chứa dữ liệu chuẩn hóa (mặc định: data/standardized)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Ghi đè tất cả các file đã tồn tại (mặc định: bỏ qua nếu hash không đổi)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Đường dẫn file ghi log lỗi (mặc định: normalize_errors.log)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Hàm thực thi chính của Task 2 Normalization Pipeline."""
    args = parse_args(argv)

    input_path = PROJECT_ROOT / args.input_dir
    output_path = PROJECT_ROOT / args.output_dir
    log_file_path = Path(args.log_file) if args.log_file else (PROJECT_ROOT / "normalize_errors.log")

    print("=" * 70)
    print("🚀 [TASK 2] BRONZE → SILVER DATA NORMALIZATION PIPELINE")
    print(f"📂 Thư mục nguồn (Bronze): {input_path}")
    print(f"📁 Thư mục đích  (Silver): {output_path}")
    print(f"🔄 Chế độ ghi đè:          {'Bật (--overwrite)' if args.overwrite else 'Tắt (Incremental - chỉ xử lý file mới/đổi)'}")
    print(f"📝 Nhật ký lỗi (Log):      {log_file_path}")
    print("=" * 70)

    start_time = time.time()

    stats = run_normalize_pipeline(
        input_dir=input_path,
        output_dir=output_path,
        overwrite=args.overwrite,
        log_file=log_file_path,
    )

    duration = time.time() - start_time

    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT TASK 2 NORMALIZATION TRONG {duration:.2f} GIÂY!")
    print("📊 TỔNG KẾT:")
    print(f"   - Tổng số file phát hiện : {stats.get('total_files', 0):,}")
    print(f"   - File chuẩn hóa thành công: {stats.get('processed', 0):,}")
    print(f"   - File bỏ qua (unchanged): {stats.get('skipped', 0):,}")
    print(f"   - Số lỗi phát sinh       : {stats.get('errors', 0):,}")
    if stats.get("error_files"):
        print("   - Danh sách file lỗi:")
        for ef in stats["error_files"]:
            print(f"     * {ef}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    main()
