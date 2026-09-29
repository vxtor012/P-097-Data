"""src/data_pipeline/task2_normalize_data.py
Pipeline Chuẩn hóa Dữ liệu Đồng bộ Toàn diện sử dụng IBM Docling (Task 2 — Bronze → Silver Data Normalization):

1. Mục tiêu:
   - Quét toàn bộ tệp văn bản từ `data/landing/` (faqs, legal, news, policies, specs).
   - Áp dụng IBM Docling để phân tích cấu trúc, chuẩn hóa Markdown và trích xuất bảng biểu.
   - Đối với JSON: Chuẩn hóa nội dung trường `raw_content` bằng Docling và bổ sung metadata vào YAML Frontmatter.
   - Đối với PDF (legal): Sử dụng Docling DocumentConverter để chuyển đổi sang Markdown chuẩn xác.
   - Tuyệt đối không can thiệp vào thư mục `relational` (dữ liệu bảng CSV).

2. Sử dụng:
   python src/data_pipeline/task2_normalize_data.py
   python src/data_pipeline/task2_normalize_data.py --input-dir data/landing --output-dir data/standardized
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Cấu hình đường dẫn root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Cấu hình UTF-8 stdout trên Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.data_pipeline.normalize.processor import NormalizationProcessor

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Task2DoclingNormalize")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments cho Task 2 Normalize Data."""
    parser = argparse.ArgumentParser(
        prog="task2_normalize_data",
        description="[Task 2] Bronze → Silver Data Normalization Pipeline bằng IBM Docling. "
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
        default=True,
        help="Ghi đè tất cả các file đã tồn tại",
    )
    parser.add_argument(
        "--use-ocr",
        action="store_true",
        default=False,
        help="Bật OCR cho Docling khi đọc PDF scanned (mặc định tắt để tăng tốc)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Hàm thực thi chính của Task 2 Normalization Pipeline."""
    args = parse_args(argv)

    input_path = PROJECT_ROOT / args.input_dir
    output_path = PROJECT_ROOT / args.output_dir

    print("=" * 70)
    print("🚀 [TASK 2] BRONZE → SILVER DATA NORMALIZATION PIPELINE (IBM DOCLING)")
    print(f"📂 Thư mục nguồn (Bronze): {input_path}")
    print(f"📁 Thư mục đích  (Silver): {output_path}")
    print(f"🔍 Chế độ OCR:             {'Bật' if args.use_ocr else 'Tắt'}")
    print("=" * 70)

    start_time = time.time()

    processor = NormalizationProcessor(
        landing_dir=input_path,
        standardized_dir=output_path,
        overwrite=args.overwrite,
        use_ocr=args.use_ocr,
    )
    stats = processor.run()

    duration = time.time() - start_time

    print("\n" + "=" * 70)
    print(f"🏁 HOÀN TẤT TASK 2 NORMALIZATION BẰNG DOCLING TRONG {duration:.2f} GIÂY!")
    print("📊 TỔNG KẾT:")
    print(f"   - Tổng file nguồn phát hiện  : {stats.get('total_source_files', 0):,}")
    print(f"   - File nguồn xử lý thành công: {stats.get('processed_files', 0):,}")
    print(f"   - File Markdown đã tạo       : {stats.get('generated_markdown_files', 0):,}")
    print(f"   - Số lỗi phát sinh           : {stats.get('errors', 0):,}")
    if stats.get("error_details"):
        print("   - Danh sách lỗi:")
        for err in stats["error_details"]:
            print(f"     * {err}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    main()
