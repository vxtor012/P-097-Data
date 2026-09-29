"""src/data_pipeline/normalize — Bronze → Silver Data Normalization Pipeline.

Quét các thư mục faqs, legal, news, policies, specs trong `data/landing/`,
trích xuất nội dung từ PDF / JSON / CSV, chuẩn hóa và xuất Markdown + YAML Frontmatter vào `data/standardized/`.
Tuyệt đối không can thiệp thư mục `relational`.
"""

from src.data_pipeline.normalize.file_extractors import (
    ExtractionResult,
    extract_csv,
    extract_file,
    extract_json,
    extract_pdf,
    is_supported_file,
)
from src.data_pipeline.normalize.metadata_extractor import (
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
from src.data_pipeline.normalize.normalize_to_silver import (
    ALLOWED_CATEGORIES,
    EXCLUDED_CATEGORIES,
    build_markdown_output,
    is_target_file,
    process_single_file,
    run_normalize_pipeline,
)
from src.data_pipeline.normalize.text_cleaner import (
    clean_text_pipeline,
    deduplicate_paragraphs,
    heal_broken_lines,
    normalize_unicode,
    normalize_whitespace,
    remove_noise_lines,
)

__all__ = [
    # Pipeline Orchestration & Category Filtering
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
