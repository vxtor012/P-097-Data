"""
Unit tests for ChunkDeduplicator.
Tests exact deduplication, near-duplicate similarity, and provenance tracking.
"""

import pytest
from pipeline.filters.chunk_deduplicator import ChunkDeduplicator
from pipeline.models.schemas import SilverChunk


def test_exact_deduplication_prefers_deeper_heading():
    dedup = ChunkDeduplicator(enable_exact=True, enable_near=False)

    chunk_shallow = SilverChunk(
        chunk_id="chunk_1",
        doc_id="doc_a",
        chunk_index=0,
        heading_path=["Bảng giá xe"],
        heading_context="Bảng giá xe",
        content="Lệ phí đăng ký và cấp biển số tại Hà Nội, TP.HCM là 20.000.000 VNĐ.",
        raw_chunk_text="Lệ phí đăng ký và cấp biển số tại Hà Nội, TP.HCM là 20.000.000 VNĐ.",
        token_estimate=15,
        char_count=68,
        category="gia_xe",
        source_type="html_article",
        metadata={"consultation_score": 0.8},
    )

    chunk_deep = SilverChunk(
        chunk_id="chunk_2",
        doc_id="doc_b",
        chunk_index=1,
        heading_path=["Bảng giá xe", "VF 8", "Lệ phí trước bạ và biển số"],
        heading_context="Bảng giá xe > VF 8 > Lệ phí trước bạ và biển số",
        content="Lệ phí đăng ký và cấp biển số tại Hà Nội, TP.HCM là 20.000.000 VNĐ.",
        raw_chunk_text="Lệ phí đăng ký và cấp biển số tại Hà Nội, TP.HCM là 20.000.000 VNĐ.",
        token_estimate=15,
        char_count=68,
        category="gia_xe",
        source_type="html_article",
        metadata={"consultation_score": 0.9},
    )

    res = dedup.deduplicate([chunk_shallow, chunk_deep])

    assert len(res.unique_chunks) == 1
    assert res.exact_duplicates_count == 1
    kept = res.unique_chunks[0]
    # Kept chunk should be chunk_deep because it has deeper heading_path and higher score
    assert kept.chunk_id == "chunk_2"
    assert "doc_a" in kept.metadata["duplicate_doc_sources"]
    assert "doc_b" in kept.metadata["duplicate_doc_sources"]
    assert kept.metadata["duplicate_count"] == 1


def test_near_deduplication():
    dedup = ChunkDeduplicator(enable_exact=False, enable_near=True, similarity_threshold=0.85)

    text_a = (
        "Khách hàng mua xe ô tô điện VinFast VF 8 được hưởng chính sách bảo hành 10 năm "
        "hoặc 200.000 km tùy điều kiện nào đến trước trên toàn bộ hệ thống xưởng dịch vụ."
    )
    # text_b has slight variation (e.g. added "chính hãng")
    text_b = (
        "Khách hàng mua xe ô tô điện VinFast VF 8 được hưởng chính sách bảo hành 10 năm "
        "hoặc 200.000 km tùy điều kiện nào đến trước trên toàn bộ hệ thống xưởng dịch vụ chính hãng."
    )

    chunk_a = SilverChunk(
        chunk_id="chunk_a",
        doc_id="doc_1",
        chunk_index=0,
        heading_path=["Chính sách bảo hành"],
        heading_context="Chính sách bảo hành",
        content=text_a,
        raw_chunk_text=text_a,
        token_estimate=30,
        char_count=len(text_a),
        category="bao_hanh",
        source_type="html_article",
        metadata={"gold_topic": "bao_hanh_hau_mai"},
    )

    chunk_b = SilverChunk(
        chunk_id="chunk_b",
        doc_id="doc_2",
        chunk_index=0,
        heading_path=["Chính sách bảo hành"],
        heading_context="Chính sách bảo hành",
        content=text_b,
        raw_chunk_text=text_b,
        token_estimate=31,
        char_count=len(text_b),
        category="bao_hanh",
        source_type="html_article",
        metadata={"gold_topic": "bao_hanh_hau_mai"},
    )

    res = dedup.deduplicate([chunk_a, chunk_b])

    assert len(res.unique_chunks) == 1
    assert res.near_duplicates_count == 1
    assert res.total_dropped == 1


def test_distinct_chunks_preserved():
    dedup = ChunkDeduplicator(enable_exact=True, enable_near=True, similarity_threshold=0.90)

    chunk_1 = SilverChunk(
        chunk_id="c1",
        doc_id="d1",
        chunk_index=0,
        heading_path=["Giá xe VF 3"],
        heading_context="Giá xe VF 3",
        content="Giá xe VinFast VF 3 thuê pin từ 240 triệu đồng.",
        raw_chunk_text="Giá xe VinFast VF 3 thuê pin từ 240 triệu đồng.",
        token_estimate=12,
        char_count=48,
        category="gia_xe",
        source_type="html_article",
        metadata={"gold_topic": "bao_gia_chi_phi"},
    )

    chunk_2 = SilverChunk(
        chunk_id="c2",
        doc_id="d2",
        chunk_index=0,
        heading_path=["Trạm sạc"],
        heading_context="Trạm sạc",
        content="Hệ thống trạm sạc V-GREEN phủ sóng 63 tỉnh thành cả nước.",
        raw_chunk_text="Hệ thống trạm sạc V-GREEN phủ sóng 63 tỉnh thành cả nước.",
        token_estimate=12,
        char_count=58,
        category="tram_sac",
        source_type="html_article",
        metadata={"gold_topic": "pin_va_tram_sac"},
    )

    res = dedup.deduplicate([chunk_1, chunk_2])

    assert len(res.unique_chunks) == 2
    assert res.total_dropped == 0
