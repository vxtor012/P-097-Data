"""Unit tests for Hierarchical Chunker."""

import pytest
from src.chunking.hierarchical_chunker import HierarchicalChunker


def test_breadcrumb_preservation():
    chunker = HierarchicalChunker(chunk_size=200, chunk_overlap=30)
    markdown = """
# VinFast VF 8
## Chính sách bảo hành
Bảo hành xe 10 năm hoặc 200.000 km tùy điều kiện nào đến trước.
Pin được bảo hành 10 năm không giới hạn số km.
"""
    chunks = chunker.chunk_document(doc_id="test_doc", markdown_text=markdown)
    assert len(chunks) >= 1
    # Check that the chunk contains breadcrumb context
    assert "VinFast VF 8 > Chính sách bảo hành" in chunks[0].heading_context
    assert "[VinFast VF 8 > Chính sách bảo hành]" in chunks[0].content


def test_table_kept_intact():
    chunker = HierarchicalChunker(chunk_size=300, chunk_overlap=30)
    markdown = """
# Bảng giá xe
| Dòng xe | Phiên bản | Giá niêm yết |
|---|---|---|
| VF 3 | Eco | 285.000.000 đ |
| VF 5 | Plus | 540.000.000 đ |
"""
    chunks = chunker.chunk_document(doc_id="test_table", markdown_text=markdown)
    assert len(chunks) == 1
    assert "| VF 3 | Eco |" in chunks[0].content
    assert "| VF 5 | Plus |" in chunks[0].content
