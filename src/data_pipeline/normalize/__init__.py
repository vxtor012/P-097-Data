"""src/data_pipeline/normalize
Module chuẩn hóa dữ liệu Bronze sang Silver sử dụng IBM Docling.
"""

from src.data_pipeline.normalize.docling_converter import DoclingService
from src.data_pipeline.normalize.metadata_utils import (
    build_yaml_frontmatter,
    clean_metadata_dict,
    compute_content_hash,
    compute_file_sha256,
    count_words_and_chars,
    extract_pdf_metadata,
)
from src.data_pipeline.normalize.processor import NormalizationProcessor

__all__ = [
    "DoclingService",
    "NormalizationProcessor",
    "build_yaml_frontmatter",
    "clean_metadata_dict",
    "compute_content_hash",
    "compute_file_sha256",
    "count_words_and_chars",
    "extract_pdf_metadata",
]
