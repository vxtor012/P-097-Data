"""src/data_pipeline/normalize/normalize_to_silver.py
Entrypoint chính — Bronze → Silver Data Normalization Pipeline.

Quét các thư mục faqs, legal, news, policies, specs trong data/landing/,
trích xuất nội dung từ PDF / JSON / CSV, chuẩn hóa làm sạch và xuất Markdown (.md)
kèm YAML Frontmatter metadata phong phú vào thư mục data/standardized/.
LƯU Ý: Tuyệt đối không can thiệp vào dữ liệu bảng quan hệ (data/landing/relational/).

Sử dụng:
    python src/data_pipeline/normalize/normalize_to_silver.py
    python src/data_pipeline/normalize/normalize_to_silver.py --input-dir data/landing --output-dir data/standardized
    python src/data_pipeline/normalize/normalize_to_silver.py --overwrite
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Path & Encoding Setup
# ---------------------------------------------------------------------------

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------

from src.data_pipeline.normalize.file_extractors import (  # noqa: E402
    ExtractionResult,
    extract_file,
    is_supported_file,
)
from src.data_pipeline.normalize.metadata_extractor import (  # noqa: E402
    build_frontmatter_metadata,
    compute_file_sha256,
)
from src.data_pipeline.normalize.text_cleaner import clean_text_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------


def _setup_logger(log_file: Path) -> logging.Logger:
    """Cấu hình logger ghi lỗi vào file và console."""
    logger = logging.getLogger("normalize_silver")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # File handler — ghi lỗi
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler — info+
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# YAML Frontmatter Writer
# ---------------------------------------------------------------------------

# Custom YAML Dumper hỗ trợ Unicode tiếng Việt và None → null
class _VNYamlDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.Dumper, data: str) -> Any:
    """Dùng block scalar cho chuỗi dài, literal cho chuỗi ngắn."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    if len(data) > 80:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_VNYamlDumper.add_representer(str, _str_representer)


def build_markdown_output(metadata: dict[str, Any], cleaned_text: str) -> str:
    """Tạo nội dung file Markdown hoàn chỉnh với YAML Frontmatter."""
    clean_meta = {
        k: v for k, v in metadata.items()
        if v is not None and v != "" and v != []
    }
    yaml_str = yaml.dump(
        clean_meta,
        Dumper=_VNYamlDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )

    return f"---\n{yaml_str}---\n\n{cleaned_text}\n"


# ---------------------------------------------------------------------------
# Bộ đệm SHA256 cho cơ chế skip-if-unchanged
# ---------------------------------------------------------------------------


def _load_hash_cache(cache_path: Path) -> dict[str, str]:
    """Load cache SHA256 từ file JSON."""
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_hash_cache(cache_path: Path, cache: dict[str, str]) -> None:
    """Lưu cache SHA256 vào file JSON."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


# ---------------------------------------------------------------------------
# Cấu hình phạm vi danh mục (Chỉ: faqs, legal, news, policies, specs)
# ---------------------------------------------------------------------------

ALLOWED_CATEGORIES: frozenset[str] = frozenset({"faqs", "faq", "legal", "news", "policies", "specs"})
EXCLUDED_CATEGORIES: frozenset[str] = frozenset({"relational"})


def is_target_file(file_path: Path, input_dir: Path) -> bool:
    """Kiểm tra file có thuộc phạm vi chuẩn hóa Bronze → Silver hay không.

    Quy tắc nghiệp vụ:
    - CHỈ chuẩn hóa các tệp trong: faqs, legal, news, policies, specs.
    - TUYỆT ĐỐI KHÔNG động đến thư mục relational (dữ liệu quan hệ dạng bảng).
    - Bỏ qua các file summary/metadata nội bộ (*_summary.json).
    - File phải thuộc định dạng hỗ trợ (PDF, JSON, CSV).
    """
    if not is_supported_file(file_path):
        return False

    if file_path.name.endswith(("_summary.json", "summary.json")):
        return False

    try:
        rel_parts = [p.lower() for p in file_path.relative_to(input_dir).parts]
    except ValueError:
        rel_parts = [p.lower() for p in file_path.parts]

    # Loại trừ tuyệt đối relational
    if any(p in EXCLUDED_CATEGORIES for p in rel_parts):
        return False

    # Kiểm tra danh mục hợp lệ
    # 1. Nếu file nằm trong một thư mục con dưới input_dir
    if len(rel_parts) > 1 and rel_parts[0] in ALLOWED_CATEGORIES:
        return True

    # 2. Hoặc nếu đường dẫn chứa bất kỳ danh mục allowed nào
    if any(p in ALLOWED_CATEGORIES for p in rel_parts):
        return True

    return False


def _infer_doc_type_from_path(rel_path: str) -> str:
    """Suy luận doc_type hint từ cấu trúc thư mục landing."""
    parts = rel_path.lower().replace("\\", "/")
    if "/legal/" in parts or parts.startswith("legal/"):
        return "legal_document"
    if "/faqs/" in parts or parts.startswith("faqs/") or "/faq/" in parts or parts.startswith("faq/"):
        return "faq"
    if "/policies/" in parts or parts.startswith("policies/"):
        return "policy"
    if "/news/" in parts or parts.startswith("news/"):
        return "news"
    if "/specs/" in parts or parts.startswith("specs/"):
        return "technical_manual"
    return ""


# ---------------------------------------------------------------------------
# Core Processing
# ---------------------------------------------------------------------------


def _generate_output_path(file_path: Path, input_dir: Path, output_dir: Path) -> Path:
    """Tạo đường dẫn output giữ nguyên cấu trúc thư mục con, đổi extension → .md."""
    rel = file_path.relative_to(input_dir)
    output_path = output_dir / rel.with_suffix(".md")
    return output_path


def process_single_file(
    file_path: Path,
    input_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    hash_cache: dict[str, str] | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    """Xử lý chuẩn hóa một file đơn lẻ.

    Returns:
        True nếu file được xử lý thành công, False nếu bỏ qua hoặc lỗi.
    """
    log = logger or logging.getLogger("normalize_silver")
    rel_path_str = str(file_path.relative_to(input_dir)).replace("\\", "/")

    # Skip nếu không thuộc danh mục cho phép hoặc là file không hỗ trợ/summary
    if not is_target_file(file_path, input_dir):
        return False

    # Tính SHA256 để kiểm tra thay đổi
    current_hash = compute_file_sha256(file_path)
    output_path = _generate_output_path(file_path, input_dir, output_dir)

    # Skip-if-unchanged logic
    if not overwrite and hash_cache is not None:
        cached_hash = hash_cache.get(rel_path_str, "")
        if cached_hash == current_hash and output_path.exists():
            log.info(f"   ⏭️  Không thay đổi, bỏ qua: {rel_path_str}")
            return False

    # --- BƯỚC 1: Trích xuất nội dung ---
    extraction: ExtractionResult = extract_file(file_path)

    if not extraction.raw_text.strip():
        log.warning(f"Nội dung trống sau khi trích xuất: {rel_path_str}")
        return False

    # --- BƯỚC 2: Làm sạch & Chuẩn hóa ---
    cleaned_text = clean_text_pipeline(extraction.raw_text)

    if not cleaned_text.strip():
        log.warning(f"Nội dung trống sau khi làm sạch: {rel_path_str}")
        return False

    # --- BƯỚC 3: Xây dựng Metadata ---
    doc_type_hint = _infer_doc_type_from_path(rel_path_str)

    metadata = build_frontmatter_metadata(
        file_path=file_path,
        base_dir=input_dir,
        cleaned_text=cleaned_text,
        raw_text=extraction.raw_text,
        total_pages=extraction.total_pages,
        has_tables=extraction.has_tables,
        pdf_title=extraction.pdf_title,
        pdf_creation_date=extraction.pdf_creation_date,
        pdf_mod_date=extraction.pdf_mod_date,
        doc_type_hint=doc_type_hint,
        extra_metadata=extraction.extra_metadata,
    )

    # --- BƯỚC 4: Ghi file Markdown ---
    md_content = build_markdown_output(metadata, cleaned_text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Cập nhật hash cache
    if hash_cache is not None:
        hash_cache[rel_path_str] = current_hash

    log.info(
        f"   ✅ {rel_path_str} → {output_path.relative_to(output_dir)} "
        f"({metadata['char_count']:,} chars, {metadata['word_count']:,} words)"
    )
    return True


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------


def run_normalize_pipeline(
    input_dir: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    log_file: Path | None = None,
) -> dict[str, Any]:
    """Chạy toàn bộ pipeline chuẩn hóa Bronze → Silver.

    Args:
        input_dir: Thư mục chứa dữ liệu Bronze (data/landing/).
        output_dir: Thư mục xuất dữ liệu Silver (data/standardized/).
        overwrite: Nếu True, ghi đè tất cả. Nếu False, bỏ qua file chưa thay đổi.
        log_file: File ghi log lỗi.

    Returns:
        Dictionary thống kê kết quả pipeline.
    """
    if log_file is None:
        log_file = PROJECT_ROOT / "normalize_errors.log"

    logger = _setup_logger(log_file)

    start_time = datetime.now(UTC)
    logger.info("=" * 70)
    logger.info("🔄 Bronze → Silver Data Normalization Pipeline")
    logger.info(f"   📂 Input:  {input_dir}")
    logger.info(f"   📁 Output: {output_dir}")
    logger.info(f"   🔄 Overwrite: {overwrite}")
    logger.info(f"   ⏰ Started: {start_time.isoformat()}")
    logger.info("=" * 70)

    # Kiểm tra thư mục input
    if not input_dir.exists():
        logger.error(f"❌ Thư mục input không tồn tại: {input_dir}")
        return {"error": f"Input directory not found: {input_dir}"}

    # Tạo thư mục output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load hash cache
    cache_path = output_dir / ".normalize_cache.json"
    hash_cache = _load_hash_cache(cache_path)

    # Thu thập danh sách file (chỉ quét các danh mục cho phép, bỏ qua relational)
    all_files = sorted([
        f for f in input_dir.rglob("*")
        if f.is_file() and is_target_file(f, input_dir)
    ])

    total_files = len(all_files)
    logger.info(f"\n📊 Tìm thấy {total_files} file cần xử lý\n")

    # Xử lý từng file với progress bar
    processed = 0
    skipped = 0
    errors = 0
    error_files: list[str] = []

    try:
        from tqdm import tqdm  # noqa: PLC0415
        file_iterator = tqdm(all_files, desc="🔧 Normalizing", unit="file", ncols=100)
    except ImportError:
        logger.info("⚠️  tqdm chưa được cài đặt, hiển thị tiến trình đơn giản.")
        file_iterator = all_files

    for file_path in file_iterator:
        try:
            success = process_single_file(
                file_path,
                input_dir,
                output_dir,
                overwrite=overwrite,
                hash_cache=hash_cache,
                logger=logger,
            )
            if success:
                processed += 1
            else:
                skipped += 1
        except Exception as exc:
            errors += 1
            rel = str(file_path.relative_to(input_dir)).replace("\\", "/")
            error_files.append(rel)
            logger.error(f"❌ Lỗi xử lý {rel}: {type(exc).__name__}: {exc}")

    # Lưu hash cache
    _save_hash_cache(cache_path, hash_cache)

    # Thống kê kết quả
    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    stats = {
        "total_files": total_files,
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "error_files": error_files,
        "duration_seconds": round(duration, 2),
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
    }

    logger.info("\n" + "=" * 70)
    logger.info("📊 KẾT QUẢ PIPELINE")
    logger.info(f"   ✅ Đã xử lý: {processed}/{total_files} files")
    logger.info(f"   ⏭️  Bỏ qua:   {skipped} files")
    logger.info(f"   ❌ Lỗi:      {errors} files")
    logger.info(f"   ⏱️  Thời gian: {duration:.2f}s")

    if error_files:
        logger.info(f"   📝 Chi tiết lỗi: {log_file}")
        for ef in error_files:
            logger.info(f"      - {ef}")

    logger.info("=" * 70)

    # Lưu stats report
    stats_path = output_dir / ".normalize_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="normalize_to_silver",
        description="Bronze → Silver Data Normalization Pipeline. "
                    "Quét data/landing/, chuẩn hóa và xuất Markdown + YAML Frontmatter.",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/landing",
        help="Thư mục chứa dữ liệu Bronze (mặc định: data/landing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/standardized",
        help="Thư mục xuất dữ liệu Silver (mặc định: data/standardized)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Ghi đè tất cả file đã tồn tại (mặc định: bỏ qua nếu hash không đổi)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="File ghi log lỗi (mặc định: normalize_errors.log ở thư mục gốc)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    """Main entrypoint cho CLI."""
    args = parse_args(argv)

    input_dir = PROJECT_ROOT / args.input_dir
    output_dir = PROJECT_ROOT / args.output_dir
    log_file = Path(args.log_file) if args.log_file else None

    return run_normalize_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        overwrite=args.overwrite,
        log_file=log_file,
    )


if __name__ == "__main__":
    main()
