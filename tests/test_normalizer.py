import os
from pathlib import Path
import pytest
from src.core.models import DocumentCategory, RawDocument
from src.core.normalizer import Normalizer


@pytest.fixture
def normalizer(tmp_path):
    # Set output dir to data_new/silver inside tmp or workspace
    return Normalizer(output_dir=tmp_path / "silver")


def test_html_normalization_and_table_preservation(normalizer):
    html_input = """
    <html>
      <head><title>Bảng Giá Xe VF 7</title></head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <div class="popup-dang-ky-lai-thu">Đăng ký ngay!</div>
        <script>console.log("tracking");</script>
        <h1>VinFast VF 7</h1>
        <p>Chi tiết thông số kỹ thuật xe VinFast VF 7.</p>
        <img src="https://vinfastauto.com/images/vf7.jpg" alt="VinFast VF 7 Plus" />
        <table>
          <tr>
            <th>Phiên bản</th>
            <th>Base</th>
            <th>Plus</th>
          </tr>
          <tr>
            <td>Giá niêm yết</td>
            <td>850.000.000 VNĐ</td>
            <td>1.199.000.000 VNĐ</td>
          </tr>
          <tr>
            <td>Công suất</td>
            <td>130 kW</td>
            <td>260 kW</td>
          </tr>
        </table>
        <footer>Bản quyền VinFast 2026</footer>
      </body>
    </html>
    """
    raw_doc = RawDocument.create(
        raw_content=html_input,
        title="Bảng Giá Xe VF 7",
        category=DocumentCategory.CAR_SPEC,
        file_type="html",
        source_url="https://vinfastauto.com/vf7",
    )

    norm_doc = normalizer.normalize(raw_doc, export=True)

    # 1. Boilerplates removed
    assert "tracking" not in norm_doc.markdown_content
    assert "Đăng ký ngay!" not in norm_doc.markdown_content
    assert "Bản quyền VinFast" not in norm_doc.markdown_content

    # 2. Image rewritten
    assert "resource://images/" in norm_doc.markdown_content
    assert "VinFast VF 7 Plus" in norm_doc.markdown_content

    # 3. Table preserved in markdown
    assert "| Phiên bản | Base | Plus |" in norm_doc.markdown_content
    assert "| 850.000.000 VNĐ | 1.199.000.000 VNĐ |" in norm_doc.markdown_content

    # 4. Exported to silver directory
    assert norm_doc.silver_file_path is not None
    silver_path = Path(norm_doc.silver_file_path)
    assert silver_path.exists()
    assert "thong_so_ky_thuat" in str(silver_path)


def test_pdf_boilerplate_and_unwrapping(normalizer):
    pdf_text = """
    CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
    Độc lập - Tự do - Hạnh phúc
    Trang 1/5

    Điều 8. Mức thu lệ phí trước bạ theo tỷ lệ (%)
    1. Ô tô điện chạy pin:
    a) Kể từ ngày Nghị định này có hiệu lực thi hành
    trong vòng 3 năm: nộp lệ phí trước bạ lần đầu với
    mức thu là 0%.
    b) Trong vòng 2 năm tiếp theo: nộp lệ phí trước bạ lần
    đầu với mức thu bằng 50% mức thu đối với ô tô chạy xăng.
    """
    raw_doc = RawDocument.create(
        raw_content=pdf_text,
        title="Nghị định 10/2022/NĐ-CP",
        category=DocumentCategory.LEGAL,
        file_type="pdf",
    )

    norm_doc = normalizer.normalize(raw_doc, export=True)

    # Boilerplate removed
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" not in norm_doc.markdown_content
    assert "Trang 1/5" not in norm_doc.markdown_content

    # Lines unwrapped cleanly
    assert "trong vòng 3 năm: nộp lệ phí trước bạ lần đầu với mức thu là 0%." in norm_doc.markdown_content
    assert Path(norm_doc.silver_file_path).exists()
    assert "thu_tuc_phap_ly" in norm_doc.silver_file_path
