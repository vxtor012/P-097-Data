import pytest
from src.core.models import BatteryPolicy, DocumentCategory, RawDocument
from src.splitters.car_spec_splitter import CarSpecSplitter
from src.splitters.finance_splitter import FinanceSplitter
from src.splitters.legal_splitter import LegalSplitter
from src.splitters.policy_splitter import PolicySplitter


# -------------------------------------------------------------------------
# Acceptance Criterion 1: test_legal_splitter_integrity
# -------------------------------------------------------------------------
def test_legal_splitter_integrity():
    """Nhập một văn bản Nghị định gồm 5 Điều.
    Kết quả đầu ra không được làm mất bất kỳ một 'Khoản' hoặc 'Điểm' nào.
    Mỗi chunk phải có breadcrumb chứa chính xác tên 'Điều'.
    """
    sample_legal_text = """
    Chương I: QUY ĐỊNH CHUNG

    Điều 1. Phạm vi điều chỉnh
    1. Nghị định này quy định về đối tượng chịu lệ phí trước bạ, người nộp lệ phí trước bạ.
    2. Áp dụng đối với ô tô điện, xe máy điện và các phương tiện giao thông đường bộ khác.

    Điều 2. Đối tượng chịu lệ phí
    1. Ô tô điện chạy pin và các dòng xe thuần điện đăng ký lần đầu.
    2. Các dòng xe hybrid cắm sạc (PHEV) có tiêu chuẩn khí thải Euro 5.

    Điều 3. Người nộp lệ phí
    Tổ chức, cá nhân có tài sản thuộc đối tượng chịu lệ phí trước bạ quy định tại Điều 2.

    Chương II: MỨC THU VÀ CHÍNH SÁCH ƯU ĐÃI

    Điều 4. Mức thu lệ phí trước bạ theo tỷ lệ (%)
    1. Ô tô điện chạy pin:
    a) Trong vòng 3 năm đầu kể từ ngày Nghị định có hiệu lực: Nộp lệ phí trước bạ lần đầu với mức thu là 0%.
    b) Trong vòng 2 năm tiếp theo: Nộp lệ phí trước bạ lần đầu bằng 50% mức thu của xe xăng có cùng số chỗ ngồi.
    2. Xe máy điện VinFast:
    a) Đăng ký tại các thành phố trực thuộc Trung ương: Mức thu là 5%.
    b) Đăng ký tại các địa phương khác: Mức thu là 2%.

    Điều 5. Hiệu lực thi hành
    1. Nghị định này có hiệu lực thi hành kể từ ngày 01 tháng 3 năm 2022.
    2. Bãi bỏ các quy định trước đây trái với Nghị định này.
    """

    raw_doc = RawDocument.create(
        raw_content=sample_legal_text,
        title="Nghị định 10/2022/NĐ-CP",
        category=DocumentCategory.LEGAL,
        file_type="txt",
    )

    splitter = LegalSplitter(max_chunk_size=800)
    chunks, parent_chunks = splitter.split(raw_doc)

    # Must generate 5 ParentChunks (1 per Điều)
    assert len(parent_chunks) == 5
    dieu_titles = [p.title for p in parent_chunks]
    assert any("Điều 1" in t for t in dieu_titles)
    assert any("Điều 2" in t for t in dieu_titles)
    assert any("Điều 3" in t for t in dieu_titles)
    assert any("Điều 4" in t for t in dieu_titles)
    assert any("Điều 5" in t for t in dieu_titles)

    # Every child chunk must have breadcrumb containing exact Điều name
    for chunk in chunks:
        assert "ĐIỀU " in chunk.breadcrumb
        assert chunk.parent_id is not None

    # Check that Khoản & Điểm are not lost
    combined_content = " ".join(c.content for c in chunks)
    assert "mức thu là 0%" in combined_content
    assert "bằng 50% mức thu của xe xăng" in combined_content
    assert "Mức thu là 5%" in combined_content
    assert "Mức thu là 2%" in combined_content
    assert "kể từ ngày 01 tháng 3 năm 2022" in combined_content
    assert "Bãi bỏ các quy định trước đây" in combined_content


# -------------------------------------------------------------------------
# Acceptance Criterion 2: test_car_spec_table_preservation
# -------------------------------------------------------------------------
def test_car_spec_table_preservation():
    """Nhập bảng so sánh thông số VF 7 (Base vs Plus).
    Kiểm tra Markdown Table đầu ra: Số lượng cột và hàng phải nguyên vẹn,
    không có dòng bị gãy ngang (orphan cells).
    """
    table_content = """# Thông số kỹ thuật VinFast VF 7

Bảng so sánh chi tiết giữa 2 phiên bản Base và Plus:

| Thông số | VF 7 Base | VF 7 Plus |
| --- | --- | --- |
| Giá niêm yết (kèm pin) | 999.000.000 VNĐ | 1.199.000.000 VNĐ |
| Dài x Rộng x Cao (mm) | 4.545 x 1.890 x 1.635 | 4.545 x 1.890 x 1.635 |
| Chiều dài cơ sở (mm) | 2.840 | 2.840 |
| Công suất tối đa | 130 kW / 174 hp | 260 kW / 349 hp |
| Mô-men xoắn cực đại | 250 Nm | 500 Nm |
| Hệ dẫn động | Cầu trước (FWD) | 2 cầu toàn thời gian (AWD) |
| Quãng đường (WLTP) | 375 km | 431 km |
| Kích thước la-zăng | 19 inch | 20 inch |
"""

    raw_doc = RawDocument.create(
        raw_content=table_content,
        title="Thông số kỹ thuật VinFast VF 7",
        category=DocumentCategory.CAR_SPEC,
        file_type="md",
    )

    splitter = CarSpecSplitter()
    chunks, parent_chunks = splitter.split(raw_doc)

    assert len(parent_chunks) >= 1
    assert len(chunks) >= 1

    # Check table in generated chunks
    found_table = False
    for chunk in chunks:
        if "| Thông số | VF 7 Base | VF 7 Plus |" in chunk.content:
            found_table = True
            lines = [l for l in chunk.content.splitlines() if l.startswith("|")]
            # Check row count intact (1 header + 1 separator + 8 data rows = 10 rows)
            assert len(lines) == 10
            for row in lines:
                # 3 columns separated by pipes -> each row has 4 '|' characters
                assert row.count("|") == 4
                # Ensure no orphaned trailing or leading cells
                assert row.endswith("|")

    assert found_table, "Complete spec table must be preserved in at least one chunk."


# -------------------------------------------------------------------------
# Acceptance Criterion 3: test_parent_child_linking
# -------------------------------------------------------------------------
def test_parent_child_linking():
    """Kiểm tra parent_id trong mọi ChildChunk phải trỏ tới đúng một ParentChunk."""
    content = """# VinFast VF 6

## Phiên bản Base
Giá niêm yết: 675.000.000 VNĐ
Công suất: 100 kW. Quãng đường 399 km.

## Phiên bản Plus
Giá niêm yết: 765.000.000 VNĐ
Công suất: 150 kW. Quãng đường 381 km.
Tính năng ADAS cấp độ 2 tích hợp hỗ trợ lái trên cao tốc.
"""
    raw_doc = RawDocument.create(
        raw_content=content,
        title="VinFast VF 6 Toàn Diện",
        category=DocumentCategory.CAR_SPEC,
        file_type="md",
    )

    splitter = CarSpecSplitter()
    chunks, parent_chunks = splitter.split(raw_doc)

    parent_map = {p.parent_id: p for p in parent_chunks}

    for chunk in chunks:
        assert chunk.parent_id is not None
        assert chunk.parent_id in parent_map
        parent = parent_map[chunk.parent_id]
        assert chunk.chunk_id in parent.child_chunk_ids


# -------------------------------------------------------------------------
# Acceptance Criterion 4: test_deduplication
# -------------------------------------------------------------------------
def test_deduplication():
    """Upload 2 lần cùng một file nội dung giống hệt nhau (MD5 hash trùng).
    Pipeline phải phát hiện và ghi nhận cùng một content_hash.
    """
    text = "Nội dung kiểm tra trùng lặp cho VinFast VF 3."
    doc1 = RawDocument.create(raw_content=text, title="Doc 1", category=DocumentCategory.CAR_SPEC, file_type="txt")
    doc2 = RawDocument.create(raw_content=text, title="Doc 2", category=DocumentCategory.CAR_SPEC, file_type="txt")

    assert doc1.content_hash == doc2.content_hash
    assert len(doc1.content_hash) == 32


# -------------------------------------------------------------------------
# Acceptance Criterion 5: test_numeric_metadata_filtering
# -------------------------------------------------------------------------
def test_numeric_metadata_filtering():
    """Kiểm tra trường price_vnd được parse đúng kiểu số nguyên (int),
    cho phép thực thi query lọc: WHERE price_vnd BETWEEN 500000000 AND 800000000.
    """
    content = """# Báo giá VinFast VF 6
Phiên bản VF 6 Base có giá bán niêm yết là 675.000.000 VNĐ (thuê pin).
Đặt cọc sớm nhận ưu đãi 20 triệu đồng.
"""
    raw_doc = RawDocument.create(
        raw_content=content,
        title="Báo giá VF 6",
        category=DocumentCategory.CAR_SPEC,
        file_type="md",
    )

    splitter = CarSpecSplitter()
    chunks, _ = splitter.split(raw_doc)

    pricing_chunks = [c for c in chunks if c.metadata.price_vnd is not None]
    assert len(pricing_chunks) > 0

    chunk = pricing_chunks[0]
    price = chunk.metadata.price_vnd

    assert isinstance(price, int)
    assert price == 675_000_000
    # Simulate SQL WHERE price_vnd BETWEEN 500000000 AND 800000000
    assert 500_000_000 <= price <= 800_000_000


# -------------------------------------------------------------------------
# Test Policy Splitter and Finance Splitter
# -------------------------------------------------------------------------
def test_policy_and_vgreen_splitter():
    vgreen_content = """# Biểu phí trạm sạc V-Green
Biểu phí dịch vụ sạc xe điện VinFast tại trạm sạc V-Green là 3.858 VNĐ/kWh (đã bao gồm VAT).
Phụ thu đỗ xe quá giờ sau khi xe đã sạc đầy 100% quá 30 phút là 1.000 VNĐ/phút.

# Công suất trụ sạc
Trụ sạc AC công suất 11kW thích hợp sạc qua đêm.
Trụ sạc DC siêu nhanh công suất 150kW đến 250kW giúp sạc từ 10% đến 70% chỉ trong 25 phút.
Cổng sạc chuẩn CCS2 tương thích toàn cầu.
"""
    raw_doc = RawDocument.create(
        raw_content=vgreen_content,
        title="Chính sách V-Green",
        category=DocumentCategory.CHARGING_STATION,
        file_type="md",
    )

    splitter = PolicySplitter()
    chunks, parent_chunks = splitter.split(raw_doc)

    assert len(parent_chunks) == 1
    assert len(chunks) >= 2
    for c in chunks:
        assert "V-Green" in c.breadcrumb
        assert c.metadata.category == DocumentCategory.CHARGING_STATION


def test_finance_scenario_generation():
    finance_content = """# Chính sách trả góp Techcombank
Ngân hàng Techcombank hỗ trợ vay mua xe điện VinFast với lãi suất ưu đãi 6.9%/năm trong 2 năm đầu.
Hỗ trợ vay đến 80% giá trị xe, thời hạn lên đến 8 năm.
"""
    raw_doc = RawDocument.create(
        raw_content=finance_content,
        title="Gói vay Techcombank",
        category=DocumentCategory.FINANCE,
        file_type="md",
    )

    splitter = FinanceSplitter()
    chunks, parent_chunks = splitter.split(raw_doc)

    assert len(parent_chunks) == 1
    # Should include base chunk + pre-calculated scenarios
    assert len(chunks) > 5

    # Check simulated scenario chunk format
    scenario_chunks = [c for c in chunks if "TÍNH TOÁN TRẢ GÓP" in c.breadcrumb]
    assert len(scenario_chunks) > 0
    sc = scenario_chunks[0]
    assert "- Giá trị xe" in sc.content
    assert "- Tỷ lệ vay:" in sc.content
    assert "- Số tiền gốc hàng tháng:" in sc.content
    assert sc.metadata.price_vnd is not None
